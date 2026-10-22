from uuid import uuid4


def application(client, **extra):
    response = client.post("/api/applications", json={
        "job_title": "Engineer", "company": "Example", "date_applied": "2026-09-25",
        "email_reference": "Message 123", **extra,
    })
    assert response.status_code == 201
    return response.json()["id"]


def test_draft_fallback_keeps_mailbox_disconnected_and_never_sends(client):
    application_id = application(client, phone_number="06 12 34 56 78")
    followup = client.post(f"/api/applications/{application_id}/followups", json={"channel": "BOTH"}).json()
    endpoint = f"/api/applications/{application_id}/followups/{followup['id']}/draft"
    payload = {"content": "Checking in about the role", "operation_id": str(uuid4()), "expected_revision": followup["revision"]}
    result = client.post(endpoint, json=payload)
    assert result.status_code == 200
    assert result.json()["location"] == "LOCAL_NOTE"
    assert client.post(endpoint, json=payload).json() == result.json()
    assert "not placed in a mailbox or sent" in result.json()["message"]
    work = client.get(f"/api/applications/{application_id}/work").json()
    assert len(work["notes"]) == 1
    assert work["notes"][0]["type"] == "EMAIL_DRAFT"
    assert work["notes"][0]["content"] == "Checking in about the role"
    drafted = next(item for item in work["followups"] if item["id"] == followup["id"])
    assert drafted["status"] == "PREPARED"
    assert drafted["sent_at"] is None
    status = client.get('/api/integrations').json()
    assert status['mail'] == status['calendar'] == {'connected': False}
    assert status['google']['status'] == 'DISCONNECTED'


def test_phone_only_cannot_create_email_draft(client):
    application_id = application(client, phone_number="+33 6 12 34 56 78")
    followup = client.post(f"/api/applications/{application_id}/followups", json={"channel": "PHONE"}).json()
    result = client.post(f"/api/applications/{application_id}/followups/{followup['id']}/draft", json={"content": "Email text"})
    assert result.status_code == 422
    assert client.get(f"/api/applications/{application_id}/work").json()["notes"] == []
