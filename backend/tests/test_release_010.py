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


def test_draft_fallback_keeps_mailbox_disconnected_and_never_sends(tmp_path):
    with make_client(tmp_path) as client:
        application_id = application(client, phone_number="06 12 34 56 78")
        followup = client.post(f"/api/applications/{application_id}/followups", json={"channel": "BOTH"}).json()
        result = client.post(f"/api/applications/{application_id}/followups/{followup['id']}/draft", json={"content": "Checking in about the role"})
        assert result.status_code == 200
        assert result.json()["location"] == "LOCAL_NOTE"
        assert "not placed in a mailbox or sent" in result.json()["message"]
        work = client.get(f"/api/applications/{application_id}/work").json()
        assert work["notes"][0]["type"] == "EMAIL_DRAFT"
        assert work["notes"][0]["content"] == "Checking in about the role"
        assert work["followups"][0]["status"] == "DRAFTED"
        assert work["followups"][0]["sent_at"] is None
        assert client.get("/api/integrations").json() == {"mail": {"connected": False}, "calendar": {"connected": False}}


def test_phone_only_cannot_create_email_draft(tmp_path):
    with make_client(tmp_path) as client:
        application_id = application(client, phone_number="+33 6 12 34 56 78")
        followup = client.post(f"/api/applications/{application_id}/followups", json={"channel": "PHONE"}).json()
        result = client.post(f"/api/applications/{application_id}/followups/{followup['id']}/draft", json={"content": "Email text"})
        assert result.status_code == 422
        assert client.get(f"/api/applications/{application_id}/work").json()["notes"] == []


def test_scheduler_classifies_work_without_mutation(tmp_path):
    with make_client(tmp_path) as client:
        application_id = application(client, phone_number="+33612345678")
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
            assert session.query(FollowUp).one().status.value == "PENDING"
            assert session.query(Task).one().status.value == "PENDING"


def test_calendar_file_is_only_generated_on_explicit_download(tmp_path):
    with make_client(tmp_path) as client:
        application_id = application(client)
        interview = client.post(f"/api/applications/{application_id}/interviews", json={
            "type": "TECHNICAL", "scheduled_at": "2026-10-01T14:00:00+02:00", "duration": 45,
        }).json()
        response = client.get(f"/api/interviews/{interview['id']}/calendar.ics")
        assert response.status_code == 200
        assert "text/calendar" in response.headers["content-type"]
        assert "DTSTART:20261001T120000Z" in response.text
        assert "DTEND:20261001T124500Z" in response.text


def test_compiled_frontend_is_served_by_production_backend(tmp_path):
    from app.config import PROJECT_ROOT

    with TestClient(create_app(Settings(app_data_dir=tmp_path, app_static_dir=PROJECT_ROOT / "frontend" / "dist", _env_file=None))) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Application Tracker" in page.text
        assert client.get("/api/health").json()["version"] == "0.10.0"
