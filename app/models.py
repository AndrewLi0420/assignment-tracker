from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(Text, nullable=True)
    sender: Mapped[str] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    raw_body: Mapped[str] = mapped_column(Text, nullable=True)
    cleaned_body: Mapped[str] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class AssignmentEvent(Base):
    __tablename__ = "assignment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(255), index=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(50))  # assigned, due_date, due_date_changed, overdue, reminder, unknown
    course: Mapped[str] = mapped_column(Text, nullable=True)
    assignment_name: Mapped[str] = mapped_column(Text, nullable=True)
    raw_excerpt: Mapped[str] = mapped_column(Text, nullable=True)
    parsed_due_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    normalized_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    course: Mapped[str] = mapped_column(Text, nullable=True)
    assignment_name: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    due_at_estimated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, due_soon, overdue, unknown, completed
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    source_thread_id: Mapped[str] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
