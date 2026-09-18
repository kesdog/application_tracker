from datetime import timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, ApplicationStatus
from app.schemas import ApplicationCreate, ApplicationUpdate


class ApplicationNotFound(Exception):
    pass


class InvalidApplication(ValueError):
    pass


def create_application(session: Session, data: ApplicationCreate) -> Application:
    application = Application(**data.model_dump())
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def list_applications(session: Session) -> list[Application]:
    return list(session.scalars(select(Application).order_by(Application.date_applied.desc(), Application.id)))


def get_application(session: Session, application_id: str) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise ApplicationNotFound("Application not found")
    return application


def update_application(session: Session, application_id: str, data: ApplicationUpdate) -> Application:
    application = get_application(session, application_id)
    changes = data.model_dump(exclude_unset=True)
    # Validate the whole prospective record before mutating any persisted fields.
    merged = {name: changes.get(name, getattr(application, name)) for name in ApplicationCreate.model_fields}
    try:
        ApplicationCreate.model_validate(merged)
    except ValidationError as exc:
        raise InvalidApplication(". ".join(error["msg"] for error in exc.errors())) from exc

    status = changes.get("status", application.status)
    outcome = changes.get("outcome", application.outcome)
    if application.status == ApplicationStatus.CLOSED and status != ApplicationStatus.CLOSED:
        if application.outcome is not None and ("outcome" not in changes or changes["outcome"] is not None):
            raise InvalidApplication("To reopen this application, explicitly clear its outcome")
    if outcome is not None:
        if "status" in changes and status != ApplicationStatus.CLOSED:
            raise InvalidApplication("An outcome requires status CLOSED")
        changes["status"] = ApplicationStatus.CLOSED

    checked_at = changes.get("posting_last_checked_at")
    if checked_at is not None:
        changes["posting_last_checked_at"] = checked_at.astimezone(timezone.utc).replace(tzinfo=None)
    for name, value in changes.items():
        setattr(application, name, value)
    session.commit()
    session.refresh(application)
    return application
