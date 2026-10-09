import asyncio
from datetime import timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.config import Settings
from app.main import create_app
from app.models import utc_now
from app.scheduler import ReminderScheduler

def make_client(tmp_path):
    return TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None)))


def application(client, **extra):
    response = client.post("/api/applications", json={
        "job_title": "Engineer", "company": "Example", "date_applied": "2026-09-25",
        "email_reference": "Message 123", **extra,
    })
    assert response.status_code == 201
    return response.json()["id"]


def test_scheduler_classifies_work_without_mutation(tmp_path):
    with make_client(tmp_path) as client:
        application_id = application(client, phone_number="+33612345678", max_followup_suggestions=0)
        past = (utc_now() - timedelta(days=1)).replace(tzinfo=timezone.utc).isoformat()
        future = (utc_now() + timedelta(days=1)).replace(tzinfo=timezone.utc).isoformat()
        client.post(f"/api/applications/{application_id}/followups", json={"channel": "PHONE", "due_at": past})
        client.post(f"/api/applications/{application_id}/tasks", json={"title": "Call", "due_at": future})
        reminder = ReminderScheduler(client.app.state.engine)
        result = asyncio.run(reminder.refresh())
        assert len(result["overdue_followups"]) == 1
        assert len(result["due_tasks"]) == 1
        with Session(client.app.state.engine) as session:
            from app.models import FollowUp, Task
            assert session.query(FollowUp).filter(FollowUp.is_automatic.is_(False)).one().status.value == "PREPARED"
            assert session.query(Task).one().status.value == "PENDING"
