from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Enum as SqlEnum, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ApplicationStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    INTERVIEW = "INTERVIEW"
    CLOSED = "CLOSED"


class ApplicationOutcome(str, Enum):
    SUCCESSFUL = "SUCCESSFUL"
    UNSUCCESSFUL = "UNSUCCESSFUL"
    WITHDRAWN = "WITHDRAWN"
    JOB_CANCELLED = "JOB_CANCELLED"
    GHOSTED = "GHOSTED"


class PostingStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    LIVE = "LIVE"
    CLOSED = "CLOSED"


class ActorType(str, Enum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("length(trim(coalesce(job_url, ''))) > 0 OR length(trim(coalesce(email_reference, ''))) > 0", name="application_source_required"),
        CheckConstraint("length(trim(job_title)) > 0 AND length(trim(company)) > 0", name="application_title_company_required"),
        CheckConstraint("outcome IS NULL OR status = 'CLOSED'", name="application_outcome_requires_closed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    date_applied: Mapped[date]
    job_url: Mapped[str | None] = mapped_column(String(2048))
    email_reference: Mapped[str | None] = mapped_column(String(2048))
    location: Mapped[str | None] = mapped_column(String(300))
    remote_policy: Mapped[str | None] = mapped_column(String(300))
    contract_type: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(
        SqlEnum(ApplicationStatus, native_enum=False, create_constraint=True, name="application_status"),
        default=ApplicationStatus.SUBMITTED, server_default="SUBMITTED",
    )
    outcome: Mapped[ApplicationOutcome | None] = mapped_column(
        SqlEnum(ApplicationOutcome, native_enum=False, create_constraint=True, name="application_outcome")
    )
    posting_status: Mapped[PostingStatus] = mapped_column(
        SqlEnum(PostingStatus, native_enum=False, create_constraint=True, name="posting_status"),
        default=PostingStatus.UNKNOWN, server_default="UNKNOWN",
    )
    # SQLite stores naive datetimes; this column always contains UTC.
    posting_last_checked_at: Mapped[datetime | None]
    followup_delay_days: Mapped[int | None]
    max_followup_suggestions: Mapped[int | None]
    deleted_at: Mapped[datetime | None]


class NoteType(str, Enum):
    GENERAL = "GENERAL"
    ASSESSMENT = "ASSESSMENT"
    EMAIL_DRAFT = "EMAIL_DRAFT"
    INTERVIEW = "INTERVIEW"
    AGENT = "AGENT"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class FollowUpStatus(str, Enum):
    PENDING = "PENDING"
    DRAFTED = "DRAFTED"
    SENT = "SENT"
    CANCELLED = "CANCELLED"


class InterviewType(str, Enum):
    PHONE = "PHONE"
    HR = "HR"
    TECHNICAL = "TECHNICAL"
    ONSITE = "ONSITE"
    FINAL = "FINAL"
    OTHER = "OTHER"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (CheckConstraint("length(trim(content)) > 0", name="note_content_required"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    type: Mapped[NoteType] = mapped_column(SqlEnum(NoteType, native_enum=False, create_constraint=True, name="note_type"), default=NoteType.GENERAL)
    created_by: Mapped[str] = mapped_column(String(300), default="HUMAN")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="task_title_required"),
        CheckConstraint("(status = 'COMPLETED' AND completed_at IS NOT NULL) OR (status != 'COMPLETED' AND completed_at IS NULL)", name="task_completion_consistent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus, native_enum=False, create_constraint=True, name="task_status"), default=TaskStatus.PENDING)


class FollowUp(Base):
    __tablename__ = "followups"
    __table_args__ = (
        UniqueConstraint("application_id", "sequence_number", name="followup_sequence_unique"),
        CheckConstraint("sequence_number > 0", name="followup_sequence_positive"),
        CheckConstraint("(status = 'SENT' AND sent_at IS NOT NULL) OR (status != 'SENT' AND sent_at IS NULL)", name="followup_sent_consistent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    sequence_number: Mapped[int]
    due_at: Mapped[datetime]
    sent_at: Mapped[datetime | None]
    status: Mapped[FollowUpStatus] = mapped_column(SqlEnum(FollowUpStatus, native_enum=False, create_constraint=True, name="followup_status"), default=FollowUpStatus.PENDING)
    template_reference: Mapped[str | None] = mapped_column(String(2048))


class Interview(Base):
    __tablename__ = "interviews"
    __table_args__ = (
        CheckConstraint("duration IS NULL OR duration > 0", name="interview_duration_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    type: Mapped[InterviewType] = mapped_column(SqlEnum(InterviewType, native_enum=False, create_constraint=True, name="interview_type"))
    scheduled_at: Mapped[datetime] = mapped_column(index=True)
    duration: Mapped[int | None]
    location: Mapped[str | None] = mapped_column(String(300))
    meeting_url: Mapped[str | None] = mapped_column(String(2048))
    interviewer: Mapped[str | None] = mapped_column(String(300))
    email_reference: Mapped[str | None] = mapped_column(String(2048))
    notes: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_type: Mapped[ActorType] = mapped_column(SqlEnum(ActorType, native_enum=False, create_constraint=True, name="actor_type"))
    actor_reference: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(String(500))
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(50))
    field: Mapped[str | None] = mapped_column(String(100))
    previous_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    actor_type: Mapped[ActorType] = mapped_column(SqlEnum(ActorType, native_enum=False, create_constraint=True, name="audit_actor_type"))
    actor_reference: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    reversible: Mapped[bool] = mapped_column(Boolean, default=False)
    undone_at: Mapped[datetime | None]
