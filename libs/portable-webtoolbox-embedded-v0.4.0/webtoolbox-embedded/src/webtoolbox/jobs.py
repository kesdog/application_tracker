"""Lightweight in-process background handles; no broker, service, or polling loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JobHandle:
    """An awaitable result and observable state for one application-owned task."""

    id: str
    operation: str
    _task: asyncio.Task[dict[str, Any]] | None = field(default=None, repr=False)
    _state: str = "queued"
    _partial: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def status(self) -> str:
        return self._state

    @property
    def done(self) -> bool:
        # The handle can be polled by a request handler without awaiting.
        return self._task is not None and self._task.done()

    def cancel(self) -> bool:
        # Cancellation is cooperative; HTTP/browser requests may take time to unwind.
        return self._task.cancel() if self._task is not None else False

    async def result(self) -> dict[str, Any]:
        # Await the same task multiple times without repeating the network request.
        if self._task is None:
            raise RuntimeError("Job was not scheduled")
        return await self._task

    @property
    def partial(self) -> dict[str, Any] | None:
        # Host applications can persist last completed evidence after cancellation.
        return self._partial

    @property
    def error(self) -> str | None:
        # Inspect errors without propagating them during status polling.
        if not self.done or self._task is None or self._task.cancelled():
            return None
        error = self._task.exception()
        return str(error) if error is not None else None
