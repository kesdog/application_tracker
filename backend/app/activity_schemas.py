from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class UndoRead(BaseModel):
    audit_id: str
    entity_type: str
    entity_id: str
    fields: list[str]
