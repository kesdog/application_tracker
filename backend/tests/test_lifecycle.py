from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.applications import InvalidApplication, update_application
from app.config import PROJECT_ROOT, Settings
from app.database import create_database
from app.main import create_app
from app.schemas import ApplicationUpdate


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client


@pytest.fixture
def application(client):
    response = client.post('/api/applications', json={
        'job_title': 'Engineer', 'company': 'Example', 'date_applied': '2026-09-18',
        'job_url': 'https://example.com/jobs/1',
    })
    assert response.status_code == 201
    return response.json()


def path(application):
    return f"/api/applications/{application['id']}"


def test_get_detail_and_partial_edit(client, application):
    assert client.get(path(application)).json() == application
    assert application['posting_status'] == 'UNKNOWN'
    assert application['posting_last_checked_at'] is None
    changes = {'job_title': 'Senior Engineer', 'company': 'New Company', 'location': 'Paris',
               'date_applied': '2026-09-17', 'remote_policy': 'Hybrid', 'contract_type': 'Permanent',
               'source': 'Referral', 'description': 'First line\nSecond line', 'requirements': 'Python'}
    response = client.patch(path(application), json=changes)
    assert response.status_code == 200
    for name, value in changes.items():
        assert response.json()[name] == value
    assert response.json()['job_url'] == application['job_url']
    assert client.get('/api/applications').json() == [response.json()]
    assert client.patch(path(application), json={}).json() == response.json()


def test_transition_to_interview_then_close(client, application):
    assert client.patch(path(application), json={'status': 'INTERVIEW'}).json()['status'] == 'INTERVIEW'
    response = client.patch(path(application), json={'status': 'CLOSED', 'outcome': 'UNSUCCESSFUL'})
    assert response.status_code == 200
    assert response.json()['status'] == 'CLOSED'
    assert response.json()['outcome'] == 'UNSUCCESSFUL'


@pytest.mark.parametrize('outcome', ['SUCCESSFUL', 'UNSUCCESSFUL', 'WITHDRAWN', 'JOB_CANCELLED', 'GHOSTED'])
def test_outcome_alone_closes_application(client, application, outcome):
    response = client.patch(path(application), json={'outcome': outcome})
    assert response.status_code == 200
    assert response.json()['status'] == 'CLOSED'
    assert response.json()['outcome'] == outcome


@pytest.mark.parametrize('status', ['SUBMITTED', 'INTERVIEW'])
def test_reopening_requires_explicit_outcome_clear(client, application, status):
    client.patch(path(application), json={'outcome': 'UNSUCCESSFUL'})
    response = client.patch(path(application), json={'status': status})
    assert response.status_code == 422
    assert 'explicitly clear' in response.json()['detail']
    unchanged = client.get(path(application)).json()
    assert unchanged['status'] == 'CLOSED'
    assert unchanged['outcome'] == 'UNSUCCESSFUL'
    reopened = client.patch(path(application), json={'status': status, 'outcome': None})
    assert reopened.status_code == 200
    assert reopened.json()['status'] == status
    assert reopened.json()['outcome'] is None


def test_close_without_outcome_and_reopen(client, application):
    closed = client.patch(path(application), json={'status': 'CLOSED'}).json()
    assert closed['status'] == 'CLOSED'
    assert closed['outcome'] is None
    assert client.patch(path(application), json={'status': 'SUBMITTED'}).json()['status'] == 'SUBMITTED'


@pytest.mark.parametrize('changes', [
    {'status': 'INTERVIEW', 'outcome': 'SUCCESSFUL'}, {'status': 'SUBMITTED', 'outcome': 'GHOSTED'},
    {'job_url': None}, {'job_url': ' ', 'email_reference': ' '}, {'job_title': None},
    {'company': ' '}, {'date_applied': None}, {'status': None}, {'posting_status': None},
    {'job_url': 'javascript:alert(1)'}, {'status': 'INVALID'}, {'posting_status': 'INVALID'},
    {'posting_last_checked_at': '2026-09-18T12:00:00'}, {'id': 'overwrite'},
])
def test_invalid_edit_does_not_change_any_fields(client, application, changes):
    response = client.patch(path(application), json={'location': 'Must not persist', **changes})
    assert response.status_code == 422
    assert client.get(path(application)).json() == application


def test_replace_source_and_clear_optional_fields(client, application):
    response = client.patch(path(application), json={'job_url': None, 'email_reference': ' Message 123 ', 'location': 'Paris'})
    assert response.status_code == 200
    assert response.json()['job_url'] is None
    assert response.json()['email_reference'] == 'Message 123'
    response = client.patch(path(application), json={'location': ''})
    assert response.json()['location'] is None
    assert response.json()['email_reference'] == 'Message 123'


def test_posting_state_timestamp_and_clear_are_independent_of_lifecycle(client, application):
    response = client.patch(path(application), json={'posting_status': 'CLOSED', 'posting_last_checked_at': '2026-09-18T14:30:00+02:00'})
    assert response.status_code == 200
    assert response.json()['posting_status'] == 'CLOSED'
    assert response.json()['status'] == 'SUBMITTED'
    assert response.json()['posting_last_checked_at'] == '2026-09-18T12:30:00Z'
    assert client.get(path(application)).json()['posting_last_checked_at'] == '2026-09-18T12:30:00Z'
    assert client.patch(path(application), json={'posting_last_checked_at': None}).json()['posting_last_checked_at'] is None


def test_missing_application_returns_404(client):
    assert client.get('/api/applications/missing').status_code == 404
    assert client.patch('/api/applications/missing', json={'status': 'INTERVIEW'}).status_code == 404


def test_service_enforces_lifecycle_without_rest(client, application):
    with Session(client.app.state.engine) as session:
        with pytest.raises(InvalidApplication):
            update_application(session, application['id'], ApplicationUpdate(status='INTERVIEW', outcome='SUCCESSFUL'))


def test_database_rejects_active_outcome(client, application):
    with pytest.raises(IntegrityError):
        with client.app.state.engine.begin() as connection:
            connection.execute(text("UPDATE applications SET outcome = 'SUCCESSFUL' WHERE id = :id"), {'id': application['id']})


def test_migration_preserves_020_records_and_edits_survive_restart(tmp_path):
    config = Config(str(PROJECT_ROOT / 'alembic.ini'))
    engine = create_database(tmp_path)
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0001_applications')
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-18', 'Message 123')"))
    engine.dispose()
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        existing = client.get('/api/applications/existing').json()
        assert existing['posting_status'] == 'UNKNOWN'
        assert existing['email_reference'] == 'Message 123'
        edited = client.patch('/api/applications/existing', json={'outcome': 'SUCCESSFUL', 'posting_status': 'LIVE'}).json()
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/existing').json() == edited
