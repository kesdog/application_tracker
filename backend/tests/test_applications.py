from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect

from app.config import Settings
from app.database import create_database
from app.main import create_app
from app.models import Base


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client


def payload(**overrides):
    return {"job_title": "Engineer", "company": "Example", "date_applied": "2026-09-18", "job_url": "https://example.com/jobs/1", **overrides}


def test_create_with_url_and_defaults(client):
    response = client.post("/api/applications", json=payload())
    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["status"] == "SUBMITTED"
    assert data["outcome"] is None
    assert data["job_url"] == "https://example.com/jobs/1"
    assert client.get("/api/applications").json() == [data]


def test_create_with_email_and_optional_metadata(client):
    data = payload(job_url=" ", email_reference="  Message-ID: example-123  ", location="Paris", remote_policy="Hybrid", contract_type="Permanent", source="Referral", description="Role details", requirements="Python")
    response = client.post("/api/applications", json=data)
    assert response.status_code == 201
    saved = response.json()
    assert saved["job_url"] is None
    assert saved["email_reference"] == "Message-ID: example-123"
    for name in ("location", "remote_policy", "contract_type", "source", "description", "requirements"):
        assert saved[name] == data[name]


@pytest.mark.parametrize("overrides", [
    {"job_url": None}, {"job_url": " ", "email_reference": "\n "},
    {"job_title": " "}, {"company": ""}, {"date_applied": "invalid"},
    {"job_url": "javascript:alert(1)"}, {"job_url": "ftp://example.com"},
    {"status": "CLOSED"}, {"outcome": "SUCCESSFUL"},
])
def test_invalid_create_is_rejected_without_inserting(client, overrides):
    assert client.post("/api/applications", json=payload(**overrides)).status_code == 422
    assert client.get("/api/applications").json() == []


def test_lists_newest_application_date_first(client):
    assert client.get("/api/applications").json() == []
    for day in ("2026-08-01", "2026-09-18", "2026-09-01"):
        assert client.post("/api/applications", json=payload(date_applied=day)).status_code == 201
    assert [item["date_applied"] for item in client.get("/api/applications").json()] == ["2026-09-18", "2026-09-01", "2026-08-01"]


def test_migrates_010_database_and_preserves_records_after_restart(tmp_path):
    # 0.1.0 created an empty SQLite file in WAL mode, without application tables.
    engine = create_database(tmp_path)
    assert inspect(engine).get_table_names() == []
    engine.dispose()
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/applications", json=payload()).json()
    application = create_app(settings)
    with TestClient(application) as client:
        assert client.get("/api/applications").json() == [created]
        with application.state.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0002_application_lifecycle"
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
