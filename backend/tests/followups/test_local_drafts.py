from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

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
        drafted = next(item for item in work["followups"] if item["id"] == followup["id"])
        assert drafted["status"] == "PREPARED"
        assert drafted["sent_at"] is None
        assert client.get("/api/integrations").json() == {"mail": {"connected": False}, "calendar": {"connected": False}}


def test_phone_only_cannot_create_email_draft(tmp_path):
    with make_client(tmp_path) as client:
        application_id = application(client, phone_number="+33 6 12 34 56 78")
        followup = client.post(f"/api/applications/{application_id}/followups", json={"channel": "PHONE"}).json()
        result = client.post(f"/api/applications/{application_id}/followups/{followup['id']}/draft", json={"content": "Email text"})
        assert result.status_code == 422
        assert client.get(f"/api/applications/{application_id}/work").json()["notes"] == []
