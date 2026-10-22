"""Durable merge work; queued in the same transaction as every new mutation."""
from sqlalchemy.dialects.sqlite import insert

from app.sync.models import SyncDirty


def chunks(values, size=200):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def mark_dirty(session, keys):
    values = [{'key': key} for key in sorted(set(keys))]
    for group in chunks(values):
        session.connection().execute(insert(SyncDirty).values(group).on_conflict_do_nothing())
