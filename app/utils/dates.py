from datetime import datetime
from typing import Optional
import dateparser
from app.config import config


def parse_date(text: str, reference_date: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a natural language date string into a datetime object."""
    settings = {
        "TIMEZONE": config.TIMEZONE,
        "RETURN_AS_TIMEZONE_AWARE": False,
        "PREFER_DATES_FROM": "future",
    }
    if reference_date:
        settings["RELATIVE_BASE"] = reference_date

    result = dateparser.parse(text, settings=settings)
    return result


def now() -> datetime:
    return datetime.utcnow()
