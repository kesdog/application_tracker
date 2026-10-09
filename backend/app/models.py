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


class ContactType(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"


class DeadlineKind(str, Enum):
    APPLICATION_CLOSING = "APPLICATION_CLOSING"
    FIRST_ROUND = "FIRST_ROUND"


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
    intermediary: Mapped[str | None] = mapped_column(String(300))
    date_applied: Mapped[date]
    job_url: Mapped[str | None] = mapped_column(String(2048))
    email_reference: Mapped[str | None] = mapped_column(String(2048))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_name: Mapped[str | None] = mapped_column(String(300))
    deadline: Mapped[date | None]
    deadline_kind: Mapped[DeadlineKind | None] = mapped_column(
        SqlEnum(DeadlineKind, native_enum=False, create_constraint=True, name="deadline_kind")
    )
    contact_type: Mapped[ContactType] = mapped_column(
        SqlEnum(ContactType, native_enum=False, create_constraint=True, name="contact_type"),
        default=ContactType.EMAIL, server_default="EMAIL",
    )
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
    posting_http_status: Mapped[int | None]
    posting_final_url: Mapped[str | None] = mapped_column(String(2048))
    posting_check_method: Mapped[str | None] = mapped_column(String(32))
    posting_check_reason: Mapped[str | None] = mapped_column(String(500))
    posting_check_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    followup_delay_days: Mapped[int | None]
    max_followup_suggestions: Mapped[int | None]
    followup_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    followup_customization: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    followup_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
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
    PREPARED = "PREPARED"
    READY = "READY"
    PENDING = "PREPARED"  # Source compatibility for existing integrations.
    DRAFTED = "PREPARED"
    SENT = "SENT"
    CANCELLED = "CANCELLED"

    @classmethod
    def _missing_(cls, value):
        if value in ("PENDING", "DRAFTED"):
            return cls.PREPARED


class FollowUpChannel(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    BOTH = "BOTH"


class InterviewType(str, Enum):
    PHONE = "PHONE"
    HR = "HR"
    TECHNICAL = "TECHNICAL"
    ONSITE = "ONSITE"
    FINAL = "FINAL"
    OTHER = "OTHER"


class DocumentType(str, Enum):
    CV = "CV"
    COVER_LETTER = "COVER_LETTER"


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
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    channel: Mapped[FollowUpChannel] = mapped_column(SqlEnum(FollowUpChannel, native_enum=False, create_constraint=False, name="followup_channel"), default=FollowUpChannel.EMAIL, server_default="EMAIL")
    template_reference: Mapped[str | None] = mapped_column(String(2048))
    subject: Mapped[str] = mapped_column(Text, default="", server_default="")
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    template_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    variable_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    customization: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    approved_revision: Mapped[int | None]
    prepared_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
    snoozed_until: Mapped[datetime | None]
    archived_at: Mapped[datetime | None]
    parent_followup_id: Mapped[str | None] = mapped_column(String(36))


class GeneralSettings(Base):
    __tablename__ = "general_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class FollowUpNotice(Base):
    __tablename__ = "followup_notices"
    __table_args__ = (UniqueConstraint("followup_id", "schedule_key", name="followup_notice_unique"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    followup_id: Mapped[str] = mapped_column(ForeignKey("followups.id"), index=True)
    schedule_key: Mapped[str] = mapped_column(String(160))
    due_at: Mapped[datetime]
    state: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    read_at: Mapped[datetime | None]


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


class ApplicationDocument(Base):
    __tablename__ = "application_documents"
    __table_args__ = (
        CheckConstraint(
            "(storage_path IS NOT NULL AND external_reference IS NULL) OR "
            "(storage_path IS NULL AND external_reference IS NOT NULL)",
            name="document_upload_or_reference",
        ),
        CheckConstraint("length(trim(filename)) > 0", name="document_filename_required"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    type: Mapped[DocumentType] = mapped_column(
        SqlEnum(DocumentType, native_enum=False, create_constraint=True, name="document_type")
    )
    filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str | None] = mapped_column(String(2048))
    external_reference: Mapped[str | None] = mapped_column(String(2048))
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


class AgentCredential(Base):
    __tablename__ = "agent_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    permissions: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class AgentIdempotencyRecord(Base):
    """A bounded replay cache for successful agent create requests."""
    __tablename__ = "agent_idempotency_records"
    __table_args__ = (UniqueConstraint("token_hash", "operation", "idempotency_key", name="agent_idempotency_key_unique"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(index=True)


class InvalidationEvent(Base):
    __tablename__ = "invalidation_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(80))
    application_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class HumanSession(Base):
    __tablename__ = "human_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    credential_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(index=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)


class PushDevice(Base):
    __tablename__ = "push_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True)
    endpoint: Mapped[str] = mapped_column(Text)
    keys: Mapped[dict] = mapped_column(JSON)
    label: Mapped[str] = mapped_column(String(80))
    key_fingerprint: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class PushDelivery(Base):
    __tablename__ = "push_deliveries"
    __table_args__ = (UniqueConstraint("device_id", "batch_key", name="push_batch_unique"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    device_id: Mapped[str] = mapped_column(ForeignKey("push_devices.id"), index=True)
    batch_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="REMINDER")
    notice_ids: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    lease_until: Mapped[datetime | None]
    lease_token: Mapped[str | None] = mapped_column(String(36))
    last_status: Mapped[int | None]
    last_error: Mapped[str | None] = mapped_column(String(120))
    accepted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
