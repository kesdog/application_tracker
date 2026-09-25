"""Persistence boundary for deterministic posting checks."""
import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activity import record_event
from app.applications import get_application
from app.models import ActorType, Application, PostingStatus, utc_now
from app.posting_checker import PostingCheckResult, PostingChecker
from app.schemas import PostingCheckRead


def apply_result(session: Session, application: Application, result: PostingCheckResult, *, actor_type: ActorType = ActorType.SYSTEM) -> PostingCheckRead:
    prior = application.posting_status
    application.posting_last_checked_at = result.checked_at
    application.posting_http_status = result.http_status
    application.posting_final_url = result.final_url
    application.posting_check_method = result.method
    application.posting_check_reason = result.reason
    if result.status == PostingStatus.UNKNOWN:
        application.posting_check_failures += 1
    else:
        application.posting_check_failures = 0
        application.posting_status = result.status
    if result.status != PostingStatus.UNKNOWN and prior != result.status:
        record_event(
            session, application.id, "POSTING_STATUS_CHANGED",
            f"Posting status changed from {prior.value} to {result.status.value}",
            actor_type=actor_type, metadata={"method": result.method, "reason": result.reason},
        )
    session.commit()
    return PostingCheckRead(
        status=application.posting_status, checked_at=result.checked_at, http_status=result.http_status,
        final_url=result.final_url, method=result.method, reason=result.reason,
        failures=application.posting_check_failures,
    )


def check_application_posting(session: Session, application_id: str, checker: PostingChecker | None = None, *, actor_type: ActorType = ActorType.HUMAN) -> PostingCheckRead:
    application = get_application(session, application_id)
    if not application.job_url:
        result = PostingCheckResult(PostingStatus.UNKNOWN, utc_now(), None, None, "ERROR", "No job URL is saved for this application")
    else:
        result = asyncio.run((checker or PostingChecker()).check(application.job_url))
    return apply_result(session, application, result, actor_type=actor_type)


def eligible_application_ids(session: Session) -> list[str]:
    return list(session.scalars(select(Application.id).where(
        Application.deleted_at.is_(None), Application.job_url.is_not(None), Application.posting_status != PostingStatus.CLOSED,
    ).order_by(Application.posting_last_checked_at.is_(None).desc(), Application.posting_last_checked_at, Application.id)))
