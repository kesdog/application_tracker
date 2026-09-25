from datetime import timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activity import InvalidActor, record_audit, record_event
from app.models import ActorType, Application, ApplicationStatus, utc_now
from app.schemas import ApplicationCreate, ApplicationUpdate


class ApplicationNotFound(Exception):
    pass


class InvalidApplication(ValueError):
    pass


def value_text(value) -> str:
    return getattr(value, "value", value) if value is not None else "none"


def create_application(
    session: Session, data: ApplicationCreate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Application:
    application = Application(**data.model_dump())
    session.add(application)
    session.flush()
    record_event(session, application.id, "APPLICATION_CREATED", "Application created", actor_type=actor_type, actor_reference=actor_reference)
    record_audit(session, application.id, "APPLICATION", application.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    session.commit()
    session.refresh(application)
    return application


def list_applications(session: Session) -> list[Application]:
    return list(session.scalars(select(Application).where(Application.deleted_at.is_(None)).order_by(Application.date_applied.desc(), Application.id)))


def get_application(session: Session, application_id: str) -> Application:
    application = session.get(Application, application_id)
    if application is None or application.deleted_at is not None:
        raise ApplicationNotFound("Application not found")
    return application


def update_application(
    session: Session, application_id: str, data: ApplicationUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Application:
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
    changes = {name: value for name, value in changes.items() if value != getattr(application, name)}
    previous = {name: getattr(application, name) for name in changes}
    for name, value in changes.items():
        setattr(application, name, value)
    if changes:
        record_audit(
            session, application_id, "APPLICATION", application_id, "UPDATE",
            previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True,
        )
        if "status" in changes:
            record_event(session, application_id, "STATUS_CHANGED", f"Status changed from {value_text(previous['status'])} to {value_text(changes['status'])}", actor_type=actor_type, actor_reference=actor_reference)
        if "outcome" in changes:
            record_event(session, application_id, "OUTCOME_CHANGED", f"Outcome changed from {value_text(previous['outcome'])} to {value_text(changes['outcome'])}", actor_type=actor_type, actor_reference=actor_reference)
        if "posting_status" in changes:
            record_event(session, application_id, "POSTING_STATUS_CHANGED", f"Posting status changed from {value_text(previous['posting_status'])} to {value_text(changes['posting_status'])}", actor_type=actor_type, actor_reference=actor_reference)
        other = set(changes) - {"status", "outcome", "posting_status"}
        if other:
            record_event(session, application_id, "APPLICATION_UPDATED", "Application details updated", actor_type=actor_type, actor_reference=actor_reference, metadata={"fields": sorted(other)})
    session.commit()
    session.refresh(application)
    return application


def delete_application(
    session: Session, application_id: str, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> None:
    if actor_type != ActorType.HUMAN:
        raise InvalidActor("Only a human can delete an application")
    application = get_application(session, application_id)
    application.deleted_at = utc_now()
    record_event(session, application_id, "APPLICATION_DELETED", "Application deleted", actor_type=actor_type, actor_reference=actor_reference)
    record_audit(session, application_id, "APPLICATION", application_id, "DELETE", previous={"deleted_at": None}, new={"deleted_at": application.deleted_at}, actor_type=actor_type, actor_reference=actor_reference, reversible=False)
    session.commit()
