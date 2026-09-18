from datetime import date, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import CheckConstraint, Enum as SqlEnum, String, Text
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
