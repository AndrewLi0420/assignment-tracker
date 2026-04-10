import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db import init_db
from app.routes import health, sync, assignments, reports, demo

_IS_VERCEL = os.getenv("VERCEL") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
