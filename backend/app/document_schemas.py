from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import DocumentType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    type: DocumentType
    filename: str
    storage_path: str | None
    external_reference: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def expose_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
