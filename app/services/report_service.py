from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Assignment
from app.utils.logging import get_logger

logger = get_logger(__name__)


def generate_nightly_report(db: Session) -> str:
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    next_72h = now + timedelta(hours=72)

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
        .filter(
            Assignment.status == "overdue",
        )
        .order_by(Assignment.due_at)
        .all()
    )

    lines = [
        "=" * 50,
        "Nightly Assignment Report",
        f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 50,
        "",
    ]

    lines.append("Newly Assigned (last 24h)")
    lines.append("-" * 30)
    if newly_assigned:
        for a in newly_assigned:
            lines.append(_format_assignment(a))
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Due Soon (next 72h)")
    lines.append("-" * 30)
    if due_soon:
        for a in due_soon:
            lines.append(_format_assignment(a))
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Overdue")
    lines.append("-" * 30)
    if overdue:
        for a in overdue:
            lines.append(_format_assignment(a))
    else:
        lines.append("  (none)")
    lines.append("")

    return "\n".join(lines)


def _format_assignment(a: Assignment) -> str:
    prefix = f"  {a.course}: " if a.course else "  "
    name = a.assignment_name or "(unknown)"
    if a.due_at:
        due_str = a.due_at.strftime("%b %-d at %-I:%M %p")
        return f"{prefix}{name} — due {due_str}"
    return f"{prefix}{name}"
