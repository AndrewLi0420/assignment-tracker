from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import config

_is_sqlite = "sqlite" in config.DATABASE_URL
_connect_args = {}
if _is_sqlite:
    _connect_args["check_same_thread"] = False
elif "postgresql" in config.DATABASE_URL:
    _connect_args["sslmode"] = "require"

engine = create_engine(config.DATABASE_URL, connect_args=_connect_args)

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
