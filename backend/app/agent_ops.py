from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app import activity, applications, dashboard, interviews, invalidation, work
from app.config import Settings
from app.models import ActorType
from app.schemas import ApplicationCreate, ApplicationFilters, ApplicationRead, ApplicationUpdate
from app.interview_schemas import InterviewContext, InterviewCreate, InterviewRead, InterviewUpdate
from app.work_schemas import FollowUpCreate, FollowUpRead, FollowUpUpdate, NoteCreate, NoteRead, TaskCreate, TaskRead, TaskUpdate
from app.activity_schemas import TimelineRead
from app.dashboard_schemas import DashboardRead


PERMISSION_FOR = {
    "list_applications": "read", "search_applications": "read", "get_application": "read",
    "find_possible_duplicates": "read", "get_application_timeline": "read", "get_upcoming_items": "read",
    "get_interview_context": "read", "create_application": "create", "update_application": "edit",
    "create_note": "draft", "create_followup": "draft", "mark_followup_sent": "draft",
    "create_task": "tasks", "complete_task": "tasks", "create_interview": "interviews",
    "update_interview": "interviews",
}


def invoke(session: Session, settings: Settings, operation: str, args: dict) -> dict | list:
    if operation not in PERMISSION_FOR:
        raise KeyError(operation)
    application_id = args.get("application_id")
    actor = {"actor_type": ActorType.AGENT, "actor_reference": "agent-token"}
    topic = None

    if operation in {"list_applications", "search_applications"}:
        result = [ApplicationRead.model_validate(item).model_dump(mode="json") for item in applications.list_applications(session, ApplicationFilters.model_validate(args.get("filters", {})))]
    elif operation == "get_application":
        result = ApplicationRead.model_validate(applications.get_application(session, application_id)).model_dump(mode="json")
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
