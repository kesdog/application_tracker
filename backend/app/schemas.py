from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator

from app.models import ApplicationOutcome, ApplicationStatus

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


class ApplicationRead(ApplicationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ApplicationStatus
    outcome: ApplicationOutcome | None
