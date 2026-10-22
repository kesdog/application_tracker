from datetime import datetime, timedelta, timezone

from app.session_manager import SessionManager, digest


class MemoryStore:
    def __init__(self):
        self.grants = {}
    def load(self, reference):
        return self.grants.get(reference)
    def replace(self, grant, old_reference, capacity):
        self.grants = {key: item for key, item in self.grants.items() if item.expires_at > grant.created_at and key != old_reference}
        for item in sorted(self.grants.values(), key=lambda item: item.created_at)[:max(0, len(self.grants) - capacity + 1)]:
            del self.grants[item.reference]
        self.grants[grant.reference] = grant
    def revoke(self, reference):
        self.grants.pop(reference, None)


def test_reusable_sessions_rotation_expiry_binding_and_shared_revocation_without_tracker():
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    binding = ['password-version-1']
    store = MemoryStore()
    first = SessionManager(store, lambda: binding[0], clock=lambda: now[0])
    second = SessionManager(store, lambda: binding[0], clock=lambda: now[0])
    old = first.create()
    assert second.valid(old) and old not in store.grants
    new = second.create(old)
    assert not first.valid(old) and first.valid_reference(digest(new))
    binding[0] = 'password-version-2'
    assert not first.valid(new)
    new = first.create()
    now[0] += timedelta(hours=8)
    assert not second.valid(new)
    new = first.create()
    second.revoke(new)
    assert not first.valid(new)
    assert not first.valid('x' * 101)


def test_capacity_is_enforced_by_injected_atomic_store():
    store = MemoryStore()
    manager = SessionManager(store, lambda: 'credential-version', capacity=2)
    tokens = [manager.create() for _ in range(3)]
    assert len(store.grants) == 2 and not manager.valid(tokens[0])
