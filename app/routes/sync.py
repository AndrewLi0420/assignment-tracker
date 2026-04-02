from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.sync_service import run_sync

router = APIRouter()


@router.post("/sync")
def sync(db: Session = Depends(get_db)):
    result = run_sync(db)
    return result
