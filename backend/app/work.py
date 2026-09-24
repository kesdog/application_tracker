from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.applications import ApplicationNotFound, get_application
from app.config import Settings
from app.models import FollowUp, FollowUpStatus, Note, Task, TaskStatus, utc_now
from app.work_schemas import FollowUpCreate, FollowUpUpdate, NoteCreate, NoteUpdate, TaskCreate, TaskUpdate


def effective_settings(application, settings: Settings) -> dict:
    return {
        name: getattr(application, name) if getattr(application, name) is not None else getattr(settings, name)
        for name in ("followup_delay_days", "max_followup_suggestions")
    }


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


def save(session, item):
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def create_note(session: Session, application_id: str, data: NoteCreate, *, actor: str = "HUMAN") -> Note:
    get_application(session, application_id)
    return save(session, Note(application_id=application_id, created_by=actor, **data.model_dump()))


def update_note(session: Session, application_id: str, item_id: str, data: NoteUpdate) -> Note:
    item = child(session, Note, application_id, item_id)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(item, name, value)
    return save(session, item)


def create_task(session: Session, application_id: str, data: TaskCreate) -> Task:
    get_application(session, application_id)
    return save(session, Task(application_id=application_id, **data.model_dump()))


def update_task(session: Session, application_id: str, item_id: str, data: TaskUpdate) -> Task:
    item = child(session, Task, application_id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] != item.status:
        item.completed_at = utc_now() if changes["status"] == TaskStatus.COMPLETED else None
    for name, value in changes.items():
        setattr(item, name, value)
    return save(session, item)


def create_followup(session: Session, application_id: str, data: FollowUpCreate, settings: Settings) -> FollowUp:
    # Take SQLite's write lock before reading the next sequence number. API calls
    # supply a fresh session; simultaneous creates serialize within busy_timeout.
    session.execute(text("BEGIN IMMEDIATE"))
    application = get_application(session, application_id)
    sequence = (session.scalar(select(func.max(FollowUp.sequence_number)).where(FollowUp.application_id == application_id)) or 0) + 1
    due_at = data.due_at or utc_now() + timedelta(days=effective_settings(application, settings)["followup_delay_days"])
    # The suggestion cap is not a limit on manual creation. No email is sent here.
    return save(session, FollowUp(application_id=application_id, sequence_number=sequence, due_at=due_at, template_reference=data.template_reference))


def update_followup(session: Session, application_id: str, item_id: str, data: FollowUpUpdate) -> FollowUp:
    item = child(session, FollowUp, application_id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] != item.status:
        item.sent_at = utc_now() if changes["status"] == FollowUpStatus.SENT else None
    for name, value in changes.items():
        setattr(item, name, value)
    return save(session, item)
