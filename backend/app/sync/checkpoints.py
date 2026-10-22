"""Bounded checkpoint files; each remains an ordinary immutable v1 batch.

History is retained and GC stays disabled. Readers already stage missing causal
parents safely, so checkpoint parts can arrive independently and in any order.
"""
from uuid import uuid4

from app.sync.crypto import canonical
from app.sync.schemas import Batch

MAX_EVENTS = 1000
MAX_EVENT_BYTES = 1024 * 1024


def checkpoint_batches(workspace_id, device_id, payloads, acknowledgments):
    group, size, emitted = [], 0, False
    for payload in payloads:
        length = len(canonical(payload))
        if group and (len(group) >= MAX_EVENTS or size + length > MAX_EVENT_BYTES):
            yield Batch(workspace_id=workspace_id, device_id=device_id, batch_id=uuid4(), kind='checkpoint',
                mutations=group, acknowledgments=acknowledgments)
            group, size, emitted = [], 0, True
        group.append(payload)
        size += length
    if group or not emitted:
        yield Batch(workspace_id=workspace_id, device_id=device_id, batch_id=uuid4(), kind='checkpoint',
            mutations=group, acknowledgments=acknowledgments)
