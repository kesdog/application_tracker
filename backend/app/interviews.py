from sqlalchemy import select
from sqlalchemy.orm import Session

from app.applications import ApplicationNotFound, get_application
from app.interview_schemas import InterviewCreate, InterviewUpdate
from app.models import Application, Interview, Note, Task


def get_interview(session: Session, interview_id: str) -> Interview:
    interview = session.get(Interview, interview_id)
    if interview is None:
        raise ApplicationNotFound("Interview not found")
    return interview


def list_interviews(session: Session) -> list[dict]:
    rows = session.execute(
        select(Interview, Application)
        .join(Application, Interview.application_id == Application.id)
        .order_by(Interview.scheduled_at, Interview.id)
    ).all()
    return [{**interview.__dict__, "application": application} for interview, application in rows]


def list_application_interviews(session: Session, application_id: str) -> list[Interview]:
    get_application(session, application_id)
    return list(session.scalars(
        select(Interview).where(Interview.application_id == application_id).order_by(Interview.scheduled_at, Interview.id)
    ))


def create_interview(session: Session, application_id: str, data: InterviewCreate) -> Interview:
    get_application(session, application_id)
    interview = Interview(application_id=application_id, **data.model_dump())
    session.add(interview)
    session.commit()
    session.refresh(interview)
    return interview


def update_interview(session: Session, application_id: str, interview_id: str, data: InterviewUpdate) -> Interview:
    get_application(session, application_id)
    interview = session.scalar(select(Interview).where(Interview.id == interview_id, Interview.application_id == application_id))
    if interview is None:
        raise ApplicationNotFound("Interview not found for this application")
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(interview, name, value)
    session.commit()
    session.refresh(interview)
    return interview


def delete_interview(session: Session, application_id: str, interview_id: str) -> None:
    get_application(session, application_id)
    interview = session.scalar(select(Interview).where(Interview.id == interview_id, Interview.application_id == application_id))
    if interview is None:
        raise ApplicationNotFound("Interview not found for this application")
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
        .order_by(Task.due_at.is_(None), Task.due_at, Task.id)
    ).all()
    return [{**task.__dict__, "application": application} for task, application in rows]
