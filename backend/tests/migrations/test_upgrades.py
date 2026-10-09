from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.config import PROJECT_ROOT, Settings
from app.database import create_database
from app.main import create_app
from app.models import Base


def payload(**overrides):
    return {"job_title": "Engineer", "company": "Example", "date_applied": "2026-09-18", "job_url": "https://example.com/jobs/1", **overrides}


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
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == ScriptDirectory.from_config(Config(str(PROJECT_ROOT / "alembic.ini"))).get_current_head()
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_migration_preserves_020_records_and_edits_survive_restart(tmp_path, legacy_database):
    with legacy_database('0001_applications') as connection:
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-18', 'Message 123')"))
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        existing = client.get('/api/applications/existing').json()
        assert existing['posting_status'] == 'UNKNOWN'
        assert existing['email_reference'] == 'Message 123'
        edited = client.patch('/api/applications/existing', json={'outcome': 'SUCCESSFUL', 'posting_status': 'LIVE'}).json()
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/existing').json() == edited


def test_upgrade_from_030_and_work_persists_after_restart(tmp_path, legacy_database):
    with legacy_database('0002_application_lifecycle') as connection:
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-24', 'Message 123')"))
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/existing').json()['followup_delay_days'] is None
        for kind, payload in [('notes', {'content': 'Assessment'}), ('tasks', {'title': 'Prepare'}), ('followups', {})]:
            assert client.post('/api/applications/existing/' + kind, json=payload).status_code == 201
        original = client.get('/api/applications/existing/work').json()
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/existing/work').json() == original


def test_upgrade_from_040_preserves_existing_work_and_adds_interviews(tmp_path, legacy_database):
    with legacy_database("0003_application_work") as connection:
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-24', 'Message')"))
        connection.execute(text("INSERT INTO tasks (id, application_id, title, status) VALUES ('task', 'existing', 'Prepare', 'PENDING')"))
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        assert client.get("/api/tasks").json()[0]["id"] == "task"
        assert client.post("/api/applications/existing/interviews", json={"type": "TECHNICAL", "scheduled_at": "2026-09-28T14:00:00+02:00"}).status_code == 201


def test_upgrade_from_050_preserves_records_and_adds_activity(tmp_path, legacy_database):
    with legacy_database("0004_interviews") as connection:
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-25', 'Message')"))
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        application = client.get("/api/applications/existing")
        assert application.status_code == 200 and application.json()["deleted_at"] is None
        initial_timeline = client.get("/api/applications/existing/timeline").json()
        assert initial_timeline["undo_available"] is False
        assert {event["event_type"] for event in initial_timeline["events"]} == {"APPLICATION_SUBMITTED", "FOLLOWUP_CREATED"}
        assert client.patch("/api/applications/existing", json={"status": "INTERVIEW"}).status_code == 200
        assert client.get("/api/applications/existing/timeline").json()["events"][0]["event_type"] == "STATUS_CHANGED"


def test_upgrade_preserves_preexisting_applications(tmp_path, legacy_database):
    with legacy_database("0014_application_intermediary") as connection:
        connection.exec_driver_sql("INSERT INTO applications (id, job_title, company, date_applied, job_url) VALUES ('old', 'Engineer', 'Example', '2026-10-01', 'https://example.com/jobs/old')")
        connection.exec_driver_sql("INSERT INTO tasks (id, application_id, title, status) VALUES ('linked-task', 'old', 'Prepare', 'PENDING')")
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        data = client.get("/api/applications/old").json()
        assert data["job_title"] == "Engineer"
        assert data["deadline"] is None
        assert data["contact_email"] is None
        assert client.get("/api/tasks").json()[0]["id"] == "linked-task"


def test_migration_preserves_legacy_followups_drafts_and_child_records(tmp_path, legacy_database):
    with legacy_database('0015_contact_and_deadline') as connection:
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('old', 'Engineer', 'Example', '2026-10-01', 'Mail 1')"))
        for index, state in enumerate(('PENDING', 'DRAFTED', 'SENT', 'CANCELLED'), 1):
            connection.execute(text("INSERT INTO followups (id, application_id, sequence_number, due_at, status, sent_at) VALUES (:id, 'old', :seq, '2026-10-08 09:00:00', :state, :sent)"),
                               {'id': f'old-{index}', 'seq': index, 'state': state, 'sent': '2026-10-09 10:00:00' if state == 'SENT' else None})
        connection.execute(text("INSERT INTO notes (id, application_id, content, type, created_by, created_at, updated_at) VALUES ('note', 'old', 'Legacy draft', 'EMAIL_DRAFT', 'HUMAN', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO timeline_events (id, application_id, event_type, actor_type, summary, metadata, created_at) VALUES ('event', 'old', 'NOTE_CREATED', 'HUMAN', 'Draft note', :metadata, CURRENT_TIMESTAMP)"), {'metadata': '{"followup_id":"old-2","note_id":"note"}'})
    config_settings = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(config_settings)) as client:
        work = client.get('/api/applications/old/work').json()
        rows = {r['id']: r for r in work['followups']}
        assert rows['old-2']['body'] == 'Legacy draft'
        assert rows['old-2']['approved_revision'] is None
        assert rows['old-3']['status'] == 'SENT' and rows['old-3']['sent_at'] == '2026-10-09T10:00:00Z'
        assert rows['old-4']['archived_at'] is not None
        assert work['notes'][0]['content'] == 'Legacy draft'
    with TestClient(create_app(config_settings)) as client:
        assert client.get('/api/applications/old/work').json() == work
