"""Read-only reminder scheduler. It never sends, closes, or edits records."""
import asyncio
import logging
from datetime import timezone

from sqlalchemy.orm import Session

from app import dashboard
from app.models import utc_now


class ReminderScheduler:
    def __init__(self, engine, interval_seconds: int = 60):
        self.engine = engine
        self.interval_seconds = interval_seconds
        self.stop = asyncio.Event()
        self.snapshot: dict = {"checked_at": None, "due_followups": [], "overdue_followups": [], "due_tasks": [], "overdue_tasks": [], "upcoming_interviews": []}

    async def refresh(self) -> dict:
        def collect():
            with Session(self.engine) as session:
                return dashboard.dashboard(session)

        data = await asyncio.to_thread(collect)
        now = utc_now()
        groups = {name: [] for name in ("due_followups", "overdue_followups", "due_tasks", "overdue_tasks", "upcoming_interviews")}
        for item in data["upcoming"]:
            if item["kind"] == "INTERVIEW":
                group = "upcoming_interviews"
            else:
                prefix = "followups" if item["kind"] == "FOLLOWUP" else "tasks"
                group = f"{'overdue' if item['due_at'] < now else 'due'}_{prefix}"
            groups[group].append(item)
        self.snapshot = {"checked_at": now.replace(tzinfo=timezone.utc), **groups}
        return self.snapshot

    async def run(self) -> None:
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                try:
                    await self.refresh()
                except Exception:
                    logging.getLogger(__name__).exception("Reminder refresh failed")
