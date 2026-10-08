from datetime import date
from io import BytesIO, StringIO
import csv

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config import PROJECT_ROOT, Settings
from app.database import create_database
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client


def payload(**extra):
    return {"job_title": "Engineer", "company": "Example", "date_applied": "2026-10-09", "job_url": "https://example.com/jobs/1", **extra}


def test_contact_validation_normalizes_without_creating_an_application(client):
    response = client.post("/api/contact-validation", json={"contact_email": " recruiter@EXAMPLE.COM ", "phone_number": "06 12 34 56 78"})
    assert response.status_code == 200
    assert response.json() == {"contact_email": "recruiter@example.com", "phone_number": "+33612345678"}
    assert client.get("/api/applications").json() == []


@pytest.mark.parametrize("contact", [{"contact_email": "not-an-email"}, {"contact_email": "a..b@example.com"}, {"contact_email": "a@localhost"}, {"phone_number": "123"}, {"phone_number": "+33 6 12 34 56 78 ext 123"}])
def test_invalid_contacts_are_rejected_consistently(client, contact):
    assert client.post("/api/contact-validation", json=contact).status_code == 422
    assert client.post("/api/applications", json=payload(**contact)).status_code == 422


def test_optional_contacts_deadline_update_clear_and_undo(client):
    created = client.post("/api/applications", json=payload(contact_name="Recruiter", contact_email="recruiter@example.com", deadline="2026-10-20", deadline_kind="FIRST_ROUND"))
    assert created.status_code == 201
    data = created.json()
    endpoint = f"/api/applications/{data['id']}"
    assert data["contact_email"] == "recruiter@example.com"
    assert data["deadline_kind"] == "FIRST_ROUND"
    assert client.patch(endpoint, json={"contact_email": "bad"}).status_code == 422
    assert client.get(endpoint).json()["contact_email"] == data["contact_email"]
    cleared = client.patch(endpoint, json={"deadline": None})
    assert cleared.status_code == 200
    assert cleared.json()["deadline"] is None
    assert cleared.json()["deadline_kind"] is None
    assert client.post(endpoint + "/undo").status_code == 200
    assert client.get(endpoint).json()["deadline"] == "2026-10-20"
    assert client.get(endpoint).json()["deadline_kind"] == "FIRST_ROUND"


def test_deadline_requires_valid_date_and_known_kind(client):
    for extra in [{"deadline": "2026-02-30"}, {"deadline_kind": "FIRST_ROUND"}, {"deadline": "2026-10-20", "deadline_kind": "UNKNOWN"}]:
        assert client.post("/api/applications", json=payload(**extra)).status_code == 422
    assert client.post("/api/applications", json=payload()).status_code == 201


def test_contacts_and_deadline_export(client):
    client.post("/api/applications", json=payload(contact_email="recruiter@example.com", deadline="2026-10-20", deadline_kind="APPLICATION_CLOSING"))
    rows = list(csv.DictReader(StringIO(client.get("/api/exports/applications.csv").content.decode("utf-8-sig"))))
    assert rows[0]["Contact Email"] == "recruiter@example.com"
    assert rows[0]["Deadline"] == "2026-10-20"
    workbook = load_workbook(BytesIO(client.get("/api/exports/applications.xlsx").content))
    assert workbook.active["S2"].value.date() == date(2026, 10, 20)
    assert workbook.active["S2"].number_format == "yyyy-mm-dd"
    workbook.close()


def test_upgrade_preserves_preexisting_applications(tmp_path):
    engine = create_database(tmp_path)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0014_application_intermediary")
        connection.exec_driver_sql("INSERT INTO applications (id, job_title, company, date_applied, job_url) VALUES ('old', 'Engineer', 'Example', '2026-10-01', 'https://example.com/jobs/old')")
        connection.exec_driver_sql("INSERT INTO tasks (id, application_id, title, status) VALUES ('linked-task', 'old', 'Prepare', 'PENDING')")
    engine.dispose()
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        data = client.get("/api/applications/old").json()
        assert data["job_title"] == "Engineer"
        assert data["deadline"] is None
        assert data["contact_email"] is None
        assert client.get("/api/tasks").json()[0]["id"] == "linked-task"
