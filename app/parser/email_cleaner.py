import re
from typing import List


# Patterns that mark the start of a quoted reply block
QUOTE_HEADER_PATTERNS = [
    re.compile(r"^On\s.{5,100}wrote:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^From:\s", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Original Message\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Forwarded message\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^_{3,}", re.MULTILINE),
    re.compile(r"^Sent from my \w+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^--\s*$", re.MULTILINE),  # email signature marker
    re.compile(r"^\[image:.*?\]", re.IGNORECASE | re.MULTILINE),
]


def clean_new_message_text(raw_body: str) -> str:
    """
    Strip quoted/old content from an email body, returning only the new text
    the sender added in this specific message.
    """
    if not raw_body:
        return ""

    lines = raw_body.splitlines()
    cleaned_lines: List[str] = []
    quote_started = False

    for line in lines:
        # Lines starting with > are quoted
        if line.startswith(">"):
            quote_started = True
            continue

        # Check if this line is a quote header
        if not quote_started:
            is_quote_header = any(p.match(line) for p in QUOTE_HEADER_PATTERNS)
            if is_quote_header:
                quote_started = True
                continue

        if not quote_started:
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
