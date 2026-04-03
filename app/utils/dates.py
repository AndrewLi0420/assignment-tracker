import re
from datetime import datetime
from typing import Optional
import dateparser
from app.config import config

# Normalize informal/shorthand date expressions before passing to dateparser
_NORMALIZATIONS = [
    (re.compile(r'\beod\b', re.IGNORECASE), '11:59 PM'),
    (re.compile(r'\bend of day\b', re.IGNORECASE), '11:59 PM'),
    (re.compile(r'\btmrw night\b', re.IGNORECASE), 'tomorrow 11:59 PM'),
    (re.compile(r'\btomorrow night\b', re.IGNORECASE), 'tomorrow 11:59 PM'),
    (re.compile(r'\btonite\b', re.IGNORECASE), 'today 11:59 PM'),
    (re.compile(r'\btonight\b', re.IGNORECASE), 'today 11:59 PM'),
    (re.compile(r'\btmrw\b', re.IGNORECASE), 'tomorrow'),
    (re.compile(r'\basap\b', re.IGNORECASE), 'today 11:59 PM'),
    (re.compile(r'\bsharp\b', re.IGNORECASE), ''),  # "9:40 am sharp" → "9:40 am"
    (re.compile(r'\bmidnight\b', re.IGNORECASE), '11:59 PM'),
]


def _preprocess(text: str) -> str:
    for pattern, replacement in _NORMALIZATIONS:
        text = pattern.sub(replacement, text)
    return text.strip()


def parse_date(text: str, reference_date: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a natural language date string into a datetime object."""
    text = _preprocess(text)
    if not text:
        return None

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
