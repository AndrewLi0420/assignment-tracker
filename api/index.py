from app.main import app  # noqa: F401 — Vercel picks up the ASGI app
from app.db import init_db

# Vercel's Python runtime does not invoke ASGI lifespan events, so we
# call init_db() at module-import time to ensure tables exist on every
# cold start before any request is handled.
try:
    init_db()
except Exception as e:
    import logging
    logging.getLogger(__name__).error("init_db failed at startup: %s", e)
