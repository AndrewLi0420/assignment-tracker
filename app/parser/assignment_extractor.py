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
    r"(?:due|deadline|extended? to|moved? to|submit by|turn in by|in by)\s*(?:by|on|at|:)?\s*"
    r"([A-Za-z0-9,: ]+(?:AM|PM|am|pm|EOD|eod|sharp|night|tonight|tmrw)?)",
    re.IGNORECASE,
)

# Catch "by <time/day/date>" patterns like "by 9:40 am", "by Friday EOD", "by April 15"
BY_TIME_PATTERN = re.compile(
    r"\bby\s+("
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s+sharp)?"                          # by 9:40 am [sharp]
    r"|eod\b|midnight\b|tonight\b|tonite\b"                                   # by EOD / midnight / tonight
    r"|(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
    r"(?:\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm))?"                     # [at 9pm]
    r"(?:\s+(?:eod|midnight|night|noon|morning))?"                             # [EOD / night]
    r"|tomorrow(?:\s+night)?(?:\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm))?"  # by tomorrow [night]
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:,?\s+\d{4})?(?:\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm))?"  # by April 15 [at 5pm]
    r")",
    re.IGNORECASE,
)

# ---- Course name heuristics ----
COURSE_PATTERNS = [
    re.compile(r"\b([A-Z]{2,5})\s*(\d{1,4}[A-Z]?)\b"),  # e.g. CS 101, MATH 54B
]

# Tokens that match COURSE_PATTERNS but are never course codes
_COURSE_DENYLIST = {
    "AM", "PM", "HW", "PS", "BY", "TO", "AT", "IN", "ON", "OR",
    "AND", "EOD", "THE", "FOR", "DUE", "LAB", "HI", "RE", "FW",
    "FWD", "NO", "OK", "TA",
}


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
        for m in pattern.finditer(text):
            if m.group(1).upper() not in _COURSE_DENYLIST:
                return m.group(0).strip()
    return None


def _trim_date_candidate(candidate: str) -> str:
    """Remove trailing non-date words that bleed past the actual date expression."""
    # Stop at conjunctions/prepositions that signal the date string has ended
    candidate = re.split(r'\s+\b(?:with|if|and|but|so|or|unless|when|while|for|from|as)\b', candidate, maxsplit=1)[0]
    return candidate.strip()[:60]


def extract_due_date(text: str, reference: Optional[datetime] = None) -> Optional[datetime]:
    # Primary: look for explicit due/deadline context
    m = DUE_DATE_CONTEXT.search(text)
    if m:
        candidate = _trim_date_candidate(m.group(1))
        parsed = parse_date(candidate, reference_date=reference)
        if parsed:
            return parsed

    # Secondary: bare "by <time>" pattern (e.g. "by 9:40 am sharp", "by EOD")
    m2 = BY_TIME_PATTERN.search(text)
    if m2:
        candidate = m2.group(1).strip()
        parsed = parse_date(candidate, reference_date=reference)
        if parsed:
            return parsed

    # Tertiary: day/date keywords only when paired with a time (avoids false positives)
    date_keywords = re.findall(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)"
        r"|"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))?",
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


def extract_events(cleaned_text: str, reference_date: Optional[datetime] = None, subject: Optional[str] = None) -> list[ExtractionResult]:
    """
    Extract all assignment events from a cleaned email body.
    Returns a list of ExtractionResult — one per detected assignment reference.
    subject is used as a fallback assignment name when no title pattern matches.
    """
    if not cleaned_text.strip():
        return []

    results = []

    # Detect whether this is a reply/forward email
    is_reply = bool(subject and re.match(r"^(Re|Fwd|FW|RE|FWD):", subject.strip()))

    # Reply emails only matter if they explicitly change a deadline (e.g. "extended to Sunday").
    # All other reply content (confirmations, acknowledgements, discussion) is ignored to avoid
    # misreading things like "respond by 1:45pm" as the assignment due date.
    if is_reply:
        event_type, confidence = determine_event_type(cleaned_text)
        if event_type == "due_date_changed":
            due_at = extract_due_date(cleaned_text, reference=reference_date)
            clean_subject = re.sub(r"^(Re|Fwd|FW|RE|FWD):\s*", "", subject, flags=re.IGNORECASE).strip() or None
            title = extract_assignment_title(cleaned_text) or clean_subject
            course = extract_course(cleaned_text)
            if due_at and title:
                return [ExtractionResult(
                    event_type="due_date_changed",
                    course=course,
                    assignment_name=title,
                    raw_excerpt=cleaned_text[:500],
                    parsed_due_at=due_at,
                    confidence=confidence,
                )]
        return []

    # Strip Re:/Fwd: prefixes from subject for use as fallback title
    clean_subject = None
    if subject:
        clean_subject = re.sub(r"^(Re|Fwd|FW|RE|FWD):\s*", "", subject, flags=re.IGNORECASE).strip() or None

    # Split into sentences/chunks for better per-assignment extraction
    chunks = _split_into_chunks(cleaned_text)

    # Extract course from the full email text once as a fallback for chunks
    # that don't mention the course code inline (e.g. "CS 101" in greeting,
    # "HW 3 due Friday" in a later paragraph).
    full_text_course = extract_course(cleaned_text)

    for chunk in chunks:
        title = extract_assignment_title(chunk)
        if not title:
            continue

        event_type, confidence = determine_event_type(chunk)
        course = extract_course(chunk) or full_text_course
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

    # If no chunk had a standard title pattern, try whole text with subject as name
    if not results:
        event_type, confidence = determine_event_type(cleaned_text)
        due_at = extract_due_date(cleaned_text, reference=reference_date)
        title = extract_assignment_title(cleaned_text) or clean_subject
        course = extract_course(cleaned_text)

        has_signal = due_at or (event_type != "unknown" and confidence >= 0.5)
        if title and has_signal:
            results.append(ExtractionResult(
                event_type=event_type if event_type != "unknown" else ("due_date" if due_at else "assigned"),
                course=course,
                assignment_name=title,
                raw_excerpt=cleaned_text[:500],
                parsed_due_at=due_at,
                confidence=confidence * 0.8 if event_type != "unknown" else 0.3,
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
