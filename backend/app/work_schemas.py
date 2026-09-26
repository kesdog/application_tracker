from datetime import datetime, timezone
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import FollowUpChannel, FollowUpStatus, NoteType, TaskStatus

Content = Annotated[str, Field(min_length=1)]
Title = Annotated[str, Field(min_length=1, max_length=300)]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("due_at", mode="after", check_fields=False)
    @classmethod
    def store_utc(cls, value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None

    @model_validator(mode="after")
    def reject_required_null(self):
        for name in ("content", "type", "title", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class NoteCreate(Input):
    content: Content
    type: NoteType = NoteType.GENERAL


class NoteUpdate(Input):
    content: Content | None = None
    type: NoteType | None = None


class TaskCreate(Input):
    title: Title
    description: str | None = None
    due_at: AwareDatetime | None = None


class TaskUpdate(Input):
    title: Title | None = None
    description: str | None = None
    due_at: AwareDatetime | None = None
    status: TaskStatus | None = None


class FollowUpCreate(Input):
    due_at: AwareDatetime | None = None
    template_reference: str | None = Field(default=None, max_length=2048)
    channel: FollowUpChannel = FollowUpChannel.EMAIL


class FollowUpUpdate(Input):
    due_at: AwareDatetime | None = None
    template_reference: str | None = Field(default=None, max_length=2048)
    status: FollowUpStatus | None = None
    channel: FollowUpChannel | None = None

    @model_validator(mode="after")
    def due_date_required(self):
        if "due_at" in self.model_fields_set and self.due_at is None:
            raise ValueError("due_at cannot be null")
        if "channel" in self.model_fields_set and self.channel is None:
            raise ValueError("channel cannot be null")
        return self


class Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    application_id: str

    @field_validator("created_at", "updated_at", "due_at", "completed_at", "sent_at", check_fields=False)
    @classmethod
    def expose_utc(cls, value):
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


class NoteRead(Read):
    content: str
    type: NoteType
    created_by: str
    created_at: datetime
    updated_at: datetime


class TaskRead(Read):
    title: str
    description: str | None
    due_at: datetime | None
    completed_at: datetime | None
    status: TaskStatus


class FollowUpRead(Read):
    sequence_number: int
    due_at: datetime
    sent_at: datetime | None
    status: FollowUpStatus
    is_automatic: bool
    channel: FollowUpChannel
    template_reference: str | None


class WorkRead(BaseModel):
    notes: list[NoteRead]
    tasks: list[TaskRead]
    followups: list[FollowUpRead]
    followup_delay_days: int
    max_followup_suggestions: int
