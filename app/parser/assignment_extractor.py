import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from app.utils.dates import parse_date
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Core rule: every non-reply email is an assignment.
# Name comes from the body (or subject). Time in body = due date.
# ---------------------------------------------------------------------------

# ---- Event type keyword patterns ----
EVENT_PATTERNS = {
    "overdue": re.compile(
        r"\b(overdue|past due|missed|late submission|missed deadline)\b", re.IGNORECASE
    ),
    "due_date_changed": re.compile(
        r"\b(extended?|extension|moved? to|pushed? to|rescheduled?|new deadline|deadline changed|now due)\b",
        re.IGNORECASE,
    ),
    "reminder": re.compile(
        r"\b(reminder|don.t forget|heads.?up|response\s*\?|wake\s*up|still waiting)\b",
        re.IGNORECASE,
    ),
    "punishment": re.compile(
        r"\b(punishment|consequence|penalty|discipline|apology|apologies)\b",
        re.IGNORECASE,
    ),
    "assigned": re.compile(
        r"\b(complete|do|finish|submit|get\s+done|assigned?|task|due|need|must|required|send|write|bring|attend|show up)\b",
        re.IGNORECASE,
    ),
}

# ---- Due date patterns (most → least specific) ----

# "due by/at/on X", "deadline X", "submit by X", "turn in by X"
_DUE_CONTEXT = re.compile(
    r"(?:due|deadline|submit by|turn in by|in by|completed? by)\s*(?:by|on|at|:)?\s*"
    r"([A-Za-z0-9,: ]+(?:AM|PM|am|pm|EOD|eod|sharp|night|tonight|tmrw)?)",
    re.IGNORECASE,
)

# "by 9:40 am", "by EOD", "by midnight", "by Friday at 9pm", "by April 15"
_BY_TIME = re.compile(
    r"\bby\s+("
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s+sharp)?"
    r"|eod\b|midnight\b|tonight\b|tonite\b"
    r"|(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
    r"(?:\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm))?"
    r"(?:\s+(?:eod|midnight|night|noon|morning))?"
    r"|tomorrow(?:\s+night)?(?:\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm))?"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:,?\s+\d{4})?(?:\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm))?"
    r")",
    re.IGNORECASE,
)

# "at 9:40 PM", "at 11:59 pm sharp"
_AT_TIME = re.compile(
    r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s+sharp)?)\b",
    re.IGNORECASE,
)

# "tonight at 9pm", "today by 10pm", "tonight 11:59 PM"
_TONIGHT_TIME = re.compile(
    r"\b(?:tonight|today)\s+(?:at\s+|by\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
    re.IGNORECASE,
)

# "Monday at 9pm", "Friday 11:59 PM", "April 15 at 5pm"
_DAY_TIME = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)"
    r"|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))?",
    re.IGNORECASE,
)

# ---- Normalizations for informal date expressions ----
_NORMALIZATIONS = [
    (re.compile(r'\beod\b', re.IGNORECASE), '11:59 PM'),
    (re.compile(r'\bend of day\b', re.IGNORECASE), '11:59 PM'),
    (re.compile(r'\btmrw night\b', re.IGNORECASE), 'tomorrow 11:59 PM'),
    (re.compile(r'\btomorrow night\b', re.IGNORECASE), 'tomorrow 11:59 PM'),
    (re.compile(r'\btonite\b', re.IGNORECASE), 'today 11:59 PM'),
    (re.compile(r'\btonight\b', re.IGNORECASE), 'today 11:59 PM'),
    (re.compile(r'\btmrw\b', re.IGNORECASE), 'tomorrow'),
    (re.compile(r'\basap\b', re.IGNORECASE), 'today 11:59 PM'),
    (re.compile(r'\bsharp\b', re.IGNORECASE), ''),
    (re.compile(r'\bmidnight\b', re.IGNORECASE), '11:59 PM'),
]

# Profanity: replace with ****
_PROFANITY = re.compile(
    r"\b(fuck(?:ing?|ed?|er|ers|s)?|shit(?:ting?|ted|s)?|ass(?:hole|holes)?|"
    r"bitch(?:es|ing?)?|cunt|dick(?:s)?|cock(?:s)?|pussy(?:ies)?|bastard|"
    r"motherfucker?s?|motherfucking|whores?|sluts?|fagg?ots?|fags?|"
    r"horniest?|horny)\b",
    re.IGNORECASE,
)

# Lines that are automated Google-Groups boilerplate — skip the whole email
_AUTO_SUBJECT = re.compile(
    r"^(you(r| have)?'?re? (subscribed|added|removed|invited)|"
    r"unsubscribe|delivery (failure|error)|bounce|out of office|"
    r"auto.?reply|no.?reply|noreply|google groups digest|"
    r"vacation|away from (my )?office)",
    re.IGNORECASE,
)

# Lines that are greetings / signatures — skip when extracting task name
_SKIP_LINE = re.compile(
    r"^(mr\.|mrs\.|ms\.|dr\.|dear|hello|hi\b|hey|greetings|pledges?|brothers?|everyone|"
    r"apolog|sorry|understood|sincerely|best,|regards|thank|thanks|—|--|unsubscribe|"
    r"university of|berkeley|b\.a\.|b\.s\.|\(\d{3}\))",
    re.IGNORECASE,
)


@dataclass
class ExtractionResult:
    event_type: str = "unknown"
    course: Optional[str] = None
    assignment_name: Optional[str] = None
    raw_excerpt: str = ""
    parsed_due_at: Optional[datetime] = None
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_events(
    cleaned_text: str,
    reference_date: Optional[datetime] = None,
    subject: Optional[str] = None,
) -> list[ExtractionResult]:
    """
    Extract assignment events from a cleaned email body.

    Rule:
    - Non-reply emails: ALWAYS an assignment (new thread = new task).
      Time in body gives the due date; if absent, due_at is None.
    - Reply emails: only processed when they signal a deadline extension.
    """
    if not cleaned_text.strip():
        return []

    is_reply = bool(subject and re.match(r"^(Re|Fwd|FW|RE|FWD)[\s:]", subject.strip()))
    clean_subject = re.sub(r"^(Re|Fwd|FW|RE|FWD)[\s:]+", "", subject or "", flags=re.IGNORECASE).strip() or None

    # Skip automated / system emails
    if clean_subject and _AUTO_SUBJECT.search(clean_subject):
        return []

    # ------------------------------------------------------------------
    # Reply emails: only care about explicit deadline extensions
    # ------------------------------------------------------------------
    if is_reply:
        event_type, confidence = _determine_event_type(cleaned_text)
        if event_type == "due_date_changed":
            due_at = extract_due_date(cleaned_text, reference=reference_date)
            if due_at and clean_subject:
                return [ExtractionResult(
                    event_type="due_date_changed",
                    assignment_name=_censor_profanity(clean_subject),
                    raw_excerpt=cleaned_text[:500],
                    parsed_due_at=due_at,
                    confidence=confidence,
                )]
        return []

    # ------------------------------------------------------------------
    # Original (non-reply) emails: every new thread is an assignment
    # ------------------------------------------------------------------
    due_at = extract_due_date(cleaned_text, reference=reference_date)

    # Special case: "Dailies MM/DD" — tasks are in attachments so body has no
    # time. Build the due datetime directly from the subject date to avoid
    # dateparser jumping to next year for past dates.
    _is_dailies = bool(clean_subject and re.match(r"^dailies?", clean_subject, re.IGNORECASE))
    if due_at is None and _is_dailies:
        dailies_match = re.match(r"^dailies?\s+(\d{1,2})/(\d{1,2})", clean_subject, re.IGNORECASE)
        if dailies_match:
            try:
                ref = reference_date or datetime.utcnow()
                month, day = int(dailies_match.group(1)), int(dailies_match.group(2))
                due_at = ref.replace(month=month, day=day, hour=23, minute=59, second=0, microsecond=0)
            except (ValueError, AttributeError):
                pass

    # Punishment emails: use reference date EOD if no explicit time
    event_type, confidence = _determine_event_type(cleaned_text)
    is_punishment = event_type == "punishment" or bool(
        clean_subject and re.search(r"\b(punishment|penalty|apolog|rizz|date pledge)\b", clean_subject, re.IGNORECASE)
    )
    if due_at is None and is_punishment and reference_date:
        from app.utils.dates import parse_date as _pd
        due_at = _pd("11:59 PM", reference_date=reference_date)

    # For Dailies, use subject as name; for others use body then fall back to subject
    name = clean_subject if _is_dailies else (_extract_task_name(cleaned_text) or clean_subject)
    if not name:
        return []

    name = _censor_profanity(name)

    if event_type == "unknown":
        event_type = "punishment" if is_punishment else "assigned"
        confidence = 0.6

    return [ExtractionResult(
        event_type=event_type,
        assignment_name=name,
        raw_excerpt=cleaned_text[:500],
        parsed_due_at=due_at,  # None is OK — due date not always stated
        confidence=confidence,
    )]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def extract_due_date(text: str, reference: Optional[datetime] = None) -> Optional[datetime]:
    """
    Return the first parseable time/date expression from the text.
    Tries patterns from most to least specific.
    """
    def _try(candidate: str) -> Optional[datetime]:
        candidate = _preprocess(candidate.strip()[:80])
        if not candidate:
            return None
        return parse_date(candidate, reference_date=reference)

    # 1. Explicit due/deadline context
    m = _DUE_CONTEXT.search(text)
    if m:
        result = _try(_trim(m.group(1)))
        if result:
            return result

    # 2. "by <time/day/date>"
    m = _BY_TIME.search(text)
    if m:
        result = _try(m.group(1))
        if result:
            return result

    # 3. "tonight/today at Xpm"
    m = _TONIGHT_TIME.search(text)
    if m:
        result = _try(m.group(1))
        if result:
            return result

    # 4. "at Xpm"
    m = _AT_TIME.search(text)
    if m:
        result = _try(m.group(1))
        if result:
            return result

    # 5. Day-of-week or month + time
    for candidate in _DAY_TIME.findall(text):
        result = _try(candidate)
        if result:
            return result

    return None


def _extract_task_name(text: str) -> Optional[str]:
    """
    Return the first meaningful instructional line from the email body.
    Skips greetings, signatures, and boilerplate lines.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip() and len(l.strip()) > 6]
    for line in lines[:10]:
        if _SKIP_LINE.match(line):
            continue
        # Strip trailing email-signature noise
        line = re.split(r"\s*\||\s{3,}", line)[0].strip()
        if len(line) > 6:
            return line[:120]
    return None


def _determine_event_type(text: str) -> tuple[str, float]:
    scores = {}
    for etype, pattern in EVENT_PATTERNS.items():
        scores[etype] = len(pattern.findall(text))

    priority = ["overdue", "due_date_changed", "punishment", "reminder", "assigned"]
    for etype in priority:
        if scores.get(etype, 0) > 0:
            return etype, min(0.5 + 0.1 * scores[etype], 0.9)

    return "unknown", 0.1


def _censor_profanity(text: str) -> str:
    """Replace profane words with ****."""
    return _PROFANITY.sub("****", text).strip()


def _preprocess(text: str) -> str:
    for pattern, replacement in _NORMALIZATIONS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _trim(candidate: str) -> str:
    """Remove trailing words that bleed past the date expression."""
    candidate = re.split(r'\s+\b(?:with|if|and|but|so|or|unless|when|while|for|from|as)\b', candidate, maxsplit=1)[0]
    return candidate.strip()[:60]
