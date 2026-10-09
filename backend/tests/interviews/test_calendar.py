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
