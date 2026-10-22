"""Transaction-local journaling shared by REST, MCP, undo and background jobs."""
from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Application, Task, Interview, FollowUp
from app.sync.models import SyncMutation, SyncOutbox, SyncRecord, SyncWorkspace
from app.sync.schemas import Mutation, STATES
from app.sync.queue import mark_dirty

DOMAIN = {Application: 'application', Task: 'task', Interview: 'interview', FollowUp: 'followup'}


def record_key(entity, entity_id):
    return entity + ':' + entity_id


def json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if value.tzinfo is None else value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    if isinstance(value, date):
        return value.isoformat()
    return value


def projection(item) -> dict:
    entity = DOMAIN[type(item)]
    values = {field: json_value(getattr(item, field)) for field in STATES[entity].model_fields if field != 'deleted'}
    values['deleted'] = bool(getattr(item, 'deleted_at', None))
    return STATES[entity].model_validate(values).model_dump(mode='json')


def append_local(session, workspace, entity, entity_id, state, *, actor='SYSTEM', resolution=False, deleted=False, enqueue=True):
    key = record_key(entity, entity_id)
    record = session.get(SyncRecord, key)
    previous = record.state if record else {}
    changes = state if not record or resolution else {field: value for field, value in state.items() if previous.get(field) != value}
    if deleted:
        changes = {'deleted': True}
    if not changes:
        return None
    mutation = Mutation(event_id=uuid4(), workspace_id=workspace.workspace_id, device_id=workspace.device_id,
        device_seq=workspace.next_seq, entity=entity, entity_id=entity_id,
        op='resolution' if resolution else 'delete' if deleted else 'patch' if record else 'create',
        parents=(record.heads if resolution else record.applied_heads) if record else [], changes=changes, actor=actor)
    workspace.next_seq += 1
    data = mutation.model_dump(mode='json')
    session.add(SyncMutation(event_id=data['event_id'], workspace_id=data['workspace_id'], device_id=data['device_id'],
        device_seq=data['device_seq'], entity=entity, entity_id=entity_id, payload=data, applied=True))
    session.add(SyncOutbox(event_id=data['event_id']))
    if record is None:
        record = SyncRecord(key=key, imported=False)
        session.add(record)
    remaining = [] if resolution or not record.heads else [head for head in record.heads if head not in data['parents']]
    record.state, record.heads, record.applied_heads = state, sorted(remaining + [data['event_id']]), [data['event_id']]
    if enqueue:
        mark_dirty(session, [key])
    return data


def install_journal(engine):
    # Per-engine listeners avoid global Session state or cross-workspace echoes.
    if getattr(engine, '_compact_sync_journal', False):
        return
    engine._compact_sync_journal = True

    def before_flush(session, _context, _instances):
        if session.bind is not engine or session.info.get('sync_import'):
            return
        changed = [item for item in session.new | session.dirty | session.deleted if type(item) in DOMAIN]
        if changed:
            session.info['sync_changed'] = [(item, item in session.deleted) for item in changed]

    def after_flush(session, _context):
        changed = session.info.pop('sync_changed', [])
        if not changed:
            return
        workspace = session.get(SyncWorkspace, 1)
        if workspace is None:
            return
        from app.agent_call_context import current_call
        actor = 'AGENT' if current_call.get() else session.info.get('sync_actor', 'HUMAN')
        queued = []
        for item, deleted in changed:
            state = projection(item)
            if deleted:
                state['deleted'] = True
            if append_local(session, workspace, DOMAIN[type(item)], item.id, state, actor=actor, deleted=deleted, enqueue=False):
                queued.append(record_key(DOMAIN[type(item)], item.id))
        mark_dirty(session, queued)

    event.listen(Session, 'before_flush', before_flush)
    event.listen(Session, 'after_flush_postexec', after_flush)
    # Engine disposal happens at app/MCP shutdown. Remove Session listeners then
    # so repeated application instances don't accumulate references to engines.
    def cleanup(_engine):
        event.remove(Session, 'before_flush', before_flush)
        event.remove(Session, 'after_flush_postexec', after_flush)
        engine._compact_sync_journal = False
    event.listen(engine, 'engine_disposed', cleanup, once=True)
