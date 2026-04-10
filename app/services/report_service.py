from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Assignment
from app.parser.resolver import refresh_statuses
from app.utils.logging import get_logger

logger = get_logger(__name__)


def generate_report_data(db: Session) -> dict:
    """Return structured report data (used by both JSON endpoint and text report)."""
    refresh_statuses(db)
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
        .filter(Assignment.status == "overdue")
        .order_by(Assignment.due_at)
        .all()
    )

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "newly_assigned": [_to_dict(a) for a in newly_assigned],
        "due_soon": [_to_dict(a) for a in due_soon],
        "overdue": [_to_dict(a) for a in overdue],
    }


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


def _to_dict(a: Assignment) -> dict:
    return {
        "name": a.assignment_name or "(unknown)",
        "course": a.course,
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "due_formatted": _fmt_due(a.due_at),
        "status": a.status,
    }


def _fmt_due(due_at) -> str | None:
    if not due_at:
        return None
    hour_12 = due_at.hour % 12 or 12
    ampm = "AM" if due_at.hour < 12 else "PM"
    return f"{due_at.strftime('%b')} {due_at.day} at {hour_12}:{due_at.strftime('%M')} {ampm}"
