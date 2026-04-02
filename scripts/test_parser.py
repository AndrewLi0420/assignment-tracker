"""
Quick smoke test for the email cleaner and assignment extractor.
Run: python scripts/test_parser.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.parser.email_cleaner import clean_new_message_text
from app.parser.assignment_extractor import extract_events

SAMPLES = [
    {
        "label": "New assignment release",
        "body": """
Homework 8 has been released. It is due Friday at 11:59 PM.
Please start early as it covers material from this week's lectures.

On Mon, Apr 1, 2026 at 10:00 AM Prof Smith <prof@school.edu> wrote:
> Here is last week's assignment.
> > It was due yesterday.
""",
    },
    {
        "label": "Overdue reminder",
        "body": """
Reminder: Project checkpoint is overdue.
Please submit as soon as possible to minimize late penalty.

--
Course Staff
""",
    },
    {
        "label": "Extension announcement",
        "body": """
Extension: Lab 4 deadline moved to Sunday night.
The new due date is Sunday, Apr 6 at 11:59 PM.

From: TA <ta@school.edu>
Date: Wed, Apr 2, 2026
""",
    },
    {
        "label": "Multi-assignment email",
        "body": """
CS 101 updates:

Homework 9 is now available. Due Apr 10 at 11:59 PM.
Quiz 3 will be held next Thursday in class.
Problem Set 4 deadline extended to Apr 12.
""",
    },
]


for sample in SAMPLES:
    print(f"\n{'='*60}")
    print(f"SAMPLE: {sample['label']}")
    print("-" * 40)

    cleaned = clean_new_message_text(sample["body"])
    print(f"CLEANED TEXT:\n{cleaned}\n")

    events = extract_events(cleaned)
    if events:
        for ev in events:
            print(f"  event_type:      {ev.event_type}")
            print(f"  assignment_name: {ev.assignment_name}")
            print(f"  course:          {ev.course}")
            print(f"  parsed_due_at:   {ev.parsed_due_at}")
            print(f"  confidence:      {ev.confidence:.2f}")
            print()
    else:
        print("  (no events extracted)")
