from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Interview


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
