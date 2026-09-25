from datetime import timezone

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.activity import InvalidActor, record_audit, record_event
from app.job_sources import infer_job_source
from app.models import ActorType, Application, ApplicationDocument, ApplicationStatus, utc_now
from app.schemas import ApplicationCreate, ApplicationFilters, ApplicationUpdate


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
    if data.source is None:
        data = data.model_copy(update={"source": infer_job_source(data.job_url)})
    duplicates = find_possible_duplicates(session, data)
    application = Application(**data.model_dump())
    session.add(application)
    session.flush()
    record_event(session, application.id, "APPLICATION_CREATED", "Application created", actor_type=actor_type, actor_reference=actor_reference)
    record_audit(session, application.id, "APPLICATION", application.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    session.commit()
    session.refresh(application)
    application.duplicate_warnings = duplicates
    return application


def list_applications(session: Session, filters: ApplicationFilters | None = None) -> list[Application]:
    filters = filters or ApplicationFilters()
    query = select(Application).where(Application.deleted_at.is_(None))
    if filters.q:
        term = filters.q.casefold()
        searchable = (
            Application.job_title, Application.company, Application.location, Application.remote_policy,
            Application.contract_type, Application.source, Application.description, Application.requirements,
            Application.job_url, Application.email_reference, Application.phone_number,
        )
        query = query.where(or_(*(func.lower(func.coalesce(column, "")).contains(term, autoescape=True) for column in searchable)))
    if filters.status:
        query = query.where(Application.status == filters.status)
    if filters.outcome:
        query = query.where(Application.outcome == filters.outcome)
    for value, column in (
        (filters.company, Application.company), (filters.title, Application.job_title),
        (filters.location, Application.location), (filters.contract_type, Application.contract_type),
        (filters.source, Application.source), (filters.remote_policy, Application.remote_policy),
    ):
        if value:
            query = query.where(func.lower(func.coalesce(column, "")).contains(value.casefold(), autoescape=True))
    if filters.date_from:
        query = query.where(Application.date_applied >= filters.date_from)
    if filters.date_to:
        query = query.where(Application.date_applied <= filters.date_to)
    if filters.document_filename:
        document_match = select(ApplicationDocument.id).where(
            ApplicationDocument.application_id == Application.id,
            func.lower(ApplicationDocument.filename).contains(filters.document_filename.casefold(), autoescape=True),
        ).exists()
        query = query.where(document_match)
    return list(session.scalars(query.order_by(Application.date_applied.desc(), Application.id)))


def normalized(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def normalized_url(value: str | None) -> str:
    return normalized(value).rstrip("/")


def find_possible_duplicates(session: Session, data: ApplicationCreate) -> list[dict]:
    company = normalized(data.company)
    title = normalized(data.job_title)
    job_url = normalized_url(data.job_url)
    matches = []
    for candidate in session.scalars(select(Application).where(Application.deleted_at.is_(None))):
        reasons = []
        if company == normalized(candidate.company) and title == normalized(candidate.job_title):
            reasons.append("same company and title")
        if job_url and job_url == normalized_url(candidate.job_url):
            reasons.append("same job URL")
        if not reasons:
            continue
        if abs((data.date_applied - candidate.date_applied).days) <= 30:
            reasons.append("application dates within 30 days")
        matches.append({
            "id": candidate.id, "job_title": candidate.job_title, "company": candidate.company,
            "date_applied": candidate.date_applied, "reasons": reasons,
        })
    return sorted(matches, key=lambda item: (item["date_applied"], item["id"]), reverse=True)


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
