from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.routes import health, sync, assignments, reports, demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="TrackerBot", lifespan=lifespan)

app.include_router(demo.router)
app.include_router(health.router)
app.include_router(sync.router)
app.include_router(assignments.router)
app.include_router(reports.router)
