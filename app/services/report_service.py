from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Assignment, EmailMessage
from app.parser.resolver import refresh_statuses
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _thread_subject_map(db: Session) -> dict:
    """Return {gmail_thread_id: subject} for all known threads."""
    rows = db.query(EmailMessage.gmail_thread_id, EmailMessage.subject).all()
    result = {}
    for thread_id, subject in rows:
        if thread_id and thread_id not in result and subject:
            result[thread_id] = subject
    return result


def generate_report_data(db: Session) -> dict:
    """Return structured report data (used by both JSON endpoint and text report)."""
    refresh_statuses(db)
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    next_72h = now + timedelta(hours=72)

    thread_subjects = _thread_subject_map(db)

    newly_assigned = (
        db.query(Assignment)
        .filter(Assignment.first_seen_at >= last_24h)
        .order_by(Assignment.first_seen_at)
        .all()
    )
    due_soon = (
        db.query(Assignment)
        .filter(
            Assignment.due_at != None,
            Assignment.due_at > now,
            Assignment.due_at <= next_72h,
            Assignment.status != "overdue",
        )
        .order_by(Assignment.due_at)
        .all()
    )
    overdue = (
        db.query(Assignment)
        .filter(Assignment.status == "overdue")
        .order_by(Assignment.due_at)
        .all()
    )
    # Assignments with no due date or due date beyond 72h (still active)
    upcoming = (
        db.query(Assignment)
        .filter(
            Assignment.status.in_(["active", "unknown"]),
            ~Assignment.id.in_([a.id for a in due_soon]),
        )
        .order_by(Assignment.due_at.asc().nulls_last(), Assignment.first_seen_at.desc())
        .all()
    )

    def to_dict(a):
        return _to_dict(a, thread_subjects)

    # Build thread-grouped view across all active + overdue assignments
    all_assignments = due_soon + overdue + upcoming
    threads = _group_by_thread(all_assignments, thread_subjects)

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "newly_assigned": [to_dict(a) for a in newly_assigned],
        "due_soon": [to_dict(a) for a in due_soon],
        "overdue": [to_dict(a) for a in overdue],
        "upcoming": [to_dict(a) for a in upcoming],
        "threads": threads,
    }


def _group_by_thread(assignments: list, thread_subjects: dict) -> list:
    """Group assignments by source thread, returning ordered list of thread buckets."""
    seen_order = []
    groups: dict = {}
    for a in assignments:
        tid = a.source_thread_id or "__unknown__"
        if tid not in groups:
            seen_order.append(tid)
            groups[tid] = {
                "thread_id": tid,
                "thread_subject": _clean_subject(thread_subjects.get(tid, "")),
                "assignments": [],
            }
        groups[tid]["assignments"].append(_to_dict(a, thread_subjects))

    return [groups[tid] for tid in seen_order]


def _clean_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes and brackets for a clean thread title."""
    import re
    if not subject:
        return "(No subject)"
    s = re.sub(r"^(Re|Fwd|FW|RE|FWD)[\s:]+", "", subject.strip(), flags=re.IGNORECASE).strip()
    # Strip common list-name brackets like [Alpha Eta]
    s = re.sub(r"^\[[^\]]+\]\s*", "", s).strip()
    return s or "(No subject)"


def generate_nightly_report(db: Session) -> str:
    data = generate_report_data(db)

    lines = [
        "=" * 50,
        "Nightly Assignment Report",
        f"Generated: {data['generated_at']}",
        "=" * 50,
        "",
    ]

    def add_section(title, items):
        lines.append(title)
        lines.append("-" * 30)
        if items:
            for a in items:
                prefix = f"  {a['course']}: " if a["course"] else "  "
                due_str = f" — due {a['due_formatted']}" if a["due_formatted"] else ""
                lines.append(f"{prefix}{a['name']}{due_str}")
        else:
            lines.append("  (none)")
        lines.append("")

    add_section("Newly Assigned (last 24h)", data["newly_assigned"])
    add_section("Due Soon (next 72h)", data["due_soon"])
    add_section("Overdue", data["overdue"])

    return "\n".join(lines)


def _to_dict(a: Assignment, thread_subjects: dict = None) -> dict:
    tid = a.source_thread_id or "__unknown__"
    subj = ""
    if thread_subjects and tid in thread_subjects:
        subj = _clean_subject(thread_subjects[tid])
    return {
        "name": a.assignment_name or "(unknown)",
        "course": a.course,
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "due_formatted": _fmt_due(a.due_at),
        "status": a.status,
        "due_at_estimated": bool(a.due_at_estimated),
        "thread_id": tid,
        "thread_subject": subj,
    }


def _fmt_due(due_at) -> str | None:
    if not due_at:
        return None
    hour_12 = due_at.hour % 12 or 12
    ampm = "AM" if due_at.hour < 12 else "PM"
    return f"{due_at.strftime('%b')} {due_at.day} at {hour_12}:{due_at.strftime('%M')} {ampm}"
