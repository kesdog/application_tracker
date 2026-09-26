from datetime import datetime, time, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.applications import ApplicationNotFound, InvalidApplication, get_application
from app.activity import record_audit, record_event
from app.config import Settings
from app.models import ActorType, Application, ApplicationStatus, ContactType, FollowUp, FollowUpChannel, FollowUpStatus, Note, Task, TaskStatus, utc_now
from app.work_schemas import FollowUpCreate, FollowUpUpdate, NoteCreate, NoteUpdate, TaskCreate, TaskUpdate


def effective_settings(application, settings: Settings) -> dict:
    return {
        name: getattr(application, name) if getattr(application, name) is not None else getattr(settings, name)
        for name in ("followup_delay_days", "max_followup_suggestions")
    }


def automatic_due_at(application: Application, settings: Settings, *, after: datetime | None = None) -> datetime:
    delay = effective_settings(application, settings)["followup_delay_days"]
    baseline = after or datetime.combine(application.date_applied, time(9))
    return baseline + timedelta(days=delay)


def automatic_channel(application: Application) -> FollowUpChannel:
    return FollowUpChannel.PHONE if application.contact_type == ContactType.PHONE else FollowUpChannel.EMAIL


def can_schedule_automatic_followup(application: Application, settings: Settings) -> bool:
    return (
        application.deleted_at is None
        and application.status != ApplicationStatus.CLOSED
        and application.outcome is None
        and effective_settings(application, settings)["max_followup_suggestions"] > 0
    )


def schedule_automatic_followup(
    session: Session, application: Application, settings: Settings, *, after: datetime | None = None,
    actor_type: ActorType = ActorType.SYSTEM, actor_reference: str | None = None,
) -> FollowUp | None:
    if not can_schedule_automatic_followup(application, settings):
        return None
    automatic_count = session.scalar(
        select(func.count()).select_from(FollowUp).where(
            FollowUp.application_id == application.id, FollowUp.is_automatic.is_(True),
        )
    ) or 0
    if automatic_count >= effective_settings(application, settings)["max_followup_suggestions"]:
        return None
    sequence = (session.scalar(select(func.max(FollowUp.sequence_number)).where(FollowUp.application_id == application.id)) or 0) + 1
    item = FollowUp(
        application_id=application.id, sequence_number=sequence,
        due_at=automatic_due_at(application, settings, after=after),
        is_automatic=True, channel=automatic_channel(application), template_reference="Automatic follow-up reminder",
    )
    session.add(item)
    session.flush()
    record_event(
        session, application.id, "FOLLOWUP_CREATED", f"Automatic follow-up #{sequence} scheduled for {item.due_at.date().isoformat()}",
        actor_type=actor_type, actor_reference=actor_reference,
        metadata={"followup_id": item.id, "automatic": True, "due_at": item.due_at},
    )
    return item


def ensure_initial_followups(session: Session, settings: Settings) -> int:
    """Backfill the first reminder for active applications exactly once."""
    created = 0
    applications = session.scalars(select(Application).where(Application.deleted_at.is_(None))).all()
    for application in applications:
        existing = session.scalar(select(FollowUp.id).where(
            FollowUp.application_id == application.id, FollowUp.is_automatic.is_(True),
        ))
        if existing is None and schedule_automatic_followup(session, application, settings) is not None:
            created += 1
    if created:
        session.commit()
    return created


def reschedule_pending_automatic_followups(session: Session, application: Application, settings: Settings) -> int:
    changed = 0
    for item in session.scalars(select(FollowUp).where(
        FollowUp.application_id == application.id,
        FollowUp.is_automatic.is_(True),
        FollowUp.status == FollowUpStatus.PENDING,
    )):
        due_at = automatic_due_at(application, settings)
        if item.due_at != due_at:
            item.due_at = due_at
            changed += 1
    if changed:
        record_event(
            session, application.id, "FOLLOWUP_CHANGED", "Automatic follow-up schedule updated",
            actor_type=ActorType.HUMAN, metadata={"automatic": True, "count": changed},
        )
    return changed


def get_work(session: Session, application_id: str, settings: Settings) -> dict:
    application = get_application(session, application_id)
    return {
        "notes": list(session.scalars(select(Note).where(Note.application_id == application_id).order_by(Note.created_at.desc(), Note.id))),
        "tasks": list(session.scalars(select(Task).where(Task.application_id == application_id).order_by(Task.due_at.is_(None), Task.due_at, Task.id))),
        "followups": list(session.scalars(select(FollowUp).where(FollowUp.application_id == application_id).order_by(FollowUp.sequence_number))),
        **effective_settings(application, settings),
    }


def child(session, model, application_id, item_id):
    get_application(session, application_id)
    item = session.scalar(select(model).where(model.id == item_id, model.application_id == application_id))
    if item is None:
        raise ApplicationNotFound("Record not found for this application")
    return item


def finish(session, item):
    session.commit()
    session.refresh(item)
    return item


def create_note(
    session: Session, application_id: str, data: NoteCreate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Note:
    get_application(session, application_id)
    item = Note(application_id=application_id, created_by=actor_reference or actor_type.value, **data.model_dump())
    session.add(item); session.flush()
    record_event(session, application_id, "NOTE_ADDED", f"{item.type.value.title()} note added", actor_type=actor_type, actor_reference=actor_reference, metadata={"note_id": item.id})
    record_audit(session, application_id, "NOTE", item.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item)


def update_note(
    session: Session, application_id: str, item_id: str, data: NoteUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Note:
    item = child(session, Note, application_id, item_id)
    changes = {name: value for name, value in data.model_dump(exclude_unset=True).items() if value != getattr(item, name)}
    previous = {name: getattr(item, name) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if changes:
        record_event(session, application_id, "NOTE_CHANGED", "Note updated", actor_type=actor_type, actor_reference=actor_reference, metadata={"note_id": item.id, "fields": sorted(changes)})
        record_audit(session, application_id, "NOTE", item.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
    return finish(session, item)


def create_task(
    session: Session, application_id: str, data: TaskCreate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Task:
    get_application(session, application_id)
    item = Task(application_id=application_id, **data.model_dump())
    session.add(item); session.flush()
    record_event(session, application_id, "TASK_CREATED", f"Task created: {item.title}", actor_type=actor_type, actor_reference=actor_reference, metadata={"task_id": item.id})
    record_audit(session, application_id, "TASK", item.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item)


def update_task(
    session: Session, application_id: str, item_id: str, data: TaskUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Task:
    item = child(session, Task, application_id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] != item.status:
        changes["completed_at"] = utc_now() if changes["status"] == TaskStatus.COMPLETED else None
    changes = {name: value for name, value in changes.items() if value != getattr(item, name)}
    previous = {name: getattr(item, name) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if changes:
        event_type = "TASK_COMPLETED" if changes.get("status") == TaskStatus.COMPLETED else "TASK_CHANGED"
        summary = f"Task completed: {item.title}" if event_type == "TASK_COMPLETED" else f"Task updated: {item.title}"
        record_event(session, application_id, event_type, summary, actor_type=actor_type, actor_reference=actor_reference, metadata={"task_id": item.id})
        record_audit(session, application_id, "TASK", item.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
    return finish(session, item)


def create_followup(
    session: Session, application_id: str, data: FollowUpCreate, settings: Settings, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> FollowUp:
    # Take SQLite's write lock before reading the next sequence number. API calls
    # supply a fresh session; simultaneous creates serialize within busy_timeout.
    session.execute(text("BEGIN IMMEDIATE"))
    application = get_application(session, application_id)
    if data.channel in (FollowUpChannel.PHONE, FollowUpChannel.BOTH) and not application.phone_number:
        raise InvalidApplication("Add a phone number to the application before choosing a phone follow-up")
    sequence = (session.scalar(select(func.max(FollowUp.sequence_number)).where(FollowUp.application_id == application_id)) or 0) + 1
    due_at = data.due_at or utc_now() + timedelta(days=effective_settings(application, settings)["followup_delay_days"])
    # The suggestion cap is not a limit on manual creation. No email is sent here.
    item = FollowUp(application_id=application_id, sequence_number=sequence, due_at=due_at, template_reference=data.template_reference, channel=data.channel)
    session.add(item); session.flush()
    record_event(session, application_id, "FOLLOWUP_CREATED", f"Follow-up #{sequence} created", actor_type=actor_type, actor_reference=actor_reference, metadata={"followup_id": item.id})
    record_audit(session, application_id, "FOLLOWUP", item.id, "CREATE", new={"sequence_number": sequence, "due_at": due_at, "template_reference": data.template_reference, "channel": data.channel}, actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item)


def update_followup(
    session: Session, application_id: str, item_id: str, data: FollowUpUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None, settings: Settings | None = None,
) -> FollowUp:
    item = child(session, FollowUp, application_id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "channel" in changes and changes["channel"] in (FollowUpChannel.PHONE, FollowUpChannel.BOTH) and not get_application(session, application_id).phone_number:
        raise InvalidApplication("Add a phone number to the application before choosing a phone follow-up")
    if "status" in changes and changes["status"] != item.status:
        changes["sent_at"] = utc_now() if changes["status"] == FollowUpStatus.SENT else None
    changes = {name: value for name, value in changes.items() if value != getattr(item, name)}
    previous = {name: getattr(item, name) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if changes:
        status = changes.get("status")
        event_type = "FOLLOWUP_SENT" if status == FollowUpStatus.SENT else "FOLLOWUP_DRAFTED" if status == FollowUpStatus.DRAFTED else "FOLLOWUP_CHANGED"
        if status == FollowUpStatus.SENT:
            method = "email and phone" if item.channel == FollowUpChannel.BOTH else "phone" if item.channel == FollowUpChannel.PHONE else "email"
            summary = f"Follow-up #{item.sequence_number} completed by {method}"
        else:
            summary = f"Follow-up #{item.sequence_number} {status.value.lower()}" if status else f"Follow-up #{item.sequence_number} updated"
        record_event(session, application_id, event_type, summary, actor_type=actor_type, actor_reference=actor_reference, metadata={"followup_id": item.id})
        record_audit(session, application_id, "FOLLOWUP", item.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
        if changes.get("status") == FollowUpStatus.SENT and item.is_automatic:
            schedule_automatic_followup(session, get_application(session, application_id), settings=settings or Settings(), after=item.sent_at, actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item)
