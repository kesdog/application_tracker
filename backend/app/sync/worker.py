"""Desktop foreground worker: durable outbox debounce and bounded polling."""
import asyncio
import time
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import utc_now
from app.sync.models import SyncOutbox, SyncWorkspace


class SyncWorker:
    def __init__(self, sync, *, clock=time.monotonic):
        self.sync, self.clock = sync, clock
        self.stop = asyncio.Event()
        self.last_poll = -float('inf')
        self.last_pending, self.changed_at = 0, 0.0

    def due(self):
        with Session(self.sync.engine) as session:
            workspace = session.get(SyncWorkspace, 1)
            if not workspace or workspace.restored or (workspace.retry_at and workspace.retry_at > utc_now()):
                return False
            pending = session.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.uploaded.is_(False))) or 0
        now = self.clock()
        if pending != self.last_pending:
            self.last_pending, self.changed_at = pending, now
        return (pending > 0 and now - self.changed_at >= 3) or now - self.last_poll >= (120 if pending else 300)

    async def run(self):
        while not self.stop.is_set():
            try:
                if await asyncio.to_thread(self.due):
                    await asyncio.to_thread(self.sync.run)
                    self.last_poll = self.clock()
            except Exception:
                # A transient DB lease or credential-store failure must not kill
                # the desktop worker. Do not log exception bodies/secrets.
                logging.getLogger(__name__).warning('Sync worker check failed; durable pending edits will be retried.')
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=2)
            except TimeoutError:
                pass
