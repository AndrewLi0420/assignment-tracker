import re
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.models import EmailMessage, AssignmentEvent, Assignment
from app.parser.assignment_extractor import _detect_completion
from app.parser.resolver import resolve_completion

router = APIRouter()


@router.post("/admin/reset")
def reset_data(db: Session = Depends(get_db)):
    """Clear all parsed data so emails are re-processed on next sync."""
    db.execute(text("DELETE FROM assignment_events"))
    db.execute(text("DELETE FROM assignments"))
    db.execute(text("DELETE FROM email_messages"))
    db.commit()
    return {"status": "cleared", "message": "All assignments, events, and messages deleted. Run /sync to reprocess."}


@router.post("/admin/scan-completions")
def scan_completions(dry_run: bool = True, db: Session = Depends(get_db)):
    """
    Retroactively scan all stored reply emails for completion signals.
    Marks matching active assignments as done.
    Pass ?dry_run=false to actually apply changes.
    """
    # Load all stored reply emails
    all_msgs = db.query(EmailMessage).all()
    reply_msgs = [
        m for m in all_msgs
        if m.subject and re.match(r"^(Re|Fwd|FW|RE|FWD)[\s:]", m.subject.strip())
    ]

    detected = []
    completed_ids: set[int] = set()

    for msg in reply_msgs:
        body = msg.cleaned_body or ""
        if not body.strip():
            continue

        clean_subject = re.sub(
            r"^(Re|Fwd|FW|RE|FWD)[\s:]+", "", msg.subject, flags=re.IGNORECASE
        ).strip()

        result = _detect_completion(body, clean_subject)
        if not result:
            continue

        # Find thread matches
        thread_candidates = (
            db.query(Assignment)
            .filter(
                Assignment.source_thread_id == msg.gmail_thread_id,
                Assignment.status != "completed",
                ~Assignment.id.in_(completed_ids),
            )
            .all()
        ) if msg.gmail_thread_id else []

        matched_names = []
        if thread_candidates:
            if len(thread_candidates) == 1:
                matched_names = [thread_candidates[0].assignment_name]
                completed_ids.add(thread_candidates[0].id)
                if not dry_run:
                    thread_candidates[0].status = "completed"
                    thread_candidates[0].completed_at = msg.received_at or datetime.utcnow()
            else:
                from app.parser.resolver import _name_overlap_filter
                overlaps = _name_overlap_filter(clean_subject, thread_candidates, min_overlap=2)
                for a in overlaps:
                    matched_names.append(a.assignment_name)
                    completed_ids.add(a.id)
                    if not dry_run:
                        a.status = "completed"
                        a.completed_at = msg.received_at or datetime.utcnow()

        detected.append({
            "email_id": msg.id,
            "thread_id": msg.gmail_thread_id,
            "subject": msg.subject,
            "body_preview": body[:120].replace("\n", " "),
            "confidence": result.confidence,
            "matched_assignments": matched_names,
        })

    if not dry_run:
        db.commit()

    return {
        "mode": "dry_run" if dry_run else "applied",
        "reply_emails_scanned": len(reply_msgs),
        "completion_signals_detected": len(detected),
        "assignments_completed": len(completed_ids),
        "details": detected,
    }
