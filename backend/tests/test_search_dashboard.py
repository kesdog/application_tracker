from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client


def create_application(client, *, title="Engineer", company="Example", day="2026-09-25", url=None, **extra):
    body = {
        "job_title": title, "company": company, "date_applied": day,
        "job_url": url, "email_reference": None if url else f"{company} message", **extra,
    }
    response = client.post("/api/applications", json=body)
    assert response.status_code == 201
    return response.json()


def test_combined_application_filters(client):
    matching = create_application(
        client, title="Senior Python Engineer", company="Acme Labs", day="2026-09-20",
        location="Paris", contract_type="Permanent", source="Referral", remote_policy="Hybrid",
        description="Build data platforms", requirements="Python and SQL",
    )
    create_application(client, title="Designer", company="Acme Labs", day="2026-08-01", location="Lyon", source="Board")
    closed = create_application(client, title="Python Engineer", company="Other", day="2026-09-22", location="Paris")
    client.patch(f"/api/applications/{closed['id']}", json={"outcome": "UNSUCCESSFUL"})

    response = client.get("/api/applications", params={
        "q": "data platforms", "status": "SUBMITTED", "company": "acme", "title": "python",
        "location": "par", "contract_type": "perm", "source": "refer", "remote_policy": "hyb",
        "date_from": "2026-09-01", "date_to": "2026-09-30",
    })
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [matching["id"]]
    assert [item["id"] for item in client.get("/api/applications", params={"outcome": "UNSUCCESSFUL"}).json()] == [closed["id"]]


@pytest.mark.parametrize("term", ["senior", "ACME", "paris", "hybrid", "permanent", "referral", "platforms", "sql", "acme message"])
def test_free_text_searches_application_metadata(client, term):
    application = create_application(
        client, title="Senior Engineer", company="Acme", location="Paris", remote_policy="Hybrid",
        contract_type="Permanent", source="Referral", description="Build platforms", requirements="SQL",
    )
    assert [item["id"] for item in client.get("/api/applications", params={"q": term}).json()] == [application["id"]]


def test_document_filter_contract_returns_no_matches_until_documents_exist(client):
    create_application(client)
    assert client.get("/api/applications", params={"document_filename": "resume.pdf"}).json() == []


def test_duplicate_warning_never_blocks_creation(client):
    original = create_application(client, title="Platform Engineer", company="Acme", day="2026-09-01", url="https://example.com/jobs/42/")
    duplicate = create_application(client, title=" platform   engineer ", company="ACME", day="2026-09-20", url="https://example.com/jobs/42")
    assert duplicate["id"] != original["id"]
    assert len(duplicate["duplicate_warnings"]) == 1
    warning = duplicate["duplicate_warnings"][0]
    assert warning["id"] == original["id"]
    assert warning["reasons"] == ["same company and title", "same job URL", "application dates within 30 days"]
    assert len(client.get("/api/applications").json()) == 2


def test_recent_date_alone_is_not_a_duplicate(client):
    create_application(client, title="Engineer", company="One", day="2026-09-24")
    other = create_application(client, title="Designer", company="Two", day="2026-09-25")
    assert other["duplicate_warnings"] == []


def test_dashboard_counts_and_orders_operational_work(client):
    now = datetime.now(timezone.utc)
    active = create_application(client, title="Engineer", company="Active", day=date.today().isoformat())
    closed = create_application(client, title="Designer", company="Closed", day=date.today().isoformat())
    client.patch(f"/api/applications/{closed['id']}", json={"outcome": "UNSUCCESSFUL"})
    root = f"/api/applications/{active['id']}"

    overdue_task = client.post(root + "/tasks", json={"title": "Overdue task", "due_at": (now - timedelta(days=1)).isoformat()}).json()
    due_task = client.post(root + "/tasks", json={"title": "Due task", "due_at": (now + timedelta(days=2)).isoformat()}).json()
    completed = client.post(root + "/tasks", json={"title": "Completed", "due_at": (now - timedelta(days=2)).isoformat()}).json()
    client.patch(root + f"/tasks/{completed['id']}", json={"status": "COMPLETED"})
    client.post(root + "/tasks", json={"title": "Later", "due_at": (now + timedelta(days=10)).isoformat()})

    overdue_followup = client.post(root + "/followups", json={"due_at": (now - timedelta(hours=2)).isoformat()}).json()
    due_followup = client.post(root + "/followups", json={"due_at": (now + timedelta(days=3)).isoformat()}).json()
    sent = client.post(root + "/followups", json={"due_at": (now - timedelta(days=3)).isoformat()}).json()
    client.patch(root + f"/followups/{sent['id']}", json={"status": "SENT"})

    interview = client.post(root + "/interviews", json={"type": "TECHNICAL", "scheduled_at": (now + timedelta(days=1)).isoformat()}).json()
    client.post(root + "/interviews", json={"type": "PHONE", "scheduled_at": (now + timedelta(days=9)).isoformat()})
    client.post(root + "/interviews", json={"type": "HR", "scheduled_at": (now - timedelta(days=1)).isoformat()})

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["counts"] == {
        "active_applications": 1, "followups_due": 2, "followups_overdue": 1,
        "tasks_due": 1, "tasks_overdue": 1, "upcoming_interviews": 1,
    }
    expected = [overdue_task["id"], overdue_followup["id"], interview["id"], due_task["id"], due_followup["id"]]
    assert [item["id"] for item in dashboard["upcoming"]][:5] == expected
    assert len(dashboard["upcoming"]) == 6
    assert dashboard["recent_activity"]
    assert all(item["application"]["id"] in {active["id"], closed["id"]} for item in dashboard["recent_activity"])


def test_dashboard_excludes_soft_deleted_application_activity(client):
    application = create_application(client)
    root = f"/api/applications/{application['id']}"
    client.post(root + "/tasks", json={"title": "Due", "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    client.delete(root)
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["counts"]["active_applications"] == 0
    assert dashboard["upcoming"] == []
    assert dashboard["recent_activity"] == []
