"""Stable, compact payloads for provider-neutral agent operations."""
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from app.activity_schemas import TimelineEventRead
from app.document_schemas import DocumentRead
from app.interview_schemas import InterviewRead
from app.schemas import ApplicationCreate, ApplicationRead, ApplicationFilters, ApplicationUpdate
from app.contract_types import ContractCategory, canonical_contract
from app.work_schemas import FollowUpRead, NoteRead, TaskRead


AgentContract = Annotated[ContractCategory | None, BeforeValidator(canonical_contract)]
CONTRACT_HINT = "CDI, CDD, PART_TIME or APPRENTICESHIP_INTERNSHIP. Recognized French/English aliases normalize to a category. Unknown/ambiguous contracts must be null."


def iso_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-":
        return date.fromisoformat(value)
    raise ValueError("Use an ISO calendar date in YYYY-MM-DD format from the original email evidence")


AgentDate = Annotated[date, BeforeValidator(iso_date)]


class AgentApplicationCreate(ApplicationCreate):
    contract_type: AgentContract = Field(default=None, description=CONTRACT_HINT)
    date_applied: AgentDate = Field(description="Verified applied date, otherwise the original confirmation email date; YYYY-MM-DD.")


class AgentApplicationUpdate(ApplicationUpdate):
    contract_type: AgentContract = Field(default=None, description=CONTRACT_HINT)
    date_applied: AgentDate | None = None


class AgentApplicationFilters(ApplicationFilters):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    contract_type: AgentContract = Field(default=None, description=CONTRACT_HINT)
    date_from: AgentDate | None = None
    date_to: AgentDate | None = None

    @model_validator(mode="after")
    def date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class AgentListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: AgentApplicationFilters = Field(default_factory=AgentApplicationFilters)
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
    intermediary: str | None = None
    date_applied: date
    status: str
    outcome: str | None
    location: str | None
    source: str | None
    contract_type: str | None
    job_url: str | None
    email_reference: str | None
    next_due_item: AgentDueItem | None = None
    has_overdue_followup: bool = False
    attention_state: Literal["NORMAL", "OVERDUE", "CLOSED"] = "NORMAL"


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
