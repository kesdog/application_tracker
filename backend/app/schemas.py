from datetime import date, datetime, timezone
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator

from app.models import ApplicationOutcome, ApplicationStatus, PostingStatus

ShortText = Annotated[str, Field(min_length=1, max_length=300)]
Reference = Annotated[str, Field(max_length=2048)]


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    job_title: ShortText
    company: ShortText
    date_applied: date
    job_url: Reference | None = None
    email_reference: Reference | None = None
    location: ShortText | None = None
    remote_policy: ShortText | None = None
    contract_type: ShortText | None = None
    source: ShortText | None = None
    description: str | None = None
    requirements: str | None = None
    followup_delay_days: int | None = Field(default=None, ge=0, le=3650)
    max_followup_suggestions: int | None = Field(default=None, ge=0, le=100)

    @field_validator("followup_delay_days", "max_followup_suggestions", mode="before")
    @classmethod
    def blank_override(cls, value):
        return None if value == "" else value

    @field_validator("job_url", "email_reference", "location", "remote_policy", "contract_type", "source", "description", "requirements", mode="before")
    @classmethod
    def empty_to_none(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("job_url")
    @classmethod
    def validate_job_url(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value

    @model_validator(mode="after")
    def require_source(self) -> Self:
        if not self.job_url and not self.email_reference:
            raise ValueError("Provide a job URL or an email reference")
        return self


class DuplicateMatch(BaseModel):
    id: str
    job_title: str
    company: str
    date_applied: date
    reasons: list[str]


class ApplicationFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    q: str | None = None
    status: ApplicationStatus | None = None
    outcome: ApplicationOutcome | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    contract_type: str | None = None
    source: str | None = None
    remote_policy: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    document_filename: str | None = None

    @field_validator("q", "company", "title", "location", "contract_type", "source", "remote_policy", "document_filename", mode="before")
    @classmethod
    def blank_filter(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value


class ApplicationRead(ApplicationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ApplicationStatus
    outcome: ApplicationOutcome | None
    posting_status: PostingStatus
    posting_last_checked_at: datetime | None
    deleted_at: datetime | None
    duplicate_warnings: list[DuplicateMatch] = Field(default_factory=list)

    @field_validator("posting_last_checked_at", "deleted_at")
    @classmethod
    def expose_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class ApplicationUpdate(ApplicationCreate):
    job_title: ShortText | None = None
    company: ShortText | None = None
    date_applied: date | None = None
    status: ApplicationStatus | None = None
    outcome: ApplicationOutcome | None = None
    posting_status: PostingStatus | None = None
    posting_last_checked_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_source(self) -> Self:
        # PATCH is partial: the service validates sources against the stored record.
        for name in ("job_title", "company", "date_applied", "status", "posting_status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
