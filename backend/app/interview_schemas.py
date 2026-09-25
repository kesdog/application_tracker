from datetime import datetime, timezone
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator

from app.models import InterviewType
from app.schemas import ApplicationRead
from app.work_schemas import NoteRead, TaskRead

ShortText = Annotated[str, Field(min_length=1, max_length=300)]
Reference = Annotated[str, Field(max_length=2048)]


class InterviewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: InterviewType
    scheduled_at: AwareDatetime
    duration: int | None = Field(default=None, ge=1, le=1440)
    location: ShortText | None = None
    meeting_url: Reference | None = None
    interviewer: ShortText | None = None
    email_reference: Reference | None = None
    notes: str | None = None
    result: str | None = None

    @field_validator("location", "meeting_url", "interviewer", "email_reference", "notes", "result", mode="before")
    @classmethod
    def empty_to_none(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("meeting_url")
    @classmethod
    def validate_meeting_url(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value

    @field_validator("scheduled_at")
    @classmethod
    def store_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value is not None else None


class InterviewCreate(InterviewInput):
    pass


class InterviewUpdate(InterviewInput):
    type: InterviewType | None = None
    scheduled_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for name in ("type", "scheduled_at"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    type: InterviewType
    scheduled_at: datetime
    duration: int | None
    location: str | None
    meeting_url: str | None
    interviewer: str | None
    email_reference: str | None
    notes: str | None
    result: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("scheduled_at", "created_at", "updated_at")
    @classmethod
    def expose_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ApplicationSummary(BaseModel):
    id: str
    job_title: str
    company: str


class InterviewListItem(InterviewRead):
    application: ApplicationSummary


class TaskListItem(TaskRead):
    application: ApplicationSummary


class InterviewContext(BaseModel):
    interview: InterviewRead
    application: ApplicationRead
    notes: list[NoteRead]
    tasks: list[TaskRead]
    documents: list[dict[str, str | None]]
