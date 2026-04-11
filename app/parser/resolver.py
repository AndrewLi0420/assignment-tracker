from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Assignment, AssignmentEvent
from app.parser.normalizer import make_normalized_key
from app.utils.logging import get_logger

logger = get_logger(__name__)


def resolve_assignment(
    db: Session,
    event: AssignmentEvent,
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
    _apply_event(assignment, event)

    db.commit()
    db.refresh(assignment)
    return assignment


def _apply_event(assignment: Assignment, event: AssignmentEvent) -> None:
    """Apply an event's data onto the canonical assignment."""
    if event.event_type == "assigned":
        if assignment.assigned_at is None:
            assignment.assigned_at = event.created_at
        if event.parsed_due_at:
            assignment.due_at = event.parsed_due_at
        if assignment.status in ("unknown", None):
            assignment.status = "active"

    elif event.event_type == "due_date":
        if event.parsed_due_at:
            assignment.due_at = event.parsed_due_at
        if assignment.status in ("unknown", None):
            assignment.status = "active"

    elif event.event_type == "due_date_changed":
        # Extension: always overwrite due date with the new one
        if event.parsed_due_at:
            assignment.due_at = event.parsed_due_at
        _append_note(assignment, "Due date changed")

    elif event.event_type == "overdue":
        assignment.status = "overdue"
        _append_note(assignment, "Marked overdue")

    elif event.event_type == "reminder":
        if event.parsed_due_at:
            assignment.due_at = event.parsed_due_at
        if assignment.status in ("unknown", None):
            assignment.status = "active"
        if assignment.assigned_at is None:
            assignment.assigned_at = event.created_at

    elif event.event_type == "punishment":
        if event.parsed_due_at:
            assignment.due_at = event.parsed_due_at
        if assignment.status in ("unknown", None):
            assignment.status = "active"
        _append_note(assignment, "Punishment")

    elif event.event_type == "unknown":
        if event.parsed_due_at:
            assignment.due_at = event.parsed_due_at
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
        if a.status == "overdue":
            continue  # Don't downgrade explicit overdue flags
        if a.due_at is None:
            continue
        if a.due_at < now:
            a.status = "overdue"
        elif a.due_at <= due_soon_threshold:
            a.status = "due_soon"
        else:
            a.status = "active"

    db.commit()
