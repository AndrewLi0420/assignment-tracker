from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter()


@router.post("/admin/reset")
def reset_data(db: Session = Depends(get_db)):
    """Clear all parsed data so emails are re-processed on next sync."""
    db.execute(text("DELETE FROM assignment_events"))
    db.execute(text("DELETE FROM assignments"))
    db.execute(text("DELETE FROM email_messages"))
    db.commit()
    return {"status": "cleared", "message": "All assignments, events, and messages deleted. Run /sync to reprocess."}
