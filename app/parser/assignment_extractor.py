import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from app.utils.dates import parse_date
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Two-layer extraction:
#   Layer 1 (regex)  — whole-email heuristics (existing logic)
#   Layer 2 (NLP)    — sentence-level keyword scoring, emits one result per
#                      assignment sentence; merges with Layer 1 output.
# ---------------------------------------------------------------------------

# ---- Layer 1: event type keyword patterns ----
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

# ---- Layer 2: NLP — imperative / action-verb signal ----
# These are action words that, combined with a time expression in the same
# sentence, strongly indicate an assignment.
_ACTION = re.compile(
    r"\b("
    # core imperatives
    r"do|complete|finish|submit|send|bring|get(?:\s+done)?|make|write|record|"
    r"take|film|shoot|upload|post|create|build|run|draw|read|watch|listen|"
    r"attend|show(?:\s+up)?|join|present|perform|deliver|produce|prepare|"
    r"practice|study|memorize|review|edit|update|sign|fill(?:\s+out)?|forward|share|"
    r"respond|reply|dm|message|call|text|buy|"
    # modal / directive phrases (treated as action signals)
    r"need(?:\s+you)?\s+to|must|have\s+to|got\s+to|required\s+to|"
    r"want(?:\s+you)?\s+to|needs?\s+to\s+be|should(?:\s+be)?|"
    r"recreate|include|explain|describe|rank|list|count|calculate|"
    r"add|redo|redo|resubmit|refilm|redo"
    r")\b",
    re.IGNORECASE,
)

# ---- Due date patterns (most → least specific) ----
_DUE_CONTEXT = re.compile(
    r"(?:due|deadline|submit by|turn in by|in by|completed? by)\s*(?:by|on|at|:)?\s*"
    r"([A-Za-z0-9,: ]+(?:AM|PM|am|pm|EOD|eod|sharp|night|tonight|tmrw)?)",
    re.IGNORECASE,
)
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
_AT_TIME = re.compile(
    r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s+sharp)?)\b",
    re.IGNORECASE,
)
_TONIGHT_TIME = re.compile(
    r"\b(?:tonight|today)\s+(?:at\s+|by\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
    re.IGNORECASE,
)
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
    (re.compile(r'\bend of (the )?weekend\b', re.IGNORECASE), 'Sunday 11:59 PM'),
    (re.compile(r'\bend of (the )?night\b', re.IGNORECASE), '11:59 PM'),
]

# Profanity: replace with ****
_PROFANITY = re.compile(
    r"\b(fuck(?:ing?|ed?|er|ers|s)?|shit(?:ting?|ted|s)?|ass(?:hole|holes)?|"
    r"bitch(?:es|ing?)?|cunt|dick(?:s)?|cock(?:s)?|pussy(?:ies)?|bastard|"
    r"motherfucker?s?|motherfucking|whores?|sluts?|fagg?ots?|fags?|"
    r"horniest?|horny)\b",
    re.IGNORECASE,
)

# Automated / system email subjects → skip entire email
_AUTO_SUBJECT = re.compile(
    r"^(you(r| have)?'?re? (subscribed|added|removed|invited)|"
    r"unsubscribe|delivery (failure|error)|bounce|out of office|"
    r"auto.?reply|no.?reply|noreply|google groups digest|"
    r"vacation|away from (my )?office)",
    re.IGNORECASE,
)

# Greeting / signature lines → skip when extracting task name
_SKIP_LINE = re.compile(
    r"^(mr\.|mrs\.|ms\.|dr\.|dear|hello|hi\b|hey|greetings|pledges?|brothers?|everyone|"
    r"apolog|sorry|understood|sincerely|best,|regards|thank|thanks|—|--|unsubscribe|"
    r"university of|berkeley|b\.a\.|b\.s\.|\(\d{3}\)|\*)",
    re.IGNORECASE,
)

# Sentence openers that are filler, not part of the task name
_NAME_FILLER = re.compile(
    r"^(please|pls|kindly|just|also|so|now|furthermore|additionally|"
    r"(you\s+)?(need|must|have|got)\s+to|i\s+(want|need)(\s+you)?\s+to|"
    r"make\s+sure(\s+to)?|go\s+ahead\s+and|remember\s+to)\s+",
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
    Two-layer extraction:
      Layer 1 — whole-email regex heuristics (original logic, kept intact).
      Layer 2 — sentence-level NLP keyword scoring to catch multiple
                assignments within a single email.
    Results are merged and deduplicated by normalized name.
    """
    if not cleaned_text.strip():
        return []

    is_reply = bool(subject and re.match(r"^(Re|Fwd|FW|RE|FWD)[\s:]", subject.strip()))
    clean_subject = re.sub(r"^(Re|Fwd|FW|RE|FWD)[\s:]+", "", subject or "", flags=re.IGNORECASE).strip() or None

    if clean_subject and _AUTO_SUBJECT.search(clean_subject):
        return []

    # ------------------------------------------------------------------
    # Layer 1 — existing whole-email regex logic (unchanged)
    # ------------------------------------------------------------------
    layer1 = _layer1_extract(cleaned_text, reference_date, is_reply, clean_subject)

    # ------------------------------------------------------------------
    # Layer 2 — NLP sentence-level scoring
    # ------------------------------------------------------------------
    layer2 = _layer2_nlp(cleaned_text, reference_date, clean_subject)

    # Merge: deduplicate by first 40 chars of lowercased name
    seen: set[str] = set()
    merged: list[ExtractionResult] = []

    for result in layer1 + layer2:
        if not result.assignment_name:
            continue
        key = re.sub(r"\W+", "", result.assignment_name.lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        merged.append(result)

    return merged


# ---------------------------------------------------------------------------
# Layer 1 — whole-email regex heuristics (original logic)
# ---------------------------------------------------------------------------

def _layer1_extract(
    cleaned_text: str,
    reference_date: Optional[datetime],
    is_reply: bool,
    clean_subject: Optional[str],
) -> list[ExtractionResult]:
    # Reply emails: extract when a due date is present
    if is_reply:
        if not clean_subject:
            return []
        due_at = extract_due_date(cleaned_text, reference=reference_date)
        if not due_at:
            return []
        event_type, confidence = _determine_event_type(cleaned_text)
        if event_type not in ("due_date_changed", "overdue", "punishment", "reminder"):
            event_type = "reminder"
        return [ExtractionResult(
            event_type=event_type,
            assignment_name=_censor_profanity(clean_subject),
            raw_excerpt=cleaned_text[:500],
            parsed_due_at=due_at,
            confidence=confidence,
        )]

    # Non-reply: every thread is an assignment
    due_at = extract_due_date(cleaned_text, reference=reference_date)

    _is_dailies = bool(clean_subject and re.match(r"^dailies?", clean_subject, re.IGNORECASE))
    if due_at is None and _is_dailies:
        m = re.match(r"^dailies?\s+(\d{1,2})/(\d{1,2})", clean_subject, re.IGNORECASE)
        if m:
            try:
                ref = reference_date or datetime.utcnow()
                due_at = ref.replace(month=int(m.group(1)), day=int(m.group(2)),
                                     hour=23, minute=59, second=0, microsecond=0)
            except (ValueError, AttributeError):
                pass

    event_type, confidence = _determine_event_type(cleaned_text)
    is_punishment = event_type == "punishment" or bool(
        clean_subject and re.search(r"\b(punishment|penalty|apolog|rizz|date pledge)\b",
                                    clean_subject, re.IGNORECASE)
    )
    if due_at is None and is_punishment and reference_date:
        due_at = parse_date("11:59 PM", reference_date=reference_date)

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
        parsed_due_at=due_at,
        confidence=confidence,
    )]


# ---------------------------------------------------------------------------
# Layer 2 — NLP sentence-level keyword scoring
# ---------------------------------------------------------------------------

def _layer2_nlp(
    text: str,
    reference_date: Optional[datetime],
    clean_subject: Optional[str],
) -> list[ExtractionResult]:
    """
    Split text into sentences. For each sentence, compute a keyword score:
      +3  time expression detected
      +2  action/imperative verb detected
      +1  assignment keyword (need, must, required, due…)

    Score >= 4 (time + action at minimum) → extract as a separate assignment.
    Name is derived from the sentence itself (stripped of due-date clause and
    filler words). Falls back to subject if name is too short.
    """
    # Split on sentence-ending punctuation or blank lines
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", text)

    results: list[ExtractionResult] = []
    seen_keys: set[str] = set()

    for sent in sentences:
        sent = sent.strip()
        # Minimum length and skip boilerplate lines
        if len(sent) < 12 or _SKIP_LINE.match(sent):
            continue

        # --- Score this sentence ---
        score = 0
        has_time = bool(
            _DUE_CONTEXT.search(sent) or _BY_TIME.search(sent) or
            _TONIGHT_TIME.search(sent) or _AT_TIME.search(sent) or
            _DAY_TIME.search(sent)
        )
        has_action = bool(_ACTION.search(sent))
        has_assignment_kw = bool(EVENT_PATTERNS["assigned"].search(sent))

        if has_time:
            score += 3
        if has_action:
            score += 2
        if has_assignment_kw:
            score += 1

        # Need at least time + action to qualify
        if score < 5:
            continue

        due_at = extract_due_date(sent, reference=reference_date)
        if not due_at:
            continue

        name = _sentence_to_name(sent, clean_subject)
        if not name:
            continue
        name = _censor_profanity(name)

        key = re.sub(r"\W+", "", name.lower())[:40]
        if key in seen_keys:
            continue
        seen_keys.add(key)

        event_type, confidence = _determine_event_type(sent)
        if event_type == "unknown":
            event_type = "assigned"
            confidence = 0.65 + (0.05 * min(score - 5, 3))  # scale with score

        results.append(ExtractionResult(
            event_type=event_type,
            assignment_name=name,
            raw_excerpt=sent[:300],
            parsed_due_at=due_at,
            confidence=round(confidence, 2),
        ))

    return results


def _sentence_to_name(sentence: str, subject: Optional[str] = None) -> Optional[str]:
    """
    Derive a concise task name from an assignment sentence.
    1. Strip leading filler ("You need to", "Please", etc.)
    2. Strip trailing due-date clause ("by Friday at midnight")
    3. Truncate to 80 chars
    """
    s = sentence.strip()

    # Remove leading filler phrases
    s = _NAME_FILLER.sub("", s).strip()

    # Split off trailing due-date clause
    s = re.split(
        r"\s+(?:by|due|before|no\s+later\s+than|until|till)\s+"
        r"(?:the\s+)?(?:end\s+of\s+)?(?:tonight|today|tomorrow|monday|tuesday|wednesday|"
        r"thursday|friday|saturday|sunday|\d{1,2}(?::\d{2})?\s*(?:am|pm)|eod|midnight)",
        s, maxsplit=1, flags=re.IGNORECASE
    )[0].strip()

    # Remove trailing punctuation
    s = s.rstrip(".,;:!? ")

    if len(s) < 5:
        return subject  # fall back to thread subject
    return s[:80]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def extract_due_date(text: str, reference: Optional[datetime] = None) -> Optional[datetime]:
    """Return the first parseable time/date expression from the text."""
    def _try(candidate: str) -> Optional[datetime]:
        candidate = _preprocess(candidate.strip()[:80])
        if not candidate:
            return None
        return parse_date(candidate, reference_date=reference)

    m = _DUE_CONTEXT.search(text)
    if m:
        result = _try(_trim(m.group(1)))
        if result:
            return result

    m = _BY_TIME.search(text)
    if m:
        result = _try(m.group(1))
        if result:
            return result

    m = _TONIGHT_TIME.search(text)
    if m:
        result = _try(m.group(1))
        if result:
            return result

    m = _AT_TIME.search(text)
    if m:
        result = _try(m.group(1))
        if result:
            return result

    for candidate in _DAY_TIME.findall(text):
        result = _try(candidate)
        if result:
            return result

    return None


def _extract_task_name(text: str) -> Optional[str]:
    """Return the first meaningful instructional line from the email body."""
    lines = [l.strip() for l in text.splitlines() if l.strip() and len(l.strip()) > 6]
    for line in lines[:10]:
        if _SKIP_LINE.match(line):
            continue
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
    return _PROFANITY.sub("****", text).strip()


def _preprocess(text: str) -> str:
    for pattern, replacement in _NORMALIZATIONS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _trim(candidate: str) -> str:
    candidate = re.split(
        r'\s+\b(?:with|if|and|but|so|or|unless|when|while|for|from|as)\b',
        candidate, maxsplit=1
    )[0]
    return candidate.strip()[:60]
