from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActorType, Application, AuditEntry, FollowUp, Interview, Note, Task, TimelineEvent, utc_now


class UndoUnavailable(ValueError):
    pass


class InvalidActor(ValueError):
    pass


def record_event(
    session: Session,
    application_id: str,
    event_type: str,
    summary: str,
    *,
    actor_type: ActorType = ActorType.HUMAN,
    actor_reference: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        application_id=application_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_reference=actor_reference,
        summary=summary,
        event_metadata=jsonable_encoder(metadata or {}),
    )
    session.add(event)
    return event


def record_audit(
    session: Session,
    application_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    *,
    previous: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
    actor_type: ActorType = ActorType.HUMAN,
    actor_reference: str | None = None,
    reversible: bool = False,
) -> AuditEntry:
    entry = AuditEntry(
        application_id=application_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        field="fields" if previous or new else None,
        previous_value=jsonable_encoder(previous) if previous is not None else None,
        new_value=jsonable_encoder(new) if new is not None else None,
        actor_type=actor_type,
        actor_reference=actor_reference,
        reversible=reversible,
    )
    session.add(entry)
    return entry


def timeline(session: Session, application_id: str) -> dict:
    events = list(session.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.application_id == application_id)
        .order_by(TimelineEvent.created_at.desc(), TimelineEvent.id.desc())
    ))
    return {"events": events, "undo_available": latest_undo(session, application_id) is not None}


def latest_undo(session: Session, application_id: str) -> AuditEntry | None:
    return session.scalar(
        select(AuditEntry)
        .where(
            AuditEntry.application_id == application_id,
            AuditEntry.reversible.is_(True),
            AuditEntry.undone_at.is_(None),
        )
        .order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
    )


MODELS = {
    "APPLICATION": Application,
    "NOTE": Note,
    "TASK": Task,
    "FOLLOWUP": FollowUp,
    "INTERVIEW": Interview,
}


def restore_value(model, field: str, value):
    if value is None:
        return None
    column = model.__table__.columns[field]
    enum_class = getattr(column.type, "enum_class", None)
    if enum_class is not None:
        return enum_class(value)
    python_type = column.type.python_type
    if python_type is datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    if python_type is date:
        return date.fromisoformat(value)
    return value


def undo_last(session: Session, application_id: str, *, actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None) -> dict:
    entry = latest_undo(session, application_id)
    if entry is None or entry.previous_value is None:
        raise UndoUnavailable("No reversible change is available")
    model = MODELS.get(entry.entity_type)
    if model is None:
        raise UndoUnavailable("The latest change cannot be restored")
    entity = session.get(model, entry.entity_id)
    if entity is None or (entry.entity_type != "APPLICATION" and entity.application_id != application_id):
        raise UndoUnavailable("The changed record no longer exists")
    for field, value in entry.previous_value.items():
        setattr(entity, field, restore_value(model, field, value))
    entry.undone_at = utc_now()
    fields = sorted(entry.previous_value)
    record_event(
        session, application_id, "UNDO", f"Undid {entry.entity_type.lower()} change",
        actor_type=actor_type, actor_reference=actor_reference,
        metadata={"audit_id": entry.id, "entity_type": entry.entity_type, "entity_id": entry.entity_id, "fields": fields},
    )
    session.commit()
    return {"audit_id": entry.id, "entity_type": entry.entity_type, "entity_id": entry.entity_id, "fields": fields}
