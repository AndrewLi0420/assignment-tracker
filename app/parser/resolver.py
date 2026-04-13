import re
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Assignment, AssignmentEvent, EmailMessage
from app.parser.normalizer import make_normalized_key, normalize_assignment_name
from app.utils.logging import get_logger

# Patterns that indicate the submission was rejected (actives asking for a redo)
_REJECTION_PATTERNS = re.compile(
    r"\b(redo|do\s+it\s+again|try\s+again|not\s+acceptable|wrong\s+answer|"
    r"must\s+be\s+redone|needs?\s+to\s+be\s+redone|incorrect|that.s\s+wrong|"
    r"resubmit|refilm|redo\s+this|not\s+good\s+enough|rejected)\b",
    re.IGNORECASE,
)

logger = get_logger(__name__)


def resolve_completion(db: Session, event: AssignmentEvent) -> list[Assignment]:
    """
    For a completion event, find matching active assignments and mark them done.

    Matching strategy (in priority order):
      1. Same thread_id + exactly 1 active assignment in that thread → auto-complete it.
      2. Same thread_id + multiple assignments → name-overlap match (>= 2 tokens).
      3. No thread match → name-overlap match across all active assignments.

    Returns the list of assignments that were completed.
    """
    now = datetime.utcnow()
    completed: list[Assignment] = []

    # --- Check for rejection messages posted AFTER this submission in the same thread ---
    # If actives replied with "redo", "wrong", "not acceptable", etc., the submission was rejected.
    if event.gmail_thread_id and event.created_at:
        later_msgs = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.gmail_thread_id == event.gmail_thread_id,
                EmailMessage.received_at > event.created_at,
            )
            .all()
        )
        for msg in later_msgs:
            body = msg.cleaned_body or ""
            if _REJECTION_PATTERNS.search(body):
                logger.info(
                    "Skipping auto-complete for thread %s — rejection message found after submission (%s)",
                    event.gmail_thread_id, msg.gmail_message_id,
                )
                return []

    # --- Candidates: same thread ---
    thread_matches = (
        db.query(Assignment)
        .filter(
            Assignment.source_thread_id == event.gmail_thread_id,
            Assignment.status != "completed",
        )
        .all()
    ) if event.gmail_thread_id else []

    if thread_matches:
        if len(thread_matches) == 1:
            # Single assignment in thread — high confidence, auto-complete
            _mark_completed(thread_matches[0], event, now)
            completed.append(thread_matches[0])
            logger.info("Auto-completed (thread/1): %s", thread_matches[0].normalized_key)
        else:
            # Multiple assignments — require name overlap to narrow down
            mention = event.assignment_name or ""
            overlap_matches = _name_overlap_filter(mention, thread_matches, min_overlap=2)
            if overlap_matches:
                for a in overlap_matches:
                    _mark_completed(a, event, now)
                    completed.append(a)
                    logger.info("Auto-completed (thread/overlap): %s", a.normalized_key)
            else:
                # Couldn't pinpoint which one — complete all in thread as a fallback
                # only if the completion message is highly confident (e.g., very short reply)
                if len(mention.split()) <= 4:
                    for a in thread_matches:
                        _mark_completed(a, event, now)
                        completed.append(a)
                        logger.info("Auto-completed (thread/all-short): %s", a.normalized_key)
    else:
        # No thread match — global name-overlap search
        mention = event.assignment_name or ""
        if mention:
            all_active = (
                db.query(Assignment)
                .filter(Assignment.status != "completed")
                .all()
            )
            overlap_matches = _name_overlap_filter(mention, all_active, min_overlap=3)
            for a in overlap_matches:
                _mark_completed(a, event, now)
                completed.append(a)
                logger.info("Auto-completed (global/overlap): %s", a.normalized_key)

    return completed


def _mark_completed(assignment: Assignment, event: AssignmentEvent, now: datetime) -> None:
    assignment.status = "completed"
    assignment.completed_at = now
    _append_note(assignment, f"Auto-completed from email reply ({event.gmail_message_id})")


def _name_overlap_filter(
    mention: str, candidates: list[Assignment], min_overlap: int = 2
) -> list[Assignment]:
    """Return candidates whose normalized name shares >= min_overlap tokens with mention."""
    mention_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", normalize_assignment_name(mention)))
    if not mention_tokens:
        return []

    results = []
    for a in candidates:
        name_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", normalize_assignment_name(a.assignment_name or "")))
        overlap = len(mention_tokens & name_tokens)
        if overlap >= min_overlap:
            results.append(a)
    return results


def resolve_assignment(
    db: Session,
    event: AssignmentEvent,
    due_at_estimated: bool = False,
) -> Assignment:
    """
    Find or create a canonical Assignment from an event.
    Later events win over earlier ones for due dates and status.
    """
    normalized_key = make_normalized_key(event.course, event.assignment_name or "")

    assignment = db.query(Assignment).filter_by(normalized_key=normalized_key).first()

    if assignment is None:
        assignment = Assignment(
            normalized_key=normalized_key,
            course=event.course,
            assignment_name=event.assignment_name or "",
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            source_thread_id=event.gmail_thread_id,
            status="unknown",
        )
        db.add(assignment)
        logger.info("Created new assignment: %s", normalized_key)
    else:
        assignment.last_seen_at = datetime.utcnow()

    # Merge event data into canonical assignment
    _apply_event(assignment, event, due_at_estimated=due_at_estimated)

    db.commit()
    db.refresh(assignment)
    return assignment


def _apply_event(assignment: Assignment, event: AssignmentEvent, due_at_estimated: bool = False) -> None:
    """Apply an event's data onto the canonical assignment."""
    if event.event_type == "assigned":
        if assignment.assigned_at is None:
            assignment.assigned_at = event.created_at
        if event.parsed_due_at:
            # Only upgrade estimated→real, never downgrade real→estimated
            if not due_at_estimated or assignment.due_at_estimated:
                assignment.due_at = event.parsed_due_at
                assignment.due_at_estimated = due_at_estimated
        if assignment.status in ("unknown", None):
            assignment.status = "active"

    elif event.event_type == "due_date":
        if event.parsed_due_at:
            if not due_at_estimated or assignment.due_at_estimated:
                assignment.due_at = event.parsed_due_at
                assignment.due_at_estimated = due_at_estimated
        if assignment.status in ("unknown", None):
            assignment.status = "active"

    elif event.event_type == "due_date_changed":
        # Extension: always overwrite due date with the new one (must be real)
        if event.parsed_due_at and not due_at_estimated:
            assignment.due_at = event.parsed_due_at
            assignment.due_at_estimated = False
        _append_note(assignment, "Due date changed")

    elif event.event_type == "overdue":
        assignment.status = "overdue"
        _append_note(assignment, "Marked overdue")

    elif event.event_type == "reminder":
        if event.parsed_due_at:
            if not due_at_estimated or assignment.due_at_estimated:
                assignment.due_at = event.parsed_due_at
                assignment.due_at_estimated = due_at_estimated
        if assignment.status in ("unknown", None):
            assignment.status = "active"
        if assignment.assigned_at is None:
            assignment.assigned_at = event.created_at

    elif event.event_type == "punishment":
        if event.parsed_due_at:
            if not due_at_estimated or assignment.due_at_estimated:
                assignment.due_at = event.parsed_due_at
                assignment.due_at_estimated = due_at_estimated
        if assignment.status in ("unknown", None):
            assignment.status = "active"
        _append_note(assignment, "Punishment")

    elif event.event_type == "completion":
        # Handled separately via resolve_completion — nothing to do here
        pass

    elif event.event_type == "unknown":
        if event.parsed_due_at:
            if not due_at_estimated or assignment.due_at_estimated:
                assignment.due_at = event.parsed_due_at
                assignment.due_at_estimated = due_at_estimated
        if assignment.status in ("unknown", None):
            assignment.status = "active"


def _append_note(assignment: Assignment, note: str) -> None:
    if assignment.notes:
        assignment.notes = f"{assignment.notes}; {note}"
    else:
        assignment.notes = note


def refresh_statuses(db: Session) -> None:
    """
    Update assignment statuses based on current time.
    Called after sync and before report generation.
    """
    now = datetime.utcnow()
    from datetime import timedelta
    due_soon_threshold = now + timedelta(hours=72)

    assignments = db.query(Assignment).all()
    for a in assignments:
        # Never touch completed assignments — manual or auto completions must persist across syncs
        if a.status == "completed":
            continue

        # Fill missing due_at with EOD fallback (marks as estimated)
        if a.due_at is None:
            fallback_base = a.first_seen_at or now
            a.due_at = fallback_base.replace(hour=23, minute=59, second=0, microsecond=0)
            a.due_at_estimated = True

        # Estimated due dates never go overdue — keep them active
        if a.due_at_estimated:
            if a.status in ("overdue", "unknown", None):
                a.status = "active"
            continue

        # Real due dates: apply time-based status
        if a.due_at < now:
            a.status = "overdue"
        elif a.due_at <= due_soon_threshold:
            a.status = "due_soon"
        else:
            a.status = "active"

    db.commit()
