from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__, activity, agent_auth, agent_context, applications, dashboard, integrations, interviews, invalidation, work
from app import agent_idempotency
from app.agent_schemas import AgentListRequest
from app.config import Settings
from app.models import ActorType
from app.schemas import ApplicationCreate, ApplicationFilters, ApplicationRead, ApplicationUpdate
from app.interview_schemas import InterviewContext, InterviewCreate, InterviewRead, InterviewUpdate
from app.work_schemas import FollowUpCreate, FollowUpRead, FollowUpUpdate, NoteCreate, NoteRead, TaskCreate, TaskRead, TaskUpdate
from app.activity_schemas import TimelineEntryCreate, TimelineEntryUpdate, TimelineEventRead, TimelineRead
from app.dashboard_schemas import DashboardRead


PERMISSION_FOR = {
    "list_applications": "read", "search_applications": "read", "get_application": "read", "get_application_context": "read", "get_tracker_info": "read",
    "find_possible_duplicates": "read", "get_application_timeline": "read", "get_upcoming_items": "read",
    "get_interview_context": "read", "create_application": "create", "update_application": "edit",
    "create_timeline_entry": "edit", "update_timeline_entry": "edit",
    "create_note": "draft", "create_followup": "draft", "mark_followup_sent": "draft",
    "draft_followup": "draft",
    "create_task": "tasks", "complete_task": "tasks", "create_interview": "interviews",
    "update_interview": "interviews",
}

IDEMPOTENT_CREATE_OPERATIONS = {"create_application", "create_note", "create_followup", "create_task", "create_interview"}


def invoke(
    session: Session, settings: Settings, operation: str, args: dict, *,
    mail_provider: integrations.MailProvider | None = None, calendar_provider: integrations.CalendarProvider | None = None,
    token_fingerprint: str | None = None,
) -> dict | list:
    if operation not in PERMISSION_FOR:
        raise KeyError(operation)
    args = dict(args)
    key = args.pop("idempotency_key", None)
    if key is not None and (not isinstance(key, str) or not key.strip() or len(key) > 200):
        raise ValueError("idempotency_key must be a non-empty string of 200 characters or fewer")
    if operation in IDEMPOTENT_CREATE_OPERATIONS and key:
        if not token_fingerprint:
            raise ValueError("An authenticated token is required for idempotency")
        record, replay = agent_idempotency.reserve(session, token_fingerprint, operation, key)
        if replay is not None:
            return replay
        try:
            result = _invoke(session, settings, operation, args, mail_provider=mail_provider, calendar_provider=calendar_provider)
            agent_idempotency.complete(session, record, result)
            return result
        except Exception:
            agent_idempotency.abandon(session, record)
            raise
    return _invoke(session, settings, operation, args, mail_provider=mail_provider, calendar_provider=calendar_provider)


def _invoke(
    session: Session, settings: Settings, operation: str, args: dict, *,
    mail_provider: integrations.MailProvider | None = None, calendar_provider: integrations.CalendarProvider | None = None,
) -> dict | list:
    application_id = args.get("application_id")
    actor = {"actor_type": ActorType.AGENT, "actor_reference": "agent-token"}
    topic = None

    if operation == "get_tracker_info":
        session.execute(text("SELECT 1"))
        result = {
            "application_version": __version__, "mcp_transport": settings.mcp_transport,
            "available_permissions": list(agent_auth.PERMISSIONS),
            "enabled_permissions": agent_auth.current_settings(session).permissions.model_dump(),
            "mail_integration_connected": bool(mail_provider and mail_provider.is_connected()),
            "calendar_integration_connected": bool(calendar_provider and calendar_provider.is_connected()),
            "database_ready": True,
        }
    elif operation in {"list_applications", "search_applications"}:
        result = agent_context.compact_applications(session, AgentListRequest.model_validate(args)).model_dump(mode="json")
    elif operation == "get_application":
        result = ApplicationRead.model_validate(applications.get_application(session, application_id)).model_dump(mode="json")
    elif operation == "get_application_context":
        result = agent_context.application_context(session, application_id, settings).model_dump(mode="json")
    elif operation == "find_possible_duplicates":
        result = jsonable_encoder(applications.find_possible_duplicates(session, ApplicationCreate.model_validate(args["application"])))
    elif operation == "get_application_timeline":
        applications.get_application(session, application_id)
        result = TimelineRead.model_validate(activity.timeline(session, application_id)).model_dump(mode="json")
    elif operation == "get_upcoming_items":
        result = DashboardRead.model_validate(dashboard.dashboard(session)).model_dump(mode="json")
    elif operation == "get_interview_context":
        result = InterviewContext.model_validate(interviews.interview_context(session, args["interview_id"])).model_dump(mode="json")
    elif operation == "create_application":
        item = applications.create_application(session, ApplicationCreate.model_validate(args["application"]), **actor)
        application_id = item.id
        result = ApplicationRead.model_validate(item).model_dump(mode="json")
        topic = "application.created"
    elif operation == "update_application":
        item = applications.update_application(session, application_id, ApplicationUpdate.model_validate(args["changes"]), **actor)
        result = ApplicationRead.model_validate(item).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "create_timeline_entry":
        item = activity.create_timeline_entry(session, application_id, TimelineEntryCreate.model_validate(args["entry"]), **actor)
        result = TimelineEventRead.model_validate(item).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "update_timeline_entry":
        item = activity.update_timeline_entry(session, application_id, args["event_id"], TimelineEntryUpdate.model_validate(args["changes"]), **actor)
        result = TimelineEventRead.model_validate(item).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "create_note":
        item = work.create_note(session, application_id, NoteCreate.model_validate(args["note"]), **actor)
        result = NoteRead.model_validate(item).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "create_followup":
        item = work.create_followup(session, application_id, FollowUpCreate.model_validate(args["followup"]), settings, **actor)
        result = FollowUpRead.model_validate(item).model_dump(mode="json")
        topic = "followup.updated"
    elif operation == "mark_followup_sent":
        item = work.update_followup(session, application_id, args["followup_id"], FollowUpUpdate(status="SENT"), **actor)
        result = FollowUpRead.model_validate(item).model_dump(mode="json")
        topic = "followup.updated"
    elif operation == "draft_followup":
        result = integrations.draft_followup(session, application_id, args["followup_id"], integrations.DraftRequest.model_validate({"content": args["content"]}), mail_provider or integrations.DisconnectedMailProvider(), **actor).model_dump(mode="json")
        topic = "followup.updated"
    elif operation == "create_task":
        item = work.create_task(session, application_id, TaskCreate.model_validate(args["task"]), **actor)
        result = TaskRead.model_validate(item).model_dump(mode="json")
        topic = "task.updated"
    elif operation == "complete_task":
        item = work.update_task(session, application_id, args["task_id"], TaskUpdate(status="COMPLETED"), **actor)
        result = TaskRead.model_validate(item).model_dump(mode="json")
        topic = "task.updated"
    elif operation == "create_interview":
        item = interviews.create_interview(session, application_id, InterviewCreate.model_validate(args["interview"]), **actor)
        result = InterviewRead.model_validate(item).model_dump(mode="json")
        topic = "interview.updated"
    else:
        item = interviews.update_interview(session, application_id, args["interview_id"], InterviewUpdate.model_validate(args["changes"]), **actor)
        result = InterviewRead.model_validate(item).model_dump(mode="json")
        topic = "interview.updated"

    if topic:
        invalidation.publish(session, topic, application_id)
    return result
