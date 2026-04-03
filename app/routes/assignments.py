from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db import get_db
from app.models import Assignment, EmailMessage

router = APIRouter()


@router.get("/assignments")
def list_assignments(
    status: Optional[str] = Query(None, description="Filter by status: active, due_soon, overdue, unknown"),
    db: Session = Depends(get_db),
):
    q = db.query(Assignment)
    if status:
        q = q.filter(Assignment.status == status)
    assignments = q.order_by(Assignment.due_at.asc().nulls_last()).all()
    return [_serialize_assignment(a) for a in assignments]


@router.get("/messages")
def list_messages(limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    messages = (
        db.query(EmailMessage)
        .order_by(EmailMessage.received_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": m.id,
            "gmail_message_id": m.gmail_message_id,
            "gmail_thread_id": m.gmail_thread_id,
            "subject": m.subject,
            "sender": m.sender,
            "received_at": m.received_at,
            "processed_at": m.processed_at,
            "cleaned_body_preview": (m.cleaned_body or "")[:300],
        }
        for m in messages
    ]


def _serialize_assignment(a: Assignment) -> dict:
    return {
        "id": a.id,
        "normalized_key": a.normalized_key,
        "course": a.course,
        "assignment_name": a.assignment_name,
        "status": a.status,
        "due_at": a.due_at,
        "assigned_at": a.assigned_at,
        "first_seen_at": a.first_seen_at,
        "last_seen_at": a.last_seen_at,
        "source_thread_id": a.source_thread_id,
        "notes": a.notes,
    }
