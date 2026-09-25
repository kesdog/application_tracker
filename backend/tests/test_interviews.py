from datetime import datetime, timezone

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, Settings
from app.database import create_database
from app.main import create_app
from app.models import Interview


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client


def make_application(client, title="Engineer", company="Example"):
    response = client.post("/api/applications", json={
        "job_title": title, "company": company, "date_applied": "2026-09-24",
        "email_reference": f"{company} message",
    })
    assert response.status_code == 201
    return response.json()


def interview_payload(when="2026-09-28T14:00:00+02:00", **extra):
    return {"type": "TECHNICAL", "scheduled_at": when, **extra}


def test_interview_requires_valid_application_and_foreign_key(client):
    assert client.post("/api/applications/missing/interviews", json=interview_payload()).status_code == 404
    with Session(client.app.state.engine) as session:
        session.add(Interview(application_id="missing", type="PHONE", scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            session.commit()


def test_interview_crud_normalizes_dates_and_scopes_updates(client):
    application = make_application(client)
    base = f"/api/applications/{application['id']}/interviews"
    created = client.post(base, json=interview_payload(
        duration=75, location="Paris", meeting_url="https://meet.example/room",
        interviewer="Sam", email_reference="Thread 42", notes="Prepare systems", result="",
    ))
    assert created.status_code == 201
    item = created.json()
    assert item["scheduled_at"] == "2026-09-28T12:00:00Z"
    assert item["result"] is None and item["created_at"].endswith("Z")
    assert client.get(f"/api/interviews/{item['id']}").json() == item
    assert client.get(base).json() == [item]

    updated = client.patch(f"{base}/{item['id']}", json={
        "type": "FINAL", "scheduled_at": "2026-09-29T09:30:00Z", "result": "Advance",
    })
    assert updated.status_code == 200
    assert updated.json()["type"] == "FINAL" and updated.json()["result"] == "Advance"
    other = make_application(client, "Designer", "Other")
    assert client.patch(f"/api/applications/{other['id']}/interviews/{item['id']}", json={"notes": "wrong"}).status_code == 404
    assert client.delete(f"{base}/{item['id']}").status_code == 204
    assert client.get(f"/api/interviews/{item['id']}").status_code == 404


@pytest.mark.parametrize("payload", [
    {}, {"type": "INVALID", "scheduled_at": "2026-09-28T12:00:00Z"},
    {"type": "PHONE", "scheduled_at": "2026-09-28T12:00:00"},
    {"type": "PHONE", "scheduled_at": "2026-09-28T12:00:00Z", "duration": 0},
    {"type": "PHONE", "scheduled_at": "2026-09-28T12:00:00Z", "meeting_url": "javascript:bad"},
    {"type": "PHONE", "scheduled_at": "2026-09-28T12:00:00Z", "application_id": "other"},
])
def test_invalid_interview_create_is_rejected(client, payload):
    application = make_application(client)
    path = f"/api/applications/{application['id']}/interviews"
    assert client.post(path, json=payload).status_code == 422
    assert client.get(path).json() == []


def test_global_interviews_are_sorted_and_include_application_context(client):
    first = make_application(client, "Engineer", "One")
    second = make_application(client, "Designer", "Two")
    for app, when in ((first, "2026-10-03T10:00:00Z"), (second, "2026-09-29T10:00:00Z"), (first, "2026-10-01T10:00:00Z")):
        assert client.post(f"/api/applications/{app['id']}/interviews", json=interview_payload(when)).status_code == 201
    rows = client.get("/api/interviews").json()
    assert [row["scheduled_at"] for row in rows] == sorted(row["scheduled_at"] for row in rows)
    assert [row["application"]["company"] for row in rows] == ["Two", "One", "One"]


def test_global_tasks_only_include_application_linked_tasks_and_date_order(client):
    one = make_application(client, "Engineer", "One")
    two = make_application(client, "Designer", "Two")
    later = client.post(f"/api/applications/{one['id']}/tasks", json={"title": "Later", "due_at": "2026-10-02T10:00:00Z"}).json()
    sooner = client.post(f"/api/applications/{two['id']}/tasks", json={"title": "Sooner", "due_at": "2026-09-29T10:00:00Z"}).json()
    no_date = client.post(f"/api/applications/{one['id']}/tasks", json={"title": "No date"}).json()
    rows = client.get("/api/tasks").json()
    assert [row["id"] for row in rows] == [sooner["id"], later["id"], no_date["id"]]
    assert [row["application"]["id"] for row in rows] == [two["id"], one["id"], one["id"]]


def test_context_contains_parent_application_notes_tasks_and_document_placeholder(client):
    application = make_application(client)
    path = f"/api/applications/{application['id']}"
    note = client.post(path + "/notes", json={"content": "Interview prep", "type": "INTERVIEW"}).json()
    task = client.post(path + "/tasks", json={"title": "Prepare examples"}).json()
    interview = client.post(path + "/interviews", json=interview_payload()).json()
    context = client.get(f"/api/interviews/{interview['id']}/context")
    assert context.status_code == 200
    assert context.json()["interview"] == interview
    assert context.json()["application"] == application
    assert context.json()["notes"] == [note]
    assert context.json()["tasks"] == [task]
    assert context.json()["documents"] == []


def test_upgrade_from_040_preserves_existing_work_and_adds_interviews(tmp_path):
    engine = create_database(tmp_path)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003_application_work")
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-24', 'Message')"))
        connection.execute(text("INSERT INTO tasks (id, application_id, title, status) VALUES ('task', 'existing', 'Prepare', 'PENDING')"))
    engine.dispose()
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        assert client.get("/api/tasks").json()[0]["id"] == "task"
        assert client.post("/api/applications/existing/interviews", json=interview_payload()).status_code == 201
