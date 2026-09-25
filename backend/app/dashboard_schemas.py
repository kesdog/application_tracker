from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_validator


class DashboardCounts(BaseModel):
    active_applications: int
    followups_due: int
    followups_overdue: int
    tasks_due: int
    tasks_overdue: int
    upcoming_interviews: int


class DashboardApplication(BaseModel):
    id: str
    job_title: str
    company: str


class UpcomingItem(BaseModel):
    id: str
    kind: Literal["TASK", "FOLLOWUP", "INTERVIEW"]
    title: str
    due_at: datetime
    status: str
    application: DashboardApplication

    @field_validator("due_at")
    @classmethod
    def expose_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class RecentActivity(BaseModel):
    id: str
    event_type: str
    summary: str
    actor_type: str
    created_at: datetime
    application: DashboardApplication

    @field_validator("created_at")
    @classmethod
    def expose_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class DashboardRead(BaseModel):
    counts: DashboardCounts
    upcoming: list[UpcomingItem]
    due_followups: list[UpcomingItem]
    overdue_followups: list[UpcomingItem]
    recent_activity: list[RecentActivity]
