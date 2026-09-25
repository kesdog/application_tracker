from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.applications import ApplicationNotFound, get_application
from app.activity import record_audit, record_event
from app.interview_schemas import InterviewCreate, InterviewUpdate
from app.models import ActorType, Application, AuditEntry, Interview, Note, Task


def get_interview(session: Session, interview_id: str) -> Interview:
    interview = session.get(Interview, interview_id)
    if interview is None or session.scalar(select(Application.id).where(Application.id == interview.application_id, Application.deleted_at.is_(None))) is None:
        raise ApplicationNotFound("Interview not found")
    return interview


def list_interviews(session: Session) -> list[dict]:
    rows = session.execute(
        select(Interview, Application)
        .join(Application, Interview.application_id == Application.id)
        .where(Application.deleted_at.is_(None))
        .order_by(Interview.scheduled_at, Interview.id)
    ).all()
    return [{**interview.__dict__, "application": application} for interview, application in rows]


def list_application_interviews(session: Session, application_id: str) -> list[Interview]:
    get_application(session, application_id)
    return list(session.scalars(
        select(Interview).where(Interview.application_id == application_id).order_by(Interview.scheduled_at, Interview.id)
    ))


def create_interview(
    session: Session, application_id: str, data: InterviewCreate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Interview:
    get_application(session, application_id)
    interview = Interview(application_id=application_id, **data.model_dump())
    session.add(interview)
    session.flush()
    record_event(session, application_id, "INTERVIEW_CREATED", f"{interview.type.value.title()} interview scheduled", actor_type=actor_type, actor_reference=actor_reference, metadata={"interview_id": interview.id, "scheduled_at": interview.scheduled_at})
    record_audit(session, application_id, "INTERVIEW", interview.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    session.commit()
    session.refresh(interview)
    return interview


def update_interview(
    session: Session, application_id: str, interview_id: str, data: InterviewUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Interview:
    get_application(session, application_id)
    interview = session.scalar(select(Interview).where(Interview.id == interview_id, Interview.application_id == application_id))
    if interview is None:
        raise ApplicationNotFound("Interview not found for this application")
    changes = {name: value for name, value in data.model_dump(exclude_unset=True).items() if value != getattr(interview, name)}
    previous = {name: getattr(interview, name) for name in changes}
    for name, value in changes.items():
        setattr(interview, name, value)
    if changes:
        record_event(session, application_id, "INTERVIEW_CHANGED", f"{interview.type.value.title()} interview updated", actor_type=actor_type, actor_reference=actor_reference, metadata={"interview_id": interview.id, "fields": sorted(changes)})
        record_audit(session, application_id, "INTERVIEW", interview.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
    session.commit()
    session.refresh(interview)
    return interview


def delete_interview(
    session: Session, application_id: str, interview_id: str, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> None:
    get_application(session, application_id)
    interview = session.scalar(select(Interview).where(Interview.id == interview_id, Interview.application_id == application_id))
    if interview is None:
        raise ApplicationNotFound("Interview not found for this application")
    record_event(session, application_id, "INTERVIEW_DELETED", f"{interview.type.value.title()} interview deleted", actor_type=actor_type, actor_reference=actor_reference, metadata={"interview_id": interview.id})
    record_audit(session, application_id, "INTERVIEW", interview.id, "DELETE", previous={"type": interview.type, "scheduled_at": interview.scheduled_at}, actor_type=actor_type, actor_reference=actor_reference)
    session.execute(update(AuditEntry).where(AuditEntry.entity_type == "INTERVIEW", AuditEntry.entity_id == interview.id).values(reversible=False))
    session.delete(interview)
    session.commit()


def interview_context(session: Session, interview_id: str) -> dict:
    interview = get_interview(session, interview_id)
    application = get_application(session, interview.application_id)
    return {
        "interview": interview,
        "application": application,
        "notes": list(session.scalars(select(Note).where(Note.application_id == application.id).order_by(Note.created_at.desc(), Note.id))),
        "tasks": list(session.scalars(select(Task).where(Task.application_id == application.id).order_by(Task.due_at.is_(None), Task.due_at, Task.id))),
        "documents": [],
    }


def list_tasks(session: Session) -> list[dict]:
    rows = session.execute(
        select(Task, Application)
        .join(Application, Task.application_id == Application.id)
        .where(Application.deleted_at.is_(None))
        .order_by(Task.due_at.is_(None), Task.due_at, Task.id)
    ).all()
    return [{**task.__dict__, "application": application} for task, application in rows]
