"""Stable, compact payloads for provider-neutral agent operations."""
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.activity_schemas import TimelineEventRead
from app.document_schemas import DocumentRead
from app.interview_schemas import InterviewRead
from app.schemas import ApplicationRead, ApplicationFilters
from app.work_schemas import FollowUpRead, NoteRead, TaskRead


class AgentListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: ApplicationFilters = Field(default_factory=ApplicationFilters)
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=256)


class AgentDueItem(BaseModel):
    id: str
    kind: Literal["TASK", "FOLLOWUP", "INTERVIEW"]
    title: str
    due_at: datetime
    status: str

    @field_validator("due_at")
    @classmethod
    def expose_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class CompactApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_title: str
    company: str
    date_applied: date
    status: str
    outcome: str | None
    location: str | None
    source: str | None
    job_url: str | None
    email_reference: str | None
    next_due_item: AgentDueItem | None = None


class CompactApplicationPage(BaseModel):
    items: list[CompactApplicationRead]
    next_cursor: str | None


class ApplicationContextRead(BaseModel):
    """Everything an agent normally needs before deciding on a next action."""

    application: ApplicationRead
    notes: list[NoteRead]
    tasks: list[TaskRead]
    followups: list[FollowUpRead]
    interviews: list[InterviewRead]
    documents: list[DocumentRead]
    recent_timeline: list[TimelineEventRead]
    next_action: AgentDueItem | None
