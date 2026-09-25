"""Local stdio MCP server backed by the same agent operations as REST.

Set APPLICATION_TRACKER_AGENT_TOKEN in the MCP process environment. The token
is checked against the database for every tool call, so regeneration revokes a
running MCP client's old token immediately.
"""
import os

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from app import agent_auth, agent_ops
from app.config import Settings
from app.database import create_database, migrate_database
from app.schemas import ApplicationCreate, ApplicationFilters, ApplicationUpdate
from app.interview_schemas import InterviewCreate, InterviewUpdate
from app.work_schemas import FollowUpCreate, NoteCreate, TaskCreate


def create_mcp_server(settings: Settings | None = None, token: str | None = None) -> FastMCP:
    settings = settings or Settings()
    engine = create_database(settings.app_data_dir)
    migrate_database(engine)
    credential = token if token is not None else os.environ.get("APPLICATION_TRACKER_AGENT_TOKEN")
    server = FastMCP("Application Tracker", instructions="Manage job applications using the configured agent permissions.")

    def call(operation: str, args: dict):
        with Session(engine) as session:
            permission = agent_ops.PERMISSION_FOR[operation]
            if not agent_auth.token_valid(session, credential):
                raise ValueError("Valid agent token required")
            if not agent_auth.authorized(session, credential, permission):
                raise PermissionError(f"Agent permission required: {permission}")
            session.rollback()
            return agent_ops.invoke(session, settings, operation, args)

    @server.tool()
    def list_applications() -> list:
        """List all non-deleted applications."""
        return call("list_applications", {})

    @server.tool()
    def search_applications(filters: ApplicationFilters) -> list:
        """Search applications with combined filters."""
        return call("search_applications", {"filters": filters.model_dump(exclude_none=True)})

    @server.tool()
    def get_application(application_id: str) -> dict:
        """Get a single application by ID."""
        return call("get_application", {"application_id": application_id})

    @server.tool()
    def find_possible_duplicates(application: ApplicationCreate) -> list:
        """Check an application draft for likely duplicate records."""
        return call("find_possible_duplicates", {"application": application.model_dump(mode="json")})

    @server.tool()
    def create_application(application: ApplicationCreate) -> dict:
        """Create an application and return possible duplicate warnings."""
        return call("create_application", {"application": application.model_dump(mode="json")})

    @server.tool()
    def update_application(application_id: str, changes: ApplicationUpdate) -> dict:
        """Update an application without deleting it."""
        return call("update_application", {"application_id": application_id, "changes": changes.model_dump(mode="json", exclude_unset=True)})

    @server.tool()
    def create_note(application_id: str, note: NoteCreate) -> dict:
        """Create an application note or email draft note."""
        return call("create_note", {"application_id": application_id, "note": note.model_dump(mode="json")})

    @server.tool()
    def create_followup(application_id: str, followup: FollowUpCreate) -> dict:
        """Create a follow-up tracking record."""
        return call("create_followup", {"application_id": application_id, "followup": followup.model_dump(mode="json")})

    @server.tool()
    def mark_followup_sent(application_id: str, followup_id: str) -> dict:
        """Mark an existing follow-up as sent; this does not send email."""
        return call("mark_followup_sent", {"application_id": application_id, "followup_id": followup_id})

    @server.tool()
    def create_task(application_id: str, task: TaskCreate) -> dict:
        """Create a task for an application."""
        return call("create_task", {"application_id": application_id, "task": task.model_dump(mode="json")})

    @server.tool()
    def complete_task(application_id: str, task_id: str) -> dict:
        """Complete an existing application task."""
        return call("complete_task", {"application_id": application_id, "task_id": task_id})

    @server.tool()
    def create_interview(application_id: str, interview: InterviewCreate) -> dict:
        """Schedule an interview."""
        return call("create_interview", {"application_id": application_id, "interview": interview.model_dump(mode="json")})

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


def run() -> None:
    create_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    run()
