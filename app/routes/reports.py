from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.report_service import generate_nightly_report, generate_report_data

router = APIRouter()


@router.get("/report/nightly", response_class=PlainTextResponse)
def nightly_report(db: Session = Depends(get_db)):
    return generate_nightly_report(db)


@router.get("/report/json")
def nightly_report_json(db: Session = Depends(get_db)):
    return generate_report_data(db)
