import re
from typing import Optional


def normalize_assignment_name(name: str) -> str:
    """Produce a stable, lowercase key from an assignment name."""
    if not name:
        return ""

    text = name.lower()

    # Normalize shorthand forms
    text = re.sub(r"\bhw\b", "homework", text)
    text = re.sub(r"\bps\b", "problem set", text)
    text = re.sub(r"\bpset\b", "problem set", text)

    # Remove punctuation except digits
    text = re.sub(r"[^\w\s]", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def make_normalized_key(course: Optional[str], assignment_name: str) -> str:
    course_part = normalize_assignment_name(course or "")
    name_part = normalize_assignment_name(assignment_name)
    return f"{course_part}::{name_part}"
