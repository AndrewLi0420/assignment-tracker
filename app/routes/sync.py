from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.sync_service import run_sync

router = APIRouter()


@router.post("/sync")
def sync(
    db: Session = Depends(get_db),
    limit: int = Query(8, description="Max new messages to process per call (keep low to avoid timeout)"),
):
    result = run_sync(db, max_new=limit)
    return result
