from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.activity import InvalidActor
from app.applications import delete_application
from app.config import PROJECT_ROOT, Settings
from app.database import create_database
from app.main import create_app
from app.models import ActorType, AuditEntry
from app.work import create_note
from app.work_schemas import NoteCreate


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client


def make_application(client, company="Example"):
    response = client.post("/api/applications", json={
        "job_title": "Engineer", "company": company, "date_applied": "2026-09-25",
        "email_reference": f"{company} message",
    })
    assert response.status_code == 201
    return response.json()


def path(application):
    return f"/api/applications/{application['id']}"


def test_application_created_and_status_change_appear_in_timeline(client):
    application = make_application(client)
    initial = client.get(path(application) + "/timeline").json()
    assert initial["undo_available"] is False
    assert initial["events"][0]["event_type"] == "APPLICATION_CREATED"
    assert initial["events"][0]["actor_type"] == "HUMAN"

    assert client.patch(path(application), json={"status": "INTERVIEW"}).status_code == 200
    timeline = client.get(path(application) + "/timeline").json()
    assert timeline["undo_available"] is True
    assert timeline["events"][0]["event_type"] == "STATUS_CHANGED"
    assert "SUBMITTED to INTERVIEW" in timeline["events"][0]["summary"]


def test_actor_identity_is_preserved_for_service_mutations(client):
    application = make_application(client)
    with Session(client.app.state.engine) as session:
        created = create_note(
            session, application["id"], NoteCreate(content="Agent research"),
            actor_type=ActorType.AGENT, actor_reference="agent-7",
        )
        assert created.created_by == "agent-7"
    event = client.get(path(application) + "/timeline").json()["events"][0]
    assert event["event_type"] == "NOTE_ADDED"
    assert event["actor_type"] == "AGENT"
    assert event["actor_reference"] == "agent-7"
    with Session(client.app.state.engine) as session:
        audit = session.scalar(select(AuditEntry).where(AuditEntry.entity_id == created.id))
        assert audit.actor_type == ActorType.AGENT and audit.actor_reference == "agent-7"


def test_undo_restores_application_field_and_cannot_repeat(client):
    application = make_application(client)
    assert client.patch(path(application), json={"status": "INTERVIEW", "location": "Paris"}).status_code == 200
    undone = client.post(path(application) + "/undo")
    assert undone.status_code == 200
    assert undone.json()["entity_type"] == "APPLICATION"
    assert undone.json()["fields"] == ["location", "status"]
    restored = client.get(path(application)).json()
    assert restored["status"] == "SUBMITTED" and restored["location"] is None
    timeline = client.get(path(application) + "/timeline").json()
    assert timeline["events"][0]["event_type"] == "UNDO"
    assert timeline["undo_available"] is False
    assert client.post(path(application) + "/undo").status_code == 409


def test_undo_restores_coupled_task_completion_fields(client):
    application = make_application(client)
    task = client.post(path(application) + "/tasks", json={"title": "Prepare"}).json()
    completed = client.patch(path(application) + f"/tasks/{task['id']}", json={"status": "COMPLETED"}).json()
    assert completed["completed_at"] is not None
    result = client.post(path(application) + "/undo")
    assert result.status_code == 200 and result.json()["fields"] == ["completed_at", "status"]
    restored = client.get(path(application) + "/work").json()["tasks"][0]
    assert restored["status"] == "PENDING" and restored["completed_at"] is None


def test_operational_mutations_create_expected_timeline_events(client):
    application = make_application(client)
    root = path(application)
    client.patch(root, json={"posting_status": "LIVE", "outcome": "SUCCESSFUL"})
    note = client.post(root + "/notes", json={"content": "Assessment"}).json()
    client.patch(root + f"/notes/{note['id']}", json={"content": "Updated assessment"})
    task = client.post(root + "/tasks", json={"title": "Prepare"}).json()
    client.patch(root + f"/tasks/{task['id']}", json={"status": "COMPLETED"})
    followup = client.post(root + "/followups", json={}).json()
    client.patch(root + f"/followups/{followup['id']}", json={"status": "DRAFTED"})
    client.patch(root + f"/followups/{followup['id']}", json={"status": "SENT"})
    interview = client.post(root + "/interviews", json={"type": "PHONE", "scheduled_at": "2026-10-01T10:00:00Z"}).json()
    client.patch(root + f"/interviews/{interview['id']}", json={"type": "FINAL"})
    event_types = {event["event_type"] for event in client.get(root + "/timeline").json()["events"]}
    assert {
        "POSTING_STATUS_CHANGED", "STATUS_CHANGED", "OUTCOME_CHANGED", "NOTE_ADDED", "NOTE_CHANGED",
        "TASK_CREATED", "TASK_COMPLETED", "FOLLOWUP_CREATED", "FOLLOWUP_DRAFTED", "FOLLOWUP_SENT",
        "INTERVIEW_CREATED", "INTERVIEW_CHANGED",
    } <= event_types


def test_soft_delete_excludes_application_and_global_children(client):
    application = make_application(client)
    root = path(application)
    client.post(root + "/tasks", json={"title": "Prepare"})
    client.post(root + "/interviews", json={"type": "PHONE", "scheduled_at": "2026-10-01T10:00:00Z"})
    response = client.delete(root)
    assert response.status_code == 204
    assert client.get(root).status_code == 404
    assert client.get("/api/applications").json() == []
    assert client.get("/api/tasks").json() == []
    assert client.get("/api/interviews").json() == []
    with Session(client.app.state.engine) as session:
        deleted_at = session.execute(text("SELECT deleted_at FROM applications WHERE id=:id"), {"id": application["id"]}).scalar_one()
        assert deleted_at is not None
        audit = session.scalar(select(AuditEntry).where(AuditEntry.application_id == application["id"], AuditEntry.action == "DELETE"))
        assert audit is not None and audit.reversible is False


def test_agent_application_deletion_is_rejected(client):
    application = make_application(client)
    with Session(client.app.state.engine) as session:
        with pytest.raises(InvalidActor, match="Only a human"):
            delete_application(session, application["id"], actor_type=ActorType.AGENT, actor_reference="agent-7")
    assert client.get(path(application)).status_code == 200


def test_upgrade_from_050_preserves_records_and_adds_activity(tmp_path):
    engine = create_database(tmp_path)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0004_interviews")
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-25', 'Message')"))
    engine.dispose()
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        application = client.get("/api/applications/existing")
        assert application.status_code == 200 and application.json()["deleted_at"] is None
        assert client.get("/api/applications/existing/timeline").json() == {"events": [], "undo_available": False}
        assert client.patch("/api/applications/existing", json={"status": "INTERVIEW"}).status_code == 200
        assert client.get("/api/applications/existing/timeline").json()["events"][0]["event_type"] == "STATUS_CHANGED"
