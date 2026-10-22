"""Reusable opaque sessions. Standard library only; inject persistent storage.

Copy this module into another project or inject its SessionStore implementation.
HTTP cookies, CSRF policy, passwords, ORM models and provider OAuth are host
adapters. A store must replace/prune/insert atomically and persist only digests.
"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True, repr=False)
class SessionGrant:
    reference: str
    binding: str
    created_at: datetime
    expires_at: datetime


class SessionStore(Protocol):
    def load(self, reference: str) -> SessionGrant | None: ...
    def replace(self, grant: SessionGrant, old_reference: str | None, capacity: int) -> None: ...
    def revoke(self, reference: str) -> None: ...


class SessionManager:
    def __init__(self, store: SessionStore, credential_binding: Callable[[], str], *,
                 lifetime=timedelta(hours=8), capacity=20, clock=None):
        if lifetime <= timedelta(0) or capacity < 1:
            raise ValueError('Session lifetime and capacity must be positive')
        self.store, self.binding = store, credential_binding
        self.lifetime, self.capacity = lifetime, capacity
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def valid_reference(self, reference: str | None) -> bool:
        if not reference or len(reference) != 64:
            return False
        grant = self.store.load(reference)
        return bool(grant and grant.expires_at > self.clock() and hmac.compare_digest(grant.binding, self.binding()))

    def valid(self, token: str | None) -> bool:
        return bool(token and len(token) <= 100 and self.valid_reference(digest(token)))

    def create(self, old_token: str | None = None) -> str:
        token, now = secrets.token_urlsafe(32), self.clock()
        grant = SessionGrant(digest(token), self.binding(), now, now + self.lifetime)
        self.store.replace(grant, digest(old_token) if old_token else None, self.capacity)
        return token

    def revoke(self, token: str | None) -> None:
        if token:
            self.store.revoke(digest(token))
