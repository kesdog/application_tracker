"""Provider-independent, single-use OAuth browser sessions (memory only)."""
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar('T')


class OAuthSessionError(ValueError):
    pass


@dataclass
class PendingSession(Generic[T]):
    expires: float
    binding: str
    owner: str
    payload: T


class OAuthSessionManager(Generic[T]):
    """Bind a short-lived provider flow to its browser and initiating session."""
    def __init__(self, *, lifetime=600, capacity=20, clock=None):
        self.lifetime, self.capacity = lifetime, capacity
        self.clock = clock or time.monotonic
        self._pending: dict[str, PendingSession[T]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def create(self, binding: str, owner: str, payload: T) -> str:
        if not binding or not owner:
            raise OAuthSessionError('A browser and initiating session are required')
        state = secrets.token_urlsafe(32)
        with self._lock:
            now = self.clock()
            self._pending = {key: value for key, value in self._pending.items() if value.expires > now}
            if len(self._pending) >= self.capacity:
                raise OAuthSessionError('Too many pending connections. Wait ten minutes and try again.')
            self._pending[self._digest(state)] = PendingSession(now + self.lifetime, self._digest(binding), owner, payload)
        return state

    def consume(self, state: str, binding: str, owner: str | None, *, owner_validator: Callable[[str], bool] | None = None) -> T:
        """Allow a missing Strict cookie only with a trusted server-side owner check."""
        with self._lock:
            key = self._digest(state)
            pending = self._pending.get(key)
            if (not pending or pending.expires <= self.clock() or not binding
                    or not hmac.compare_digest(pending.binding, self._digest(binding))
                    or (owner is not None and not hmac.compare_digest(pending.owner, owner))
                    or (owner is None and owner_validator is None)
                    or (owner_validator is not None and not owner_validator(pending.owner))):
                raise OAuthSessionError('Sign-in expired or belongs to another browser/session. Start again from Settings.')
            del self._pending[key]
            return pending.payload

    def clear(self):
        with self._lock:
            self._pending.clear()
