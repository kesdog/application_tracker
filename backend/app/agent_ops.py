from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__, activity, agent_auth, agent_context, applications, confirmation_links, confirmation_details, dashboard, integrations, interviews, invalidation, posting_service, posting_review, work
from app.posting_checker import PostingChecker, render_with_playwright
from app import agent_idempotency
from app import followup_ai
from app import recipient_discovery, recipient_reports
from app.agent_schemas import AgentApplicationCreate, AgentApplicationUpdate, AgentListRequest
from app.contract_types import CONTRACT_OPTIONS
from app.config import Settings
from app.models import ActorType
from app import google_connection
from app.agent_call_context import current_call
import hashlib
import json
from uuid import UUID, uuid4
from app.schemas import ApplicationRead
from app.interview_schemas import InterviewContext, InterviewCreate, InterviewRead, InterviewUpdate
from app.work_schemas import FollowUpCreate, FollowUpRead, FollowUpUpdate, NoteCreate, NoteRead, TaskCreate, TaskRead, TaskUpdate
from app.activity_schemas import TimelineEntryCreate, TimelineEntryUpdate, TimelineEventRead, TimelineRead
from app.dashboard_schemas import DashboardRead


PERMISSION_FOR = {
    "search_mail": "read", "get_mail_message": "read",
    "get_recipient_settings": "read", "update_recipient_settings": "edit",
    "get_recipient_research": "read", "queue_recipient_research": "edit",
    "list_recipient_page_reports": "read", "get_recipient_page_report": "read",
    "extract_confirmation_details": "read", "get_posting_review": "read", "record_posting_review": "edit",
    "list_applications": "read", "search_applications": "read", "get_application": "read", "get_application_context": "read", "get_tracker_info": "read",
    "find_possible_duplicates": "read", "extract_confirmation_posting_link": "read", "get_application_timeline": "read", "get_upcoming_items": "read",
    "get_interview_context": "read", "create_application": "create", "update_application": "edit",
    "create_timeline_entry": "edit", "update_timeline_entry": "edit", "check_posting_status": "edit",
    "create_note": "draft", "create_followup": "draft", "mark_followup_sent": "draft",
    "draft_followup": "draft", "get_followup_request": "read", "revise_followup": "draft", "report_followup_result": "draft",
    "create_task": "tasks", "complete_task": "tasks", "create_interview": "interviews",
    "update_interview": "interviews",
}

def invoke(session, settings, operation, args, **kwargs):
    args = dict(args)
    supplied_id = args.pop('request_id', None)
    correlation_id = kwargs.pop('correlation_id', None)
    if supplied_id is not None:
        if not isinstance(supplied_id, str):
            raise ValueError('request_id must be a UUID string')
        request_id = str(UUID(supplied_id))
    else:
        request_id = str(UUID(correlation_id)) if correlation_id else str(uuid4())
    label = args.pop('client_label', 'unknown')
    if not isinstance(label, str) or label not in {'chatgpt', 'claude', 'codex', 'unknown'}:
        label = 'unknown'
    if supplied_id and operation in PERMISSION_FOR and PERMISSION_FOR[operation] != 'read':
        args.setdefault('idempotency_key', request_id)
    marker = current_call.set({'request_id': request_id, 'client_label': label, 'client_label_verified': False})
    try:
        return _authorized_invoke(session, settings, operation, args, **kwargs)
    finally:
        current_call.reset(marker)


def _authorized_invoke(
    session: Session, settings: Settings, operation: str, args: dict, *,
    mail_provider: integrations.MailProvider | None = None, calendar_provider: integrations.CalendarProvider | None = None,
    token_fingerprint: str | None = None,
) -> dict | list:
    if operation not in PERMISSION_FOR:
        raise KeyError(operation)
    if token_fingerprint:
        from app.models import AgentCredential
        import hmac
        credential = session.get(AgentCredential, 1)
        if not credential or not hmac.compare_digest(credential.token_hash, token_fingerprint):
            from app.agent_errors import AgentApiError
            raise AgentApiError('INVALID_TOKEN', 'Valid agent bearer token required', 401)
        if not credential.permissions.get(PERMISSION_FOR[operation], False):
            from app.agent_errors import AgentApiError
            raise AgentApiError('PERMISSION_DENIED', f'Agent permission required: {PERMISSION_FOR[operation]}', 403)
        agent_auth.mark_used(session, token_fingerprint)
    args = dict(args)
    key = args.pop("idempotency_key", None)
    if key is not None and (not isinstance(key, str) or not key.strip() or len(key) > 200):
        raise ValueError("idempotency_key must be a non-empty string of 200 characters or fewer")
    if operation == 'draft_followup':
        if not args.get('expected_revision'):
            raise ValueError('expected_revision is required when creating a follow-up draft')
        if key:
            from uuid import uuid5, NAMESPACE_URL
            args['operation_id'] = str(uuid5(NAMESPACE_URL, f'tracker:{token_fingerprint}:draft:{key}'))
        elif not args.get('operation_id'):
            raise ValueError('Supply a stable operation_id UUID or idempotency_key for a draft request')
    if PERMISSION_FOR[operation] != 'read' and operation != 'draft_followup' and key:
        if not token_fingerprint:
            raise ValueError("An authenticated token is required for idempotency")
        request_hash = hashlib.sha256(json.dumps(jsonable_encoder(args), sort_keys=True).encode()).hexdigest()
        record, replay = agent_idempotency.reserve(session, token_fingerprint, operation, key, request_hash)
        if replay is not None:
            return replay
        try:
            result = _invoke(session, settings, operation, args, mail_provider=mail_provider, calendar_provider=calendar_provider, token_fingerprint=token_fingerprint)
            agent_idempotency.complete(session, record, result)
            return result
        except Exception:
            # A service may have committed before a response/audit failure. Keep
            # the reservation so an uncertain retry cannot create a second record.
            session.rollback()
            raise
    return _invoke(session, settings, operation, args, mail_provider=mail_provider, calendar_provider=calendar_provider, token_fingerprint=token_fingerprint)


def _invoke(
    session: Session, settings: Settings, operation: str, args: dict, *,
    mail_provider: integrations.MailProvider | None = None, calendar_provider: integrations.CalendarProvider | None = None,
    token_fingerprint: str | None = None,
) -> dict | list:
    application_id = args.get("application_id")
    actor = {"actor_type": ActorType.AGENT, "actor_reference": "agent-token"}
    topic = None

    if operation in {'search_mail', 'get_mail_message'}:
        if not isinstance(mail_provider, google_connection.GoogleMailProvider):
            raise google_connection.GoogleConnectionError('Connect Google in Settings to use mailbox lookup.')
        if operation == 'search_mail':
            result = mail_provider.search(**google_connection.MailSearch.model_validate(args).model_dump())
        else:
            result = mail_provider.lookup(**google_connection.MailLookup.model_validate(args).model_dump())
    elif operation == "get_recipient_settings":
        result = recipient_reports.research_settings(session)
        session.commit()
    elif operation == "update_recipient_settings":
        result = recipient_reports.update_settings(session, recipient_reports.ResearchSettingsUpdate.model_validate(args))
        topic = 'settings.updated'
    elif operation == "get_recipient_research":
        result = recipient_discovery.application_state(session, application_id)
        session.commit()
    elif operation == "queue_recipient_research":
        request = recipient_reports.ResearchRequest.model_validate({k: v for k, v in args.items() if k != 'application_id'})
        result = recipient_discovery.enqueue(session, application_id, request.refresh_pages)
        topic = 'recipient.updated'
    elif operation == "list_recipient_page_reports":
        query = recipient_reports.ReportQuery.model_validate(args)
        result = recipient_reports.list_reports(session, **query.model_dump())
    elif operation == "get_recipient_page_report":
        result = recipient_reports.get_report(session, args['report_id'], application_id)
    elif operation == "get_tracker_info":
        session.execute(text("SELECT 1"))
        result = {
            "application_version": __version__, "mcp_transport": settings.mcp_transport,
            "available_permissions": list(agent_auth.PERMISSIONS),
            "enabled_permissions": agent_auth.current_settings(session).permissions.model_dump(),
            "mail_integration_connected": bool(mail_provider and mail_provider.is_connected()),
            "calendar_integration_connected": bool(calendar_provider and calendar_provider.is_connected()),
            "database_ready": True,
            "application_constraints": {
                "contract_types": [{"value": value, "label": label} for value, label in CONTRACT_OPTIONS.items()],
                "unknown_contract_type": None,
                "date_format": "YYYY-MM-DD",
                "application_date_source": "Use the verified applied date, otherwise the original confirmation email date.",
                "missing_job_url_requires_email_reference": True,
                "closed_attention_takes_precedence": True,
                "recipient_research": {"default_page_limit": 6, "page_limit_range": [1,100],
                    "application_override": "recipient_page_limit (null inherits general settings)",
                    "budget": "new page fetches per run; saved reports reused until explicit refresh",
                    "queue_requires_running_backend": True},
            },
        }
    elif operation in {"list_applications", "search_applications"}:
        result = agent_context.compact_applications(session, AgentListRequest.model_validate(args)).model_dump(mode="json")
    elif operation == "get_application":
        result = ApplicationRead.model_validate(applications.get_application(session, application_id)).model_dump(mode="json")
    elif operation == "get_application_context":
        result = agent_context.application_context(session, application_id, settings).model_dump(mode="json")
    elif operation == "find_possible_duplicates":
        result = jsonable_encoder(applications.find_possible_duplicates(session, AgentApplicationCreate.model_validate(args["application"])))
    elif operation == "extract_confirmation_posting_link":
        result = confirmation_links.extract_confirmation_link(args["confirmation_email"]).model_dump()
    elif operation == "extract_confirmation_details":
        result = confirmation_details.extract_confirmation_details(args["confirmation_email"]).model_dump()
    elif operation == "get_posting_review":
        result = posting_review.review_plan(session, application_id)
    elif operation == "record_posting_review":
        result = posting_review.record_review(session, application_id, posting_review.PostingReviewCreate.model_validate(args["review"]), actor_type=ActorType.AGENT).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "get_application_timeline":
        applications.get_application(session, application_id)
        result = TimelineRead.model_validate(activity.timeline(session, application_id)).model_dump(mode="json")
    elif operation == "get_upcoming_items":
        result = DashboardRead.model_validate(dashboard.dashboard(session)).model_dump(mode="json")
    elif operation == "get_interview_context":
        result = InterviewContext.model_validate(interviews.interview_context(session, args["interview_id"])).model_dump(mode="json")
    elif operation == "create_application":
        data = dict(args["application"])
        if args.get("confirmation_email"):
            details = confirmation_details.extract_confirmation_details(args["confirmation_email"])
            for field in ("job_title", "company", "date_applied", "intermediary"):
                if not data.get(field) and getattr(details, field):
                    data[field] = getattr(details, field)
            if details.intermediary == "ISCOD" and (data.get("company", "").casefold() == "iscod" or not data.get("company")):
                data["company"] = details.company or confirmation_details.UNDISCLOSED_EMPLOYER
        if not data.get("job_url") and args.get("confirmation_email"):
            extracted = confirmation_links.extract_confirmation_link(args["confirmation_email"])
            if extracted.job_url:
                data["job_url"] = extracted.job_url
                if not data.get("source") or data["source"] == "OTHER":
                    data["source"] = extracted.source
        item = applications.create_application(session, AgentApplicationCreate.model_validate(data), settings=settings, **actor)
        application_id = item.id
        result = ApplicationRead.model_validate(item).model_dump(mode="json")
        topic = "application.created"
    elif operation == "update_application":
        item = applications.update_application(session, application_id, AgentApplicationUpdate.model_validate(args["changes"]), settings=settings, **actor)
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
    elif operation == "check_posting_status":
        checker = PostingChecker(browser_fallback=render_with_playwright if settings.posting_playwright_fallback else None)
        result = posting_service.check_application_posting(session, application_id, checker, actor_type=ActorType.AGENT).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "get_followup_request":
        result = work.ai_request(session, application_id, args["followup_id"], settings)
    elif operation == "revise_followup":
        changes = FollowUpUpdate.model_validate(args["changes"])
        if changes.expected_revision is None:
            raise ValueError("expected_revision is required when revising a prepared message")
        if set(changes.model_fields_set) - {"subject", "body", "instructions", "customization", "expected_revision"}:
            raise ValueError("This operation only revises message content and instructions")
        item = work.update_followup(session, application_id, args["followup_id"], changes, settings=settings, **actor)
        result = FollowUpRead.model_validate(item).model_dump(mode="json")
        topic = "followup.updated"
    elif operation == "report_followup_result":
        result = followup_ai.report(session, application_id, args["followup_id"],
            followup_ai.FollowUpResult.model_validate(args["result"]), settings,
            actor_type=ActorType.AGENT, actor_reference=f"agent:{token_fingerprint[:16]}" if token_fingerprint else "agent-token")
        topic = "followup.updated"
    elif operation == "create_note":
        item = work.create_note(session, application_id, NoteCreate.model_validate(args["note"]), **actor)
        result = NoteRead.model_validate(item).model_dump(mode="json")
        topic = "application.updated"
    elif operation == "create_followup":
        item = work.create_followup(session, application_id, FollowUpCreate.model_validate(args["followup"]), settings, **actor)
        result = FollowUpRead.model_validate(item).model_dump(mode="json")
        topic = "followup.updated"
    elif operation == "mark_followup_sent":
        if not isinstance(args.get('expected_revision'), int) or args['expected_revision'] < 1:
            raise ValueError('expected_revision is required when marking a follow-up sent')
        item = work.update_followup(session, application_id, args["followup_id"], FollowUpUpdate(status="SENT", expected_revision=args['expected_revision']), settings=settings, **actor)
        result = FollowUpRead.model_validate(item).model_dump(mode="json")
        topic = "followup.updated"
    elif operation == "draft_followup":
        data = {key: args[key] for key in ('content', 'expected_revision', 'operation_id') if key in args}
        result = integrations.draft_followup(session, application_id, args["followup_id"], integrations.DraftRequest.model_validate(data), mail_provider or integrations.DisconnectedMailProvider(), **actor).model_dump(mode="json")
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
