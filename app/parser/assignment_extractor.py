import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

from app.utils.dates import parse_date
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---- Assignment title patterns ----
TITLE_PATTERNS = [
    re.compile(r"\b(homework|hw)\s*#?\s*(\d+[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(problem\s*set|pset|ps)\s*#?\s*(\d+[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(lab)\s*#?\s*(\d+[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(quiz)\s*#?\s*(\d+[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(project)\s+(?:checkpoint|milestone|part\s*\d+|\d+[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(midterm|final\s*exam|final\s*project)\b", re.IGNORECASE),
    re.compile(r"\b(assignment)\s*#?\s*(\d+[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(discussion)\s*#?\s*(\d+[a-z]?)\b", re.IGNORECASE),
]

# ---- Event type keyword patterns ----
EVENT_PATTERNS = {
    "assigned": re.compile(
        r"\b(released?|assigned?|posted?|available|out now|published)\b", re.IGNORECASE
    ),
    "overdue": re.compile(
        r"\b(overdue|past due|missed|late submission)\b", re.IGNORECASE
    ),
    "due_date_changed": re.compile(
        r"\b(extended?|extension|moved? to|pushed? to|rescheduled?|new deadline|deadline changed)\b",
        re.IGNORECASE,
    ),
    "reminder": re.compile(
        r"\b(reminder|don.t forget|heads.?up|friendly reminder)\b", re.IGNORECASE
    ),
    "due_date": re.compile(
        r"\b(due|deadline|submit by|turn in by)\b", re.IGNORECASE
    ),
}

# ---- Due date context patterns ----
DUE_DATE_CONTEXT = re.compile(
    r"(?:due|deadline|extended? to|moved? to|submit by|turn in by)\s*(?:by|on|at|:)?\s*"
    r"([A-Za-z0-9,: ]+(?:AM|PM|am|pm)?)",
    re.IGNORECASE,
)

# ---- Course name heuristics ----
COURSE_PATTERNS = [
    re.compile(r"\b([A-Z]{2,5})\s*(\d{1,4}[A-Z]?)\b"),  # e.g. CS 101, MATH 54B
]


@dataclass
class ExtractionResult:
    event_type: str = "unknown"
    course: Optional[str] = None
    assignment_name: Optional[str] = None
    raw_excerpt: str = ""
    parsed_due_at: Optional[datetime] = None
    confidence: float = 0.0


def extract_assignment_title(text: str) -> Optional[str]:
    for pattern in TITLE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return None


def extract_course(text: str) -> Optional[str]:
    for pattern in COURSE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return None


def extract_due_date(text: str, reference: Optional[datetime] = None) -> Optional[datetime]:
    m = DUE_DATE_CONTEXT.search(text)
    if m:
        candidate = m.group(1).strip()
        parsed = parse_date(candidate, reference_date=reference)
        if parsed:
            return parsed

    # Fallback: try parsing any date-like substring
    date_keywords = re.findall(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
        r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"[\w\s,:/]*(?:AM|PM|am|pm)?",
        text,
        re.IGNORECASE,
    )
    for candidate in date_keywords:
        parsed = parse_date(candidate.strip(), reference_date=reference)
        if parsed:
            return parsed

    return None


def determine_event_type(text: str) -> tuple[str, float]:
    """Return (event_type, confidence) based on keyword matching."""
    scores = {}
    for event_type, pattern in EVENT_PATTERNS.items():
        matches = pattern.findall(text)
        scores[event_type] = len(matches)

    # Priority order for ambiguous cases
    priority = ["overdue", "due_date_changed", "assigned", "reminder", "due_date"]
    for event_type in priority:
        if scores.get(event_type, 0) > 0:
            confidence = min(0.5 + 0.1 * scores[event_type], 0.9)
            return event_type, confidence

    return "unknown", 0.1


def extract_events(cleaned_text: str, reference_date: Optional[datetime] = None) -> list[ExtractionResult]:
    """
    Extract all assignment events from a cleaned email body.
    Returns a list of ExtractionResult — one per detected assignment reference.
    """
    if not cleaned_text.strip():
        return []

    results = []

    # Split into sentences/chunks for better per-assignment extraction
    chunks = _split_into_chunks(cleaned_text)

    for chunk in chunks:
        title = extract_assignment_title(chunk)
        if not title:
            continue

        event_type, confidence = determine_event_type(chunk)
        course = extract_course(chunk)
        due_at = extract_due_date(chunk, reference=reference_date)

        if due_at and event_type == "unknown":
            event_type = "due_date"
            confidence = 0.5

        result = ExtractionResult(
            event_type=event_type,
            course=course,
            assignment_name=title,
            raw_excerpt=chunk[:500],
            parsed_due_at=due_at,
            confidence=confidence,
        )
        results.append(result)

    # If no chunk had a title but the whole text has strong assignment signals, try whole text
    if not results:
        event_type, confidence = determine_event_type(cleaned_text)
        if event_type not in ("unknown",) or confidence > 0.2:
            due_at = extract_due_date(cleaned_text, reference=reference_date)
            title = extract_assignment_title(cleaned_text)
            course = extract_course(cleaned_text)
            if title or event_type != "unknown":
                results.append(ExtractionResult(
                    event_type=event_type,
                    course=course,
                    assignment_name=title,
                    raw_excerpt=cleaned_text[:500],
                    parsed_due_at=due_at,
                    confidence=confidence * 0.8,
                ))

    return results


def _split_into_chunks(text: str) -> list[str]:
    """Split text into paragraph-level chunks, then by sentence if needed."""
    # First split on blank lines
    paragraphs = re.split(r"\n\n+", text)
    result = []
    for para in paragraphs:
        para = para.strip()
        if not para or len(para) <= 10:
            continue
        # If paragraph has multiple lines, also split by line
        lines = [l.strip() for l in para.splitlines() if l.strip()]
        if len(lines) > 1:
            result.extend(lines)
        else:
            result.append(para)
    return result or [text]
