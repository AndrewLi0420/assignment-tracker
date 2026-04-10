from datetime import datetime
from sqlalchemy.orm import Session

from app.config import config
from app.gmail_client import get_gmail_service, list_new_message_ids, fetch_message
from app.models import EmailMessage, AssignmentEvent
from app.parser.email_cleaner import clean_new_message_text
from app.parser.assignment_extractor import extract_events
from app.parser.resolver import resolve_assignment, refresh_statuses
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_sync(db: Session, max_new: int = 25) -> dict:
    """
    Main sync entrypoint:
    1. Fetch new Gmail messages
    2. Store raw messages
    3. Clean and extract events
    4. Resolve into canonical assignments
    5. Refresh statuses
    """
    logger.info("Starting sync with query: %s", config.GMAIL_QUERY)

    try:
        service = get_gmail_service()
    except Exception as e:
        logger.error("Failed to get Gmail service: %s", e)
        return {"error": str(e), "new_messages": 0, "new_events": 0}

    existing_ids = {
        row[0] for row in db.query(EmailMessage.gmail_message_id).all()
    }
    new_ids = list_new_message_ids(
        service, config.GMAIL_QUERY, known_ids=existing_ids,
        hard_limit=config.MAX_MESSAGES_PER_SYNC,
    )
    total_pending = len(new_ids)
    new_ids = new_ids[:max_new]  # process a safe batch to avoid Vercel timeout
    logger.info("Found %d new messages total, processing %d this call", total_pending, len(new_ids))

    new_message_count = 0
    new_event_count = 0

    for message_id in new_ids:
        try:
            msg_data = fetch_message(service, message_id)
        except Exception as e:
            logger.error("Failed to fetch message %s: %s", message_id, e)
            continue

        # Store raw message
        cleaned = clean_new_message_text(msg_data.get("raw_body", ""))

        email_msg = EmailMessage(
            gmail_message_id=msg_data["gmail_message_id"],
            gmail_thread_id=msg_data["gmail_thread_id"],
            subject=msg_data.get("subject"),
            sender=msg_data.get("sender"),
            received_at=msg_data.get("received_at"),
            raw_body=msg_data.get("raw_body", ""),
            cleaned_body=cleaned,
            processed_at=datetime.utcnow(),
        )
        db.add(email_msg)
        db.flush()  # get ID without committing
        new_message_count += 1

        # Extract events from cleaned text
        reference_date = msg_data.get("received_at") or datetime.utcnow()
        try:
            events = extract_events(cleaned, reference_date=reference_date, subject=msg_data.get("subject"))
        except Exception as e:
            logger.error("Extraction failed for message %s: %s", message_id, e)
            events = []

        for ev in events:
            event_row = AssignmentEvent(
                gmail_message_id=message_id,
                gmail_thread_id=msg_data["gmail_thread_id"],
                event_type=ev.event_type,
                course=ev.course,
                assignment_name=ev.assignment_name,
                raw_excerpt=ev.raw_excerpt,
                parsed_due_at=ev.parsed_due_at,
                confidence=ev.confidence,
                created_at=reference_date,  # email receive time, not processing time
            )
            db.add(event_row)
            db.flush()

            # Resolve into canonical assignment
            try:
                resolve_assignment(db, event_row)
                new_event_count += 1
            except Exception as e:
                logger.error("Resolve failed for event from %s: %s", message_id, e)

        db.commit()
        logger.info("Processed message %s — %d events extracted", message_id, len(events))

    # Refresh statuses (overdue / due_soon)
    refresh_statuses(db)

    return {
        "new_messages": new_message_count,
        "new_events": new_event_count,
        "processed": len(new_ids),
        "remaining": total_pending - len(new_ids),
    }
