"""Read-only reminder scheduler. It never sends, closes, or edits records."""
import asyncio
import logging
from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from app import dashboard
from app.models import Application, PostingStatus, utc_now
from app.applications import get_application
from app.posting_checker import PostingChecker, render_with_playwright
from app import posting_service


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


class PostingCheckScheduler:
    """Low-frequency, bounded posting checks; no retry loop or lifecycle mutation."""
    def __init__(self, engine, settings, interval_seconds: int = 60):
        self.engine = engine; self.settings = settings; self.interval_seconds = interval_seconds
        self.stop = asyncio.Event(); self.last_run = utc_now()
        self.snapshot = {"checked_at": None, "checked": 0, "closed": 0, "unknown": 0}

    async def refresh(self) -> dict:
        if utc_now() - self.last_run < timedelta(hours=self.settings.posting_check_interval_hours):
            return self.snapshot
        with Session(self.engine) as session:
            candidates = [(item.id, item.job_url) for item in session.query(Application).filter_by(deleted_at=None).filter(Application.job_url.is_not(None)).filter(Application.posting_status != PostingStatus.CLOSED).all()]
        semaphore = asyncio.Semaphore(self.settings.posting_check_concurrency)
        checker = PostingChecker(browser_fallback=render_with_playwright if self.settings.posting_playwright_fallback else None)
        async def one(pair):
            async with semaphore:
                result = await checker.check(pair[1])
            def persist():
                with Session(self.engine) as session:
                    application = get_application(session, pair[0])
                    return posting_service.apply_result(session, application, result)
            return await asyncio.to_thread(persist)
        results = await asyncio.gather(*(one(pair) for pair in candidates), return_exceptions=True)
        checked = [item for item in results if not isinstance(item, Exception)]
        self.last_run = utc_now()
        self.snapshot = {"checked_at": self.last_run.replace(tzinfo=timezone.utc), "checked": len(checked), "closed": sum(item.status.value == "CLOSED" for item in checked), "unknown": sum(item.status.value == "UNKNOWN" for item in checked)}
        return self.snapshot

    async def run(self) -> None:
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                try: await self.refresh()
                except Exception: logging.getLogger(__name__).exception("Posting check refresh failed")
