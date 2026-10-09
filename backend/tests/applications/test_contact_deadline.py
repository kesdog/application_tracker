from datetime import date
from io import BytesIO, StringIO
import csv

import pytest
from openpyxl import load_workbook


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
