"""Browser-search handoff and evidence-backed manual posting reviews."""
from datetime import datetime, timezone
from urllib.parse import urlencode

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy.orm import Session

from app.activity import record_audit, record_event
from app.applications import get_application
from app.confirmation_details import UNDISCLOSED_EMPLOYER
from app.job_sources import infer_job_source
from app.models import ActorType, PostingStatus, utc_now
from app.posting_checker import PostingCheckResult
from app.posting_service import apply_result


class PostingReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: PostingStatus
    evidence_url: HttpUrl = Field(max_length=2048)
    notes: str = Field(min_length=10, max_length=500)
    checked_at: AwareDatetime | None = None
    same_position: bool = False
    replace_job_url: bool = False

    @model_validator(mode="after")
    def require_match(self):
        if self.status != PostingStatus.UNKNOWN and not self.same_position:
            raise ValueError("Confirm the page is the same role, employer and location before marking it live or closed")
        if self.replace_job_url and (not self.same_position or self.status != PostingStatus.LIVE):
            raise ValueError("A replacement job URL requires a verified live posting for the same position")
        if self.checked_at and self.checked_at > datetime.now(timezone.utc):
            raise ValueError("The review date cannot be in the future")
        return self


def review_plan(session: Session, application_id: str) -> dict:
    application = get_application(session, application_id)
    employer = application.company if application.company != UNDISCLOSED_EMPLOYER else application.intermediary
    terms = " ".join(value for value in (application.job_title, f'"{employer}"' if employer else None, application.location) if value)
    searches = [{"label": "Search the web", "url": "https://www.google.com/search?" + urlencode({"q": terms})}]
    for label, domain in (("Search LinkedIn", "linkedin.com/jobs/view"), ("Search Indeed", "indeed.com/viewjob")):
        searches.append({"label": label, "url": "https://www.google.com/search?" + urlencode({"q": f"site:{domain} {terms}"})})
    if application.intermediary == "ISCOD":
        searches.append({"label": "Search ISCOD partner postings", "url": "https://www.google.com/search?" + urlencode({"q": f"site:iscod.fr/offres-emploi-en-alternance {terms}"})})
    return {
        "application_id": application.id, "job_url": application.job_url,
        "searches": searches,
        "instructions": "Check the saved URL first, then the rendered page. If missing or inconclusive, search by role, employer and location. Open a candidate posting and verify it is the same vacancy (job ID when available) before recording a conclusion or replacing the URL. A search snippet or no search results cannot prove closure. CV forwarding is not an employment offer.",
    }


def record_review(session: Session, application_id: str, data: PostingReviewCreate, *, actor_type: ActorType = ActorType.HUMAN):
    application = get_application(session, application_id)
    checked_at = data.checked_at.astimezone(timezone.utc).replace(tzinfo=None) if data.checked_at else utc_now()
    evidence_url = str(data.evidence_url)
    previous = {name: getattr(application, name) for name in (
        "job_url", "source", "posting_status", "posting_last_checked_at", "posting_http_status",
        "posting_final_url", "posting_check_method", "posting_check_reason", "posting_check_failures",
    )}
    if data.replace_job_url:
        application.job_url = evidence_url
        application.source = infer_job_source(evidence_url)
    # UNKNOWN is a deliberate manual conclusion; do not keep a stale LIVE badge.
    if data.status == PostingStatus.UNKNOWN:
        application.posting_status = PostingStatus.UNKNOWN
    record_event(session, application_id, "POSTING_REVIEWED", f"Browser review: {data.status.value}", actor_type=actor_type, occurred_at=checked_at,
                 metadata={"evidence_url": evidence_url, "notes": data.notes, "same_position": data.same_position, "previous_job_url": previous["job_url"], "replaced_job_url": data.replace_job_url})
    # All fields, the review evidence and the audit are saved in one transaction.
    new = {"posting_status": data.status, "posting_last_checked_at": checked_at, "posting_http_status": None,
           "posting_final_url": evidence_url, "posting_check_method": "MANUAL_BROWSER", "posting_check_reason": data.notes,
           "posting_check_failures": application.posting_check_failures + 1 if data.status == PostingStatus.UNKNOWN else 0,
           "job_url": application.job_url, "source": application.source}
    record_audit(session, application_id, "APPLICATION", application_id, "POSTING_REVIEW", previous=previous, new=new, actor_type=actor_type)
    return apply_result(session, application, PostingCheckResult(data.status, checked_at, None, evidence_url, "MANUAL_BROWSER", data.notes), actor_type=actor_type)
