"""Read helpers shared by REST and MCP through agent_ops."""
import base64
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import documents, interviews, work
from app.activity_schemas import TimelineEventRead
from app.applications import get_application, list_applications
from app.agent_schemas import AgentDueItem, AgentListRequest, ApplicationContextRead, CompactApplicationPage, CompactApplicationRead
from app.document_schemas import DocumentRead
from app.interview_schemas import InterviewRead
from app.models import FollowUpStatus, TaskStatus, TimelineEvent
from app.schemas import ApplicationRead
from app.work_schemas import FollowUpRead, NoteRead, TaskRead


def _cursor(application) -> str:
    raw = json.dumps([application.date_applied.isoformat(), application.id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        date_applied, application_id = json.loads(raw)
        if not isinstance(date_applied, str) or not isinstance(application_id, str):
            raise ValueError
        return date_applied, application_id
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination cursor") from exc


def _due_items(session: Session, application_id: str) -> list[AgentDueItem]:
    items: list[AgentDueItem] = []
    for task in session.scalars(select(work.Task).where(
        work.Task.application_id == application_id, work.Task.status == TaskStatus.PENDING, work.Task.due_at.is_not(None),
    )):
        items.append(AgentDueItem(id=task.id, kind="TASK", title=task.title, due_at=task.due_at, status=task.status.value))
    for followup in session.scalars(select(work.FollowUp).where(
        work.FollowUp.application_id == application_id, work.FollowUp.status.in_((FollowUpStatus.PENDING, FollowUpStatus.DRAFTED)),
    )):
        items.append(AgentDueItem(id=followup.id, kind="FOLLOWUP", title=f"Follow-up #{followup.sequence_number}", due_at=followup.due_at, status=followup.status.value))
    for interview in interviews.list_application_interviews(session, application_id):
        items.append(AgentDueItem(id=interview.id, kind="INTERVIEW", title=f"{interview.type.value.title()} interview", due_at=interview.scheduled_at, status="SCHEDULED"))
    return sorted(items, key=lambda item: (item.due_at, item.kind, item.id))


def compact_applications(session: Session, request: AgentListRequest) -> CompactApplicationPage:
    applications = list_applications(session, request.filters)
    if request.cursor:
        date_applied, application_id = _decode_cursor(request.cursor)
        applications = [item for item in applications if item.date_applied.isoformat() < date_applied or (
            item.date_applied.isoformat() == date_applied and item.id > application_id
        )]
    page = applications[:request.limit]
    items = [
        CompactApplicationRead.model_validate(item).model_copy(update={"next_due_item": (_due_items(session, item.id) or [None])[0]})
        for item in page
    ]
    return CompactApplicationPage(items=items, next_cursor=_cursor(page[-1]) if len(applications) > request.limit else None)


def application_context(session: Session, application_id: str, settings) -> ApplicationContextRead:
    application = get_application(session, application_id)
    current_work = work.get_work(session, application_id, settings)
    timeline = list(session.scalars(
        select(TimelineEvent).where(TimelineEvent.application_id == application_id).order_by(TimelineEvent.created_at.desc(), TimelineEvent.id.desc()).limit(20)
    ))
    return ApplicationContextRead(
        application=ApplicationRead.model_validate(application),
        notes=[NoteRead.model_validate(item) for item in current_work["notes"]],
        tasks=[TaskRead.model_validate(item) for item in current_work["tasks"]],
        followups=[FollowUpRead.model_validate(item) for item in current_work["followups"]],
        interviews=[InterviewRead.model_validate(item) for item in interviews.list_application_interviews(session, application_id)],
        documents=[DocumentRead.model_validate(item) for item in documents.list_documents(session, application_id)],
        recent_timeline=[TimelineEventRead.model_validate(item) for item in timeline],
        next_action=(_due_items(session, application_id) or [None])[0],
    )
