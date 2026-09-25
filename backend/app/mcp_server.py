"""Local stdio MCP server backed by the same agent operations as REST.

Set APPLICATION_TRACKER_AGENT_TOKEN in the MCP process environment. The token
is checked against the database for every tool call, so regeneration revokes a
running MCP client's old token immediately.
"""
from contextvars import ContextVar
import json
import os

from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from app import agent_auth, agent_errors, agent_ops
from app.activity_schemas import TimelineEntryCreate, TimelineEntryUpdate
from app.config import Settings
from app.database import create_database, migrate_database
from app.schemas import ApplicationCreate, ApplicationFilters, ApplicationUpdate
from app.interview_schemas import InterviewCreate, InterviewUpdate
from app.work_schemas import FollowUpCreate, NoteCreate, TaskCreate


_request_token: ContextVar[str | None] = ContextVar("mcp_request_token", default=None)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Require the regular generated bearer token for Streamable HTTP requests."""

    def __init__(self, app, engine):
        super().__init__(app)
        self.engine = engine

    async def dispatch(self, request, call_next):
        authorization = request.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else None
        with Session(self.engine) as session:
            valid = agent_auth.token_valid(session, token)
        if not valid:
            return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": "Valid agent bearer token required"}}, headers={"WWW-Authenticate": "Bearer"})
        marker = _request_token.set(token)
        try:
            return await call_next(request)
        finally:
            _request_token.reset(marker)


def create_mcp_server(settings: Settings | None = None, token: str | None = None) -> FastMCP:
    settings = settings or Settings()
    engine = create_database(settings.app_data_dir)
    migrate_database(engine)
    static_token = token if token is not None else os.environ.get("APPLICATION_TRACKER_AGENT_TOKEN")
    server = FastMCP(
        "Application Tracker", instructions="Manage job applications using the configured agent permissions.",
        host=settings.mcp_host, port=settings.mcp_port, streamable_http_path="/mcp",
    )

    def call(operation: str, args: dict):
        credential = _request_token.get() or static_token
        try:
            with Session(engine) as session:
                permission = agent_ops.PERMISSION_FOR[operation]
                if not agent_auth.token_valid(session, credential):
                    raise agent_errors.AgentApiError("INVALID_TOKEN", "Valid agent bearer token required", 401)
                if not agent_auth.authorized(session, credential, permission):
                    raise agent_errors.AgentApiError("PERMISSION_DENIED", f"Agent permission required: {permission}", 403)
                session.rollback()
                return agent_ops.invoke(session, settings, operation, args, token_fingerprint=agent_auth.token_fingerprint(credential))
        except Exception as exc:
            error = agent_errors.from_exception(exc)
            raise ToolError(json.dumps(error.payload())) from exc

    @server.tool()
    def get_tracker_info() -> dict:
        """Check version, permissions, transports, and integration availability before choosing other tools. Read-only; never reveals tokens."""
        return call("get_tracker_info", {})

    @server.tool()
    def list_applications(limit: int = 25, cursor: str | None = None) -> dict:
        """Return a compact, paginated application page. Use next_cursor for another page without loading long descriptions."""
        return call("list_applications", {"limit": limit, "cursor": cursor})

    @server.tool()
    def search_applications(filters: ApplicationFilters, limit: int = 25, cursor: str | None = None) -> dict:
        """Search compact application summaries with combined filters and cursor pagination."""
        return call("search_applications", {"filters": filters.model_dump(exclude_none=True), "limit": limit, "cursor": cursor})

    @server.tool()
    def get_application(application_id: str) -> dict:
        """Get the full application when a compact result needs description or requirements."""
        return call("get_application", {"application_id": application_id})

    @server.tool()
    def get_application_context(application_id: str) -> dict:
        """Get an application's record, work, interviews, documents, recent timeline, and next action in one read-only request."""
        return call("get_application_context", {"application_id": application_id})

    @server.tool()
    def find_possible_duplicates(application: ApplicationCreate) -> list:
        """Check an application draft for likely duplicate records."""
        return call("find_possible_duplicates", {"application": application.model_dump(mode="json")})

    @server.tool()
    def create_application(application: ApplicationCreate, idempotency_key: str | None = None) -> dict:
        """Create an application. An idempotency key makes a retry return the original record instead of creating another."""
        return call("create_application", {"application": application.model_dump(mode="json"), "idempotency_key": idempotency_key})

    @server.tool()
    def update_application(application_id: str, changes: ApplicationUpdate) -> dict:
        """Update an application without deleting it; the change is recorded as agent activity."""
        return call("update_application", {"application_id": application_id, "changes": changes.model_dump(mode="json", exclude_unset=True)})

    @server.tool()
    def check_posting_status(application_id: str) -> dict:
        """Deterministically check a saved job URL and update only posting diagnostics/status. It never changes the application lifecycle."""
        return call("check_posting_status", {"application_id": application_id})

    @server.tool()
    def create_timeline_entry(application_id: str, entry: TimelineEntryCreate) -> dict:
        """Add a manual email timeline event at a verified timestamp. It never changes automatic system history."""
        return call("create_timeline_entry", {"application_id": application_id, "entry": entry.model_dump(mode="json")})

    @server.tool()
    def update_timeline_entry(application_id: str, event_id: str, changes: TimelineEntryUpdate) -> dict:
        """Edit a manual timeline entry. System-created events cannot be edited."""
        return call("update_timeline_entry", {"application_id": application_id, "event_id": event_id, "changes": changes.model_dump(mode="json", exclude_unset=True)})

    @server.tool()
    def create_note(application_id: str, note: NoteCreate, idempotency_key: str | None = None) -> dict:
        """Create an application note; this never sends a message. Use an idempotency key for retry safety."""
        return call("create_note", {"application_id": application_id, "note": note.model_dump(mode="json"), "idempotency_key": idempotency_key})

    @server.tool()
    def create_followup(application_id: str, followup: FollowUpCreate, idempotency_key: str | None = None) -> dict:
        """Create a follow-up record only; it never sends email or calls. Use an idempotency key for retry safety."""
        return call("create_followup", {"application_id": application_id, "followup": followup.model_dump(mode="json"), "idempotency_key": idempotency_key})

    @server.tool()
    def mark_followup_sent(application_id: str, followup_id: str) -> dict:
        """Record an already-sent follow-up. This updates tracker history only and never sends email."""
        return call("mark_followup_sent", {"application_id": application_id, "followup_id": followup_id})

    @server.tool()
    def draft_followup(application_id: str, followup_id: str, content: str) -> dict:
        """Create a draft without sending it. With no mail integration it is saved as a local note."""
        return call("draft_followup", {"application_id": application_id, "followup_id": followup_id, "content": content})

    @server.tool()
    def create_task(application_id: str, task: TaskCreate, idempotency_key: str | None = None) -> dict:
        """Create a task; it does not perform or submit work automatically. Use an idempotency key for retries."""
        return call("create_task", {"application_id": application_id, "task": task.model_dump(mode="json"), "idempotency_key": idempotency_key})

    @server.tool()
    def complete_task(application_id: str, task_id: str) -> dict:
        """Complete an existing application task."""
        return call("complete_task", {"application_id": application_id, "task_id": task_id})

    @server.tool()
    def create_interview(application_id: str, interview: InterviewCreate, idempotency_key: str | None = None) -> dict:
        """Schedule a tracker interview without creating an external calendar event. Use an idempotency key for retries."""
        return call("create_interview", {"application_id": application_id, "interview": interview.model_dump(mode="json"), "idempotency_key": idempotency_key})

    @server.tool()
    def update_interview(application_id: str, interview_id: str, changes: InterviewUpdate) -> dict:
        """Update an interview."""
        return call("update_interview", {"application_id": application_id, "interview_id": interview_id, "changes": changes.model_dump(mode="json", exclude_unset=True)})

    @server.tool()
    def get_interview_context(interview_id: str) -> dict:
        """Get interview details with application, work, and documents."""
        return call("get_interview_context", {"interview_id": interview_id})

    @server.tool()
    def get_application_timeline(application_id: str) -> dict:
        """Get application activity and undo availability."""
        return call("get_application_timeline", {"application_id": application_id})

    @server.tool()
    def get_upcoming_items() -> dict:
        """Get dashboard counts, upcoming work, and recent activity."""
        return call("get_upcoming_items", {})

    return server


def create_mcp_http_app(settings: Settings | None = None):
    """Serve the same FastMCP tool registry over bearer-authenticated HTTP."""
    settings = settings or Settings()
    server = create_mcp_server(settings)
    app = server.streamable_http_app()
    app.add_middleware(BearerTokenMiddleware, engine=create_database(settings.app_data_dir))
    return app


def run() -> None:
    settings = Settings()
    if settings.mcp_transport == "stdio":
        create_mcp_server(settings).run(transport="stdio")
        return
    # Streamable HTTP remains loopback by default. Deployments that change the
    # host need TLS and network controls before exposing bearer credentials.
    uvicorn.run(create_mcp_http_app(settings), host=settings.mcp_host, port=settings.mcp_port, log_level=settings.log_level)


if __name__ == "__main__":
    run()
