import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import config
from app.db import SessionLocal
from app.services.report_service import generate_nightly_report
from app.utils.logging import get_logger

logger = get_logger(__name__)

_scheduler = BackgroundScheduler()


def _run_nightly_report():
    logger.info("Running scheduled nightly report")
    db = SessionLocal()
    try:
        report = generate_nightly_report(db)
        # Print to console and save to file
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
    _scheduler.add_job(
        _run_nightly_report,
        trigger="cron",
        hour=config.NIGHTLY_REPORT_HOUR,
        minute=0,
        id="nightly_report",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — nightly report at %02d:00 UTC", config.NIGHTLY_REPORT_HOUR)


def stop_scheduler():
    _scheduler.shutdown(wait=False)
