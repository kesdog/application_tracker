from contextlib import asynccontextmanager
import asyncio
import logging
import threading
from datetime import datetime

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import uvicorn

from app import __version__
from app.config import Settings
from app.database import create_database, migrate_database
from app import applications
from app import activity
from app import dashboard as dashboard_service
from app import documents
from app import exports
from app import interviews
from app import work
from app import agent_auth, agent_errors, agent_ops, integrations, invalidation, posting_service, posting_review, scheduler
from app.posting_checker import PostingChecker, render_with_playwright
from app.interview_schemas import InterviewContext, InterviewCreate, InterviewListItem, InterviewRead, InterviewUpdate, TaskListItem
from app.activity_schemas import TimelineEntryCreate, TimelineEntryUpdate, TimelineEventRead, TimelineRead, UndoRead
from app.dashboard_schemas import DashboardRead
from app.document_schemas import DocumentRead
from app.models import DocumentType
from app.work_schemas import FollowUpCreate, FollowUpRead, FollowUpUpdate, NoteCreate, NoteRead, NoteUpdate, TaskCreate, TaskRead, TaskUpdate, WorkRead
from app.schemas import ApplicationCreate, ApplicationFilters, ApplicationRead, ApplicationUpdate, ContactValidation, PostingCheckRead
from sqlalchemy.orm import Session as DatabaseSession
from app import followup_templates, followup_reminders, human_auth, push
from sqlalchemy import select, func, or_


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


def create_app(
    settings: Settings | None = None,
    mail_provider: integrations.MailProvider | None = None,
    calendar_provider: integrations.CalendarProvider | None = None,
    push_sender=None,
) -> FastAPI:
    settings = settings or Settings()
    mail_provider = mail_provider or integrations.DisconnectedMailProvider()
    calendar_provider = calendar_provider or integrations.DisconnectedCalendarProvider()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_database(settings.app_data_dir)
        application.state.engine = engine
        reminders = None
        reminder_task = None
        posting_checks = None
        posting_task = None
        phone_push = None
        push_task = None
        try:
            migrate_database(engine)
            with Session(engine) as session:
                applications.ensure_submission_events(session)
                work.ensure_initial_followups(session, settings)
            reminders = scheduler.ReminderScheduler(engine)
            await reminders.refresh()
            application.state.reminders = reminders
            reminder_task = asyncio.create_task(reminders.run())
            posting_checks = scheduler.PostingCheckScheduler(engine, settings)
            application.state.posting_checks = posting_checks
            posting_task = asyncio.create_task(posting_checks.run())
            phone_push = push.PushScheduler(engine, settings, sender=push_sender)
            push_task = asyncio.create_task(phone_push.run())
            yield
        finally:
            if phone_push is not None and push_task is not None:
                phone_push.stop.set()
                await push_task
            if reminders is not None and reminder_task is not None:
                reminders.stop.set()
                await reminder_task
            if posting_checks is not None and posting_task is not None:
                posting_checks.stop.set()
                await posting_task
            engine.dispose()

    hosted = settings.app_mode == "hosted"
    application = FastAPI(title="Application Tracker", version=__version__, lifespan=lifespan,
                          docs_url=None if hosted else "/docs", redoc_url=None if hosted else "/redoc", openapi_url=None if hosted else "/openapi.json")
    application.state.settings = settings
    application.state.mail_provider = mail_provider
    application.state.calendar_provider = calendar_provider
    password_slots = threading.BoundedSemaphore(2)

    @application.middleware("http")
    async def protect_human_routes(request: Request, call_next):
        local = request.client is None or request.client.host in {"127.0.0.1", "::1", "testclient"}
        if not hosted and not local and not request.url.path.startswith("/api/agent/"):
            return JSONResponse(status_code=403, content={"detail": "Local access required"})
        path = request.url.path
        if hosted and path != "/api/health":
            try:
                human_auth.check_transport(request, settings)
                public = path in {"/api/auth/session", "/api/auth/login"}
                if path.startswith("/api/") and not path.startswith("/api/agent/") and not public:
                    token = request.cookies.get(human_auth.COOKIE)
                    if not await asyncio.to_thread(human_auth.authenticated, application.state.engine, settings, token):
                        raise HTTPException(401, "Sign in to your workspace")
                    if request.method not in {"GET", "HEAD", "OPTIONS"}:
                        human_auth.require_origin(request, settings)
                        import hmac
                        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), human_auth.csrf_token(token)):
                            raise HTTPException(403, "Refresh the page before saving; the security token is missing or invalid")
            except HTTPException as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
                response.headers["Cache-Control"] = "no-store"
                return response
        response = await call_next(request)
        if hosted:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
        if path.startswith("/api/") or path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(applications.ApplicationNotFound)
    async def not_found(_request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(applications.InvalidApplication)
    async def invalid_application(_request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(followup_templates.RevisionConflict)
    async def revision_conflict(_request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(activity.InvalidActor)
    async def invalid_actor(_request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @application.exception_handler(activity.UndoUnavailable)
    async def undo_unavailable(_request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(agent_errors.AgentApiError)
    async def agent_error(_request, exc):
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    def get_session():
        with Session(application.state.engine) as session:
            yield session

    def local_only(request: Request):
        if not hosted and request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(status_code=403, detail="Local access required")

    @application.get("/api/auth/session")
    def human_session(request: Request):
        if not hosted:
            return {"enabled": False, "authenticated": True, "csrf_token": None}
        token = request.cookies.get(human_auth.COOKIE)
        valid = human_auth.authenticated(application.state.engine, settings, token)
        return {"enabled": True, "authenticated": valid, "csrf_token": human_auth.csrf_token(token) if valid else None}

    @application.post("/api/auth/login")
    def human_login(data: human_auth.LoginInput, request: Request, response: Response):
        if not hosted:
            raise HTTPException(404, "Hosted sign-in is not enabled")
        human_auth.require_origin(request, settings)
        if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
            raise HTTPException(415, "Use a JSON sign-in request")
        human_auth.record_attempt(application.state.engine, request.client.host if request.client else "unknown")
        if not password_slots.acquire(blocking=False):
            raise HTTPException(429, "Sign-in is busy. Try again shortly.", headers={"Retry-After": "2"})
        try:
            if not human_auth.verify_password(data.password, settings.app_password_hash.get_secret_value()):
                raise HTTPException(401, "Incorrect workspace password")
        finally:
            password_slots.release()
        token = human_auth.create_session(application.state.engine, settings, request.cookies.get(human_auth.COOKIE))
        response.set_cookie(human_auth.COOKIE, token, max_age=settings.app_session_hours * 3600, secure=True, httponly=True, samesite="strict", path="/")
        return {"enabled": True, "authenticated": True, "csrf_token": human_auth.csrf_token(token)}

    @application.post("/api/auth/logout")
    def human_logout(request: Request, response: Response):
        if hosted:
            human_auth.revoke(application.state.engine, request.cookies.get(human_auth.COOKIE))
        response.delete_cookie(human_auth.COOKIE, secure=True, httponly=True, samesite="strict", path="/")
        return {"authenticated": False}

    @application.get("/api/settings/general")
    def general_settings(session: Session = Depends(get_session)):
        result = followup_templates.current_settings(session, settings)
        session.commit()
        return result

    @application.put("/api/settings/general")
    def save_general_settings(data: followup_templates.GeneralSettingsInput, session: Session = Depends(get_session)):
        try:
            return followup_templates.save_settings(session, data, settings)
        except followup_templates.RevisionConflict:
            raise
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.get("/api/followups/variables")
    def template_variables():
        return followup_templates.variables()

    @application.post("/api/followups/preview")
    def preview_template(data: followup_templates.PreviewInput, session: Session = Depends(get_session)):
        general = followup_templates.current_settings(session, settings)
        general.update(data.customization.model_dump(exclude_none=True))
        if data.application_id:
            app = applications.get_application(session, data.application_id)
            values = followup_templates.context_values(session, app, None, general)
        else:
            values = {v["key"]: "" for v in followup_templates.variables()}
            values.update(company_name="Example Company", position_name="Software Engineer", date_applied=datetime.now().date().isoformat(),
                          signature=general["signature"], language=general["language"], tone=general["tone"], followup_number="1")
        return {"subject": followup_templates.render(data.subject, values), "body": followup_templates.render(data.body, values), "variables": values}

    @application.get("/api/followups")
    def followup_queue(page: int = 1, page_size: int = 20, status: str = "", q: str = "", archived: bool = False,
                       paused: bool | None = None, due: str = "", session: Session = Depends(get_session)):
        from app.models import FollowUp, Application, FollowUpStatus, utc_now
        if page < 1 or not 1 <= page_size <= 100 or status not in ("", "PREPARED", "READY", "SENT") or due not in ("", "overdue", "upcoming"):
            raise HTTPException(422, "Invalid follow-up filter or pagination")
        query = select(FollowUp, Application).join(Application).where(Application.deleted_at.is_(None))
        query = query.where(FollowUp.archived_at.is_not(None) if archived else FollowUp.archived_at.is_(None))
        if status:
            query = query.where(FollowUp.status == FollowUpStatus(status))
        elif not archived:
            query = query.where(FollowUp.status != FollowUpStatus.SENT, Application.status != "CLOSED")
        if paused is not None:
            query = query.where(Application.followup_paused == paused)
        if due:
            query = query.where(FollowUp.due_at < utc_now() if due == "overdue" else FollowUp.due_at >= utc_now())
        if q:
            query = query.where(or_(Application.company.contains(q, autoescape=True), Application.job_title.contains(q, autoescape=True)))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.execute(query.order_by(FollowUp.due_at, FollowUp.id).offset((page - 1) * page_size).limit(page_size)).all()
        return {"total": total, "page": page, "page_size": page_size, "items": [
            {**FollowUpRead.model_validate(item).model_dump(mode="json"), "application": ApplicationRead.model_validate(app).model_dump(mode="json")}
            for item, app in rows]}

    @application.get("/api/followups/notices")
    def reminder_notices(session: Session = Depends(get_session)):
        followup_reminders.synchronize(session)
        return followup_reminders.notices(session)

    @application.get("/api/settings/notifications")
    def phone_notification_status(session: Session = Depends(get_session)):
        return push.status(session, settings)

    @application.post("/api/settings/notifications/devices", status_code=201)
    def enable_phone_notifications(data: push.SubscriptionInput, session: Session = Depends(get_session)):
        return push.subscribe(session, settings, data)

    @application.delete("/api/settings/notifications/devices/{device_id}", status_code=204)
    def remove_phone_notifications(device_id: str, session: Session = Depends(get_session)):
        push.remove(session, device_id)
        return Response(status_code=204)

    @application.post("/api/settings/notifications/devices/{device_id}/test", status_code=202)
    def test_phone_notifications(device_id: str, session: Session = Depends(get_session)):
        return push.test_notification(session, settings, device_id)

    @application.get("/api/applications/{application_id}/followups/{followup_id}/calendar.ics")
    def followup_calendar(application_id: str, followup_id: str, session: Session = Depends(get_session)):
        parent = applications.get_application(session, application_id)
        from app.models import FollowUp, FollowUpStatus, ApplicationStatus
        item = work.child(session, FollowUp, application_id, followup_id)
        if item.status == FollowUpStatus.SENT or item.archived_at or parent.status == ApplicationStatus.CLOSED or parent.followup_paused:
            raise HTTPException(409, "This follow-up is no longer an active reminder")
        origin = settings.app_public_url if settings.app_mode == "hosted" else f"http://{settings.app_host}:{settings.app_port}"
        return Response(content=integrations.followup_calendar_file(parent, item, origin), media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="followup-{item.id}.ics"'})

    @application.post("/api/followups/notices/{notice_id}/read")
    def read_notice(notice_id: str, session: Session = Depends(get_session)):
        from app.models import FollowUpNotice, utc_now
        notice = session.get(FollowUpNotice, notice_id)
        if not notice:
            raise HTTPException(404, "Notice not found")
        notice.read_at = utc_now()
        session.commit()
        return {"read": True}

    @application.post("/api/contact-validation", response_model=ContactValidation, dependencies=[Depends(local_only)])
    def validate_contact(data: ContactValidation):
        return data

    def agent_token(authorization: str | None = Header(default=None)) -> str:
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
        with DatabaseSession(application.state.engine) as auth_session:
            if not agent_auth.token_valid(auth_session, token):
                raise agent_errors.AgentApiError("INVALID_TOKEN", "Valid agent bearer token required", 401)
        return token

    @application.get("/api/settings/agent", response_model=agent_auth.AgentSettingsRead, dependencies=[Depends(local_only)])
    def get_agent_settings(session: Session = Depends(get_session)):
        return agent_auth.current_settings(session)

    @application.post("/api/settings/agent/token", response_model=agent_auth.AgentTokenCreated, dependencies=[Depends(local_only)])
    def regenerate_agent_token(session: Session = Depends(get_session)):
        return agent_auth.regenerate(session)

    @application.put("/api/settings/agent/permissions", response_model=agent_auth.AgentSettingsRead, dependencies=[Depends(local_only)])
    def update_agent_permissions(data: agent_auth.PermissionSettings, session: Session = Depends(get_session)):
        try:
            return agent_auth.update_permissions(session, data)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/settings/agent/connection", response_model=agent_auth.AgentConnectionInfo, dependencies=[Depends(local_only)])
    def agent_connection_info():
        address = settings.app_public_url if hosted else f"http://{settings.app_host}:{settings.app_port}"
        remote = f"http://{settings.mcp_host}:{settings.mcp_port}/mcp" if settings.mcp_transport == "streamable-http" else None
        return agent_auth.AgentConnectionInfo(
            local_mcp_command="application-tracker-mcp",
            rest_endpoint=f"{address}/api/agent/",
            mcp_transport=settings.mcp_transport,
            remote_mcp_endpoint=remote,
        )

    @application.post("/api/agent/tools/{operation}")
    def agent_operation(operation: str, args: dict, token: str = Depends(agent_token), session: Session = Depends(get_session)):
        permission = agent_ops.PERMISSION_FOR.get(operation)
        if permission is None:
            raise agent_errors.AgentApiError("VALIDATION_ERROR", "Unknown agent operation", 404)
        if not agent_auth.authorized(session, token, permission):
            raise agent_errors.AgentApiError("PERMISSION_DENIED", f"Agent permission required: {permission}", 403)
        session.rollback()
        try:
            return agent_ops.invoke(
                session, settings, operation, args, mail_provider=mail_provider,
                calendar_provider=calendar_provider,
                token_fingerprint=agent_auth.token_fingerprint(token),
            )
        except Exception as exc:
            raise agent_errors.from_exception(exc) from exc

    @application.get("/api/events", dependencies=[Depends(local_only)])
    async def events(request: Request):
        supplied = request.headers.get("last-event-id")
        cursor = int(supplied) if supplied and supplied.isdecimal() else None
        check = (lambda: human_auth.authenticated(application.state.engine, settings, request.cookies.get(human_auth.COOKIE))) if hosted else None
        return StreamingResponse(invalidation.stream(application.state.engine, cursor, authorized=check), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @application.post("/api/applications", response_model=ApplicationRead, status_code=201)
    def create_application(data: ApplicationCreate, session: Session = Depends(get_session)):
        return applications.create_application(session, data, settings=settings)

    @application.get("/api/applications", response_model=list[ApplicationRead])
    def list_applications(filters: ApplicationFilters = Depends(), session: Session = Depends(get_session)):
        return applications.list_applications(session, filters)

    @application.get("/api/applications/{application_id}", response_model=ApplicationRead)
    def get_application(application_id: str, session: Session = Depends(get_session)):
        return applications.get_application(session, application_id)

    @application.patch("/api/applications/{application_id}", response_model=ApplicationRead)
    def update_application(application_id: str, data: ApplicationUpdate, session: Session = Depends(get_session)):
        return applications.update_application(session, application_id, data, settings=settings)

    @application.post("/api/applications/{application_id}/check-posting", response_model=PostingCheckRead)
    def check_posting(application_id: str, session: Session = Depends(get_session)):
        checker = PostingChecker(browser_fallback=render_with_playwright if settings.posting_playwright_fallback else None)
        result = posting_service.check_application_posting(session, application_id, checker)
        invalidation.publish(session, "application.updated", application_id)
        return result

    @application.get("/api/applications/{application_id}/posting-review")
    def get_posting_review(application_id: str, session: Session = Depends(get_session)):
        return posting_review.review_plan(session, application_id)

    @application.post("/api/applications/{application_id}/posting-review", response_model=PostingCheckRead)
    def record_posting_review(application_id: str, data: posting_review.PostingReviewCreate, session: Session = Depends(get_session)):
        result = posting_review.record_review(session, application_id, data)
        invalidation.publish(session, "application.updated", application_id)
        return result

    @application.delete("/api/applications/{application_id}", status_code=204)
    def delete_application(application_id: str, session: Session = Depends(get_session)):
        applications.delete_application(session, application_id)
        return Response(status_code=204)

    @application.get("/api/applications/{application_id}/documents", response_model=list[DocumentRead])
    def list_documents(application_id: str, session: Session = Depends(get_session)):
        return documents.list_documents(session, application_id)

    @application.post("/api/applications/{application_id}/documents", response_model=DocumentRead, status_code=201)
    def create_document(
        application_id: str,
        document_type: DocumentType = Form(),
        filename: str | None = Form(default=None),
        external_reference: str | None = Form(default=None),
        file: UploadFile | None = File(default=None),
        session: Session = Depends(get_session),
    ):
        return documents.create_document(
            session, application_id, document_type, settings.app_data_dir,
            upload=file, filename=filename, external_reference=external_reference,
        )

    @application.get("/api/applications/{application_id}/documents/{document_id}/content")
    def download_document(application_id: str, document_id: str, session: Session = Depends(get_session)):
        path, filename = documents.uploaded_path(session, application_id, document_id, settings.app_data_dir)
        return FileResponse(path, filename=filename)

    @application.get("/api/applications/{application_id}/timeline", response_model=TimelineRead)
    def get_timeline(application_id: str, session: Session = Depends(get_session)):
        applications.get_application(session, application_id)
        return activity.timeline(session, application_id)

    @application.post("/api/applications/{application_id}/timeline", response_model=TimelineEventRead, status_code=201)
    def create_timeline_entry(application_id: str, data: TimelineEntryCreate, session: Session = Depends(get_session)):
        item = activity.create_timeline_entry(session, application_id, data)
        invalidation.publish(session, "application.updated", application_id)
        return item

    @application.patch("/api/applications/{application_id}/timeline/{event_id}", response_model=TimelineEventRead)
    def update_timeline_entry(application_id: str, event_id: str, data: TimelineEntryUpdate, session: Session = Depends(get_session)):
        item = activity.update_timeline_entry(session, application_id, event_id, data)
        invalidation.publish(session, "application.updated", application_id)
        return item

    @application.post("/api/applications/{application_id}/undo", response_model=UndoRead)
    def undo_last_change(application_id: str, session: Session = Depends(get_session)):
        applications.get_application(session, application_id)
        return activity.undo_last(session, application_id)

    @application.get("/api/applications/{application_id}/work", response_model=WorkRead)
    def get_work(application_id: str, session: Session = Depends(get_session)):
        return work.get_work(session, application_id, settings)

    @application.post("/api/applications/{application_id}/notes", response_model=NoteRead, status_code=201)
    def create_note(application_id: str, data: NoteCreate, session: Session = Depends(get_session)):
        return work.create_note(session, application_id, data)

    @application.patch("/api/applications/{application_id}/notes/{item_id}", response_model=NoteRead)
    def update_note(application_id: str, item_id: str, data: NoteUpdate, session: Session = Depends(get_session)):
        return work.update_note(session, application_id, item_id, data)

    @application.post("/api/applications/{application_id}/tasks", response_model=TaskRead, status_code=201)
    def create_task(application_id: str, data: TaskCreate, session: Session = Depends(get_session)):
        return work.create_task(session, application_id, data)

    @application.patch("/api/applications/{application_id}/tasks/{item_id}", response_model=TaskRead)
    def update_task(application_id: str, item_id: str, data: TaskUpdate, session: Session = Depends(get_session)):
        return work.update_task(session, application_id, item_id, data)

    @application.post("/api/applications/{application_id}/followups", response_model=FollowUpRead, status_code=201)
    def create_followup(application_id: str, data: FollowUpCreate, session: Session = Depends(get_session)):
        return work.create_followup(session, application_id, data, settings)

    @application.patch("/api/applications/{application_id}/followups/{item_id}", response_model=FollowUpRead)
    def update_followup(application_id: str, item_id: str, data: FollowUpUpdate, session: Session = Depends(get_session)):
        return work.update_followup(session, application_id, item_id, data, settings=settings)

    @application.get("/api/applications/{application_id}/followups/{item_id}/proposal")
    def message_proposal(application_id: str, item_id: str, latest: bool = True, session: Session = Depends(get_session)):
        return work.proposed_message(session, application_id, item_id, settings, latest=latest)

    class ApplyTemplate(BaseModel):
        expected_revision: int
        latest: bool = True

    @application.post("/api/applications/{application_id}/followups/{item_id}/apply-template", response_model=FollowUpRead)
    def apply_template(application_id: str, item_id: str, data: ApplyTemplate, session: Session = Depends(get_session)):
        return work.apply_message(session, application_id, item_id, settings, data.expected_revision, latest=data.latest)

    @application.get("/api/applications/{application_id}/followups/{item_id}/ai-request")
    def followup_ai_request(application_id: str, item_id: str, session: Session = Depends(get_session)):
        return work.ai_request(session, application_id, item_id, settings)

    @application.post("/api/applications/{application_id}/followups/{item_id}/draft", response_model=integrations.DraftResult)
    def draft_followup(application_id: str, item_id: str, data: integrations.DraftRequest, session: Session = Depends(get_session)):
        return integrations.draft_followup(session, application_id, item_id, data, mail_provider)

    @application.get("/api/applications/{application_id}/interviews", response_model=list[InterviewRead])
    def list_application_interviews(application_id: str, session: Session = Depends(get_session)):
        return interviews.list_application_interviews(session, application_id)

    @application.post("/api/applications/{application_id}/interviews", response_model=InterviewRead, status_code=201)
    def create_interview(application_id: str, data: InterviewCreate, session: Session = Depends(get_session)):
        return interviews.create_interview(session, application_id, data)

    @application.patch("/api/applications/{application_id}/interviews/{interview_id}", response_model=InterviewRead)
    def update_interview(application_id: str, interview_id: str, data: InterviewUpdate, session: Session = Depends(get_session)):
        return interviews.update_interview(session, application_id, interview_id, data)

    @application.delete("/api/applications/{application_id}/interviews/{interview_id}", status_code=204)
    def delete_interview(application_id: str, interview_id: str, session: Session = Depends(get_session)):
        interviews.delete_interview(session, application_id, interview_id)
        return Response(status_code=204)

    @application.get("/api/interviews", response_model=list[InterviewListItem])
    def list_interviews(session: Session = Depends(get_session)):
        return interviews.list_interviews(session)

    @application.get("/api/interviews/{interview_id}", response_model=InterviewRead)
    def get_interview(interview_id: str, session: Session = Depends(get_session)):
        return interviews.get_interview(session, interview_id)

    @application.get("/api/interviews/{interview_id}/context", response_model=InterviewContext)
    def get_interview_context(interview_id: str, session: Session = Depends(get_session)):
        return interviews.interview_context(session, interview_id)

    @application.get("/api/interviews/{interview_id}/calendar.ics")
    def download_interview_calendar(interview_id: str, session: Session = Depends(get_session)):
        interview = interviews.get_interview(session, interview_id)
        parent = applications.get_application(session, interview.application_id)
        return Response(content=integrations.calendar_file(parent, interview), media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="interview-{interview.id}.ics"'})

    @application.get("/api/tasks", response_model=list[TaskListItem])
    def list_tasks(session: Session = Depends(get_session)):
        return interviews.list_tasks(session)

    @application.get("/api/dashboard", response_model=DashboardRead)
    def get_dashboard(session: Session = Depends(get_session)):
        return dashboard_service.dashboard(session)

    @application.get("/api/reminders")
    def get_reminders():
        return application.state.reminders.snapshot

    @application.get("/api/integrations")
    def get_integration_status():
        return {"mail": {"connected": mail_provider.is_connected()}, "calendar": {"connected": calendar_provider.is_connected()}}

    @application.get("/api/exports/applications.csv")
    def export_applications_csv(filters: ApplicationFilters = Depends(), session: Session = Depends(get_session)):
        return Response(
            content=exports.csv_export(session, filters), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="applications.csv"'},
        )

    @application.get("/api/exports/applications.xlsx")
    def export_applications_xlsx(filters: ApplicationFilters = Depends(), session: Session = Depends(get_session)):
        return Response(
            content=exports.xlsx_export(session, filters),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="applications.xlsx"'},
        )

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        try:
            with application.state.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except SQLAlchemyError as exc:
            logging.getLogger(__name__).exception("Database health check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return HealthResponse(status="ok", version=__version__, database="connected")

    if (settings.app_static_dir / "index.html").is_file():
        application.mount("/assets", StaticFiles(directory=settings.app_static_dir / "assets"), name="assets")
        if (settings.app_static_dir / "icons").is_dir():
            application.mount("/icons", StaticFiles(directory=settings.app_static_dir / "icons"), name="icons")

        @application.get("/manifest.webmanifest", include_in_schema=False)
        def web_manifest():
            return FileResponse(settings.app_static_dir / "manifest.webmanifest", media_type="application/manifest+json")

        @application.get("/sw.js", include_in_schema=False)
        def service_worker():
            return FileResponse(settings.app_static_dir / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

        @application.get("/offline.html", include_in_schema=False)
        def offline_page():
            return FileResponse(settings.app_static_dir / "offline.html")

        @application.get("/", include_in_schema=False)
        def frontend_index():
            return FileResponse(settings.app_static_dir / "index.html")

        @application.get("/{path:path}", include_in_schema=False)
        def frontend_fallback(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            return FileResponse(settings.app_static_dir / "index.html")

    return application


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run(app, host=settings.app_host, port=settings.app_port, log_level=settings.log_level, forwarded_allow_ips=settings.app_trusted_proxy_ips)


if __name__ == "__main__":
    run()
