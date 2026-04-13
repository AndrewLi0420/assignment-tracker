from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import config

_db_url = config.DATABASE_URL
_connect_args = {}

if "sqlite" in _db_url:
    _connect_args["check_same_thread"] = False
elif "postgresql" in _db_url and "sslmode" not in _db_url:
    _db_url += ("&" if "?" in _db_url else "?") + "sslmode=require"

engine = create_engine(_db_url, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Safe incremental schema migrations — idempotent, ADD COLUMN IF NOT EXISTS only."""
    from sqlalchemy import text
    with engine.begin() as conn:
        if "sqlite" in str(engine.url):
            # SQLite: check if column exists via PRAGMA
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(assignments)"))}
            if "due_at_estimated" not in cols:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN due_at_estimated BOOLEAN DEFAULT 0"))
        else:
            # PostgreSQL: ADD COLUMN IF NOT EXISTS
            conn.execute(text(
                "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS due_at_estimated BOOLEAN DEFAULT FALSE"
            ))
            conn.execute(text(
                "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP DEFAULT NULL"
            ))
            # Fix existing assignments: EOD-fallback assignments marked overdue should revert to active
            conn.execute(text("""
                UPDATE assignments
                SET due_at_estimated = TRUE, status = 'active'
                WHERE status = 'overdue'
                  AND due_at IS NOT NULL
                  AND EXTRACT(HOUR FROM due_at) = 23
                  AND EXTRACT(MINUTE FROM due_at) = 59
                  AND EXTRACT(SECOND FROM due_at) = 0
                  AND due_at_estimated = FALSE
            """))
