import os
from fastapi import APIRouter
from sqlalchemy import text

from app.db import engine

router = APIRouter()


@router.get("/health")
def health():
    db_ok = False
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_error = str(e)

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else f"error: {db_error}",
        "gmail_query_set": os.getenv("GMAIL_QUERY") is not None,
        "gmail_token_set": os.getenv("GMAIL_TOKEN_JSON") is not None,
        "gmail_credentials_set": os.getenv("GMAIL_CREDENTIALS_JSON") is not None,
    }
