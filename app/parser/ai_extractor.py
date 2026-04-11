"""
Use Claude to extract individual assignments from email bodies.
Falls back to regex extractor if the API key is missing or the call fails.
"""
import json
import os
from datetime import datetime
from typing import Optional

from app.parser.assignment_extractor import (
    ExtractionResult,
    extract_events as regex_extract_events,
    _censor_profanity,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SYSTEM = """\
You parse emails from a college fraternity pledge program and extract every distinct task or assignment mentioned.
Return ONLY a JSON array. Each element has:
  "name"    – short clear task name (under 60 chars, no profanity)
  "due"     – due date/time as a natural language string if stated, otherwise null
  "type"    – one of: assigned, punishment, reminder, overdue, due_date_changed

Rules:
- Extract EVERY separate task (there can be multiple per email).
- If the email is just a submission/response with no new task, return [].
- Strip profanity from names.
- Do not invent tasks not implied by the email.
- Be concise: "1000 pushups video" not "send a video of you doing 1000 pushups".
"""


def extract_events(
    cleaned_text: str,
    reference_date: Optional[datetime] = None,
    subject: Optional[str] = None,
) -> list[ExtractionResult]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return regex_extract_events(cleaned_text, reference_date=reference_date, subject=subject)

    try:
        return _ai_extract(cleaned_text, reference_date=reference_date, subject=subject, api_key=api_key)
    except Exception as e:
        logger.warning("AI extraction failed (%s), falling back to regex", e)
        return regex_extract_events(cleaned_text, reference_date=reference_date, subject=subject)


def _ai_extract(
    cleaned_text: str,
    reference_date: Optional[datetime],
    subject: Optional[str],
    api_key: str,
) -> list[ExtractionResult]:
    import anthropic
    from app.utils.dates import parse_date

    # Skip automated / empty emails early
    if not cleaned_text.strip():
        return []

    clean_subject = subject or ""
    import re
    if re.match(r"^(Re|Fwd|FW|RE|FWD)[\s:]", clean_subject.strip()):
        clean_subject = re.sub(r"^(Re|Fwd|FW|RE|FWD)[\s:]+", "", clean_subject, flags=re.IGNORECASE).strip()

    ref_str = reference_date.strftime("%A %B %d %Y %I:%M %p") if reference_date else datetime.utcnow().strftime("%A %B %d %Y %I:%M %p")

    user_msg = f"""Thread subject: {clean_subject or '(none)'}
Email received: {ref_str}
---
{cleaned_text[:1500]}"""

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = resp.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    items = json.loads(raw)
    if not isinstance(items, list):
        return []

    results = []
    for item in items:
        name = _censor_profanity((item.get("name") or "").strip())
        if not name or len(name) < 3:
            continue

        due_str = item.get("due")
        parsed_due = None
        if due_str:
            try:
                parsed_due = parse_date(str(due_str), reference_date=reference_date)
            except Exception:
                pass

        event_type = item.get("type", "assigned")
        if event_type not in ("assigned", "punishment", "reminder", "overdue", "due_date_changed"):
            event_type = "assigned"

        results.append(ExtractionResult(
            event_type=event_type,
            assignment_name=name,
            raw_excerpt=cleaned_text[:300],
            parsed_due_at=parsed_due,
            confidence=0.85,
        ))

    return results
