import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db import init_db
from app.routes import health, sync, assignments, reports, demo
from app.utils.logging import get_logger

_IS_VERCEL = os.getenv("VERCEL") == "1"
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        logger.error("init_db failed (tables may not exist): %s", e)
    if not _IS_VERCEL:
        from app.services.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
        yield
        stop_scheduler()
    else:
        yield


app = FastAPI(title="TrackerBot", lifespan=lifespan)

app.include_router(demo.router)
app.include_router(health.router)
app.include_router(sync.router)
app.include_router(assignments.router)
app.include_router(reports.router)
