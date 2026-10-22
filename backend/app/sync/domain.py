"""Dedicated state projection import. Never call creation/drafting business commands."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Application, Task, Interview, FollowUp, InvalidationEvent, utc_now
from app.sync.journal import record_key
from app.sync.models import SyncRecord
from app.sync.schemas import STATES

CLASSES = {'application': Application, 'task': Task, 'interview': Interview, 'followup': FollowUp}


class DomainBlocked(ValueError):
    pass


def imported_record(session, entity, entity_id):
    record = session.get(SyncRecord, record_key(entity, entity_id))
    return bool(record and record.imported)


def require_local_message(session, followup_id):
    if imported_record(session, 'followup', followup_id):
        from app.applications import InvalidApplication
        raise InvalidApplication('Message content is not synchronized. Prepare and review a message on this device first.')


def materialize(session, entity, entity_id, state):
    validated = STATES[entity].model_validate(state)
    values = validated.model_dump()
    deleted = values.pop('deleted')
    cls = CLASSES[entity]
    item = session.get(cls, entity_id)
    fresh = item is None
    if entity != 'application':
        values['application_id'] = str(values['application_id'])
        parent = session.get(Application, values['application_id'])
        if parent is None:
            raise DomainBlocked('missing_application')
        if item and item.application_id != values['application_id']:
            raise DomainBlocked('reparenting_forbidden')
        if parent.deleted_at and not deleted:
            raise DomainBlocked('deleted_application')
    if entity == 'followup':
        if values['parent_followup_id']:
            values['parent_followup_id'] = str(values['parent_followup_id'])
        collision = session.scalar(select(FollowUp.id).where(FollowUp.application_id == values['application_id'],
            FollowUp.sequence_number == values['sequence_number'], FollowUp.id != entity_id))
        if collision and not deleted:
            raise DomainBlocked('followup_sequence_collision')
    if deleted:
        if item:
            if entity == 'application':
                item.deleted_at = item.deleted_at or utc_now()
            else:
                session.delete(item)
            session.add(InvalidationEvent(topic='application.updated', application_id=entity_id if entity == 'application' else item.application_id))
        return fresh
    if item is None:
        item = cls(id=entity_id)
        session.add(item)
    for name, value in values.items():
        if isinstance(value, datetime) and value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        setattr(item, name, value)
    if entity == 'application':
        item.deleted_at = None
    elif entity == 'followup':
        # UI revisions are local and never accepted from the wire. Remote READY
        # is a status observation; it never approves this device's message.
        if not fresh:
            item.revision += 1
        item.approved_revision = None
    session.add(InvalidationEvent(topic='application.updated', application_id=entity_id if entity == 'application' else values['application_id']))
    return fresh
