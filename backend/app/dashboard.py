from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, ApplicationStatus, FollowUp, FollowUpStatus, Interview, Task, TaskStatus, TimelineEvent, utc_now


def summary(application: Application) -> dict:
    return {"id": application.id, "job_title": application.job_title, "company": application.company}


def dashboard(session: Session) -> dict:
    now = utc_now()
    horizon = now + timedelta(days=7)
    active = session.scalar(select(func.count()).select_from(Application).where(Application.deleted_at.is_(None), Application.status != ApplicationStatus.CLOSED)) or 0

    task_rows = session.execute(
        select(Task, Application).join(Application).where(
            Application.deleted_at.is_(None), Task.status == TaskStatus.PENDING,
            Task.due_at.is_not(None), Task.due_at <= horizon,
        )
    ).all()
    followup_rows = session.execute(
        select(FollowUp, Application).join(Application).where(
            Application.deleted_at.is_(None), FollowUp.status.in_((FollowUpStatus.PENDING, FollowUpStatus.DRAFTED)),
            FollowUp.due_at <= horizon,
        )
    ).all()
    interview_rows = session.execute(
        select(Interview, Application).join(Application).where(
            Application.deleted_at.is_(None), Interview.scheduled_at >= now, Interview.scheduled_at <= horizon,
        )
    ).all()

    upcoming = [
        {"id": task.id, "kind": "TASK", "title": task.title, "due_at": task.due_at, "status": task.status.value, "application": summary(application)}
        for task, application in task_rows
    ] + [
        {"id": item.id, "kind": "FOLLOWUP", "title": f"Follow-up #{item.sequence_number}", "due_at": item.due_at, "status": item.status.value, "application": summary(application)}
        for item, application in followup_rows
    ] + [
        {"id": item.id, "kind": "INTERVIEW", "title": f"{item.type.value.title()} interview", "due_at": item.scheduled_at, "status": "SCHEDULED", "application": summary(application)}
        for item, application in interview_rows
    ]
    upcoming.sort(key=lambda item: (item["due_at"], item["kind"], item["id"]))
    due_followups = [item for item in upcoming if item["kind"] == "FOLLOWUP" and item["due_at"] >= now]
    overdue_followups = [item for item in upcoming if item["kind"] == "FOLLOWUP" and item["due_at"] < now]

    activity_rows = session.execute(
        select(TimelineEvent, Application).join(Application).where(Application.deleted_at.is_(None))
        .order_by(TimelineEvent.created_at.desc(), TimelineEvent.id.desc()).limit(10)
    ).all()
    recent = [{
        "id": event.id, "event_type": event.event_type, "summary": event.summary,
        "actor_type": event.actor_type.value, "created_at": event.created_at, "application": summary(application),
    } for event, application in activity_rows]

    return {
        "counts": {
            "active_applications": active,
            "tasks_due": sum(task.due_at >= now for task, _ in task_rows),
            "tasks_overdue": sum(task.due_at < now for task, _ in task_rows),
            "followups_due": sum(item.due_at >= now for item, _ in followup_rows),
            "followups_overdue": sum(item.due_at < now for item, _ in followup_rows),
            "upcoming_interviews": len(interview_rows),
        },
        "upcoming": upcoming,
        "due_followups": due_followups,
        "overdue_followups": overdue_followups,
        "recent_activity": recent,
    }
