from datetime import datetime, timezone
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ActorType


class TimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    event_type: str
    actor_type: ActorType
    actor_reference: str | None
    summary: str
    metadata: dict[str, Any] = Field(validation_alias="event_metadata", serialization_alias="metadata")
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def expose_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class TimelineRead(BaseModel):
    events: list[TimelineEventRead]
    undo_available: bool


class TimelineEntryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    summary: str = Field(min_length=1, max_length=500)
    occurred_at: AwareDatetime


class TimelineEntryUpdate(TimelineEntryCreate):
    summary: str | None = Field(default=None, min_length=1, max_length=500)
    occurred_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if self.summary is None and self.occurred_at is None:
            raise ValueError("Provide a timeline summary or time")
        return self


class UndoRead(BaseModel):
    audit_id: str
    entity_type: str
    entity_id: str
    fields: list[str]
