import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import config
from app.db import SessionLocal
from app.services.report_service import generate_nightly_report
from app.services.sync_service import run_sync
from app.utils.logging import get_logger

logger = get_logger(__name__)

_scheduler = BackgroundScheduler()


def _run_periodic_sync():
    logger.info("Running scheduled sync")
    db = SessionLocal()
    try:
        result = run_sync(db)
        logger.info("Scheduled sync complete: %s", result)
    except Exception as e:
        logger.error("Scheduled sync failed: %s", e)
    finally:
        db.close()


def _run_nightly_report():
    logger.info("Running scheduled nightly report")
    db = SessionLocal()
    try:
        # Sync first so the report reflects the latest emails
        try:
            run_sync(db)
        except Exception as e:
            logger.warning("Pre-report sync failed (continuing anyway): %s", e)

        report = generate_nightly_report(db)
        print(report)
        report_path = f"reports/nightly_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.txt"
        os.makedirs("reports", exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        logger.info("Nightly report saved to %s", report_path)
    except Exception as e:
        logger.error("Nightly report failed: %s", e)
    finally:
        db.close()


def start_scheduler():
    # Poll Gmail every hour so new assignments are picked up automatically
    _scheduler.add_job(
        _run_periodic_sync,
        trigger="interval",
        hours=1,
        id="periodic_sync",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_nightly_report,
        trigger="cron",
        hour=config.NIGHTLY_REPORT_HOUR,
        minute=0,
        id="nightly_report",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — syncing every hour, nightly report at %02d:00 UTC",
        config.NIGHTLY_REPORT_HOUR,
    )


def stop_scheduler():
    _scheduler.shutdown(wait=False)
