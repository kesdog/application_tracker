from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, Settings
from app.database import create_database
from app.main import create_app
from app.models import FollowUp, Note, Task, utc_now
from app.work import create_followup
from app.work_schemas import FollowUpCreate


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, followup_delay_days=7, max_followup_suggestions=2, _env_file=None))) as client:
        yield client


def create_application(client, **extra):
    response = client.post('/api/applications', json={
        'job_title': 'Engineer', 'company': 'Example', 'date_applied': '2026-09-24',
        'email_reference': 'Message 123', **extra,
    })
    assert response.status_code == 201
    return f"/api/applications/{response.json()['id']}"


@pytest.fixture
def path(client):
    return create_application(client)


def test_note_creation_edit_and_author(client, path):
    note = client.post(path + '/notes', json={'content': 'Initial assessment', 'type': 'ASSESSMENT'})
    assert note.status_code == 201
    original = note.json()
    assert original['created_by'] == 'HUMAN'
    assert original['created_at'].endswith('Z')
    edited = client.patch(path + '/notes/' + original['id'], json={'content': 'Updated assessment', 'type': 'EMAIL_DRAFT'})
    assert edited.status_code == 200
    assert edited.json()['content'] == 'Updated assessment'
    assert edited.json()['created_at'] == original['created_at']
    assert edited.json()['updated_at'] >= original['updated_at']
    assert edited.json()['created_by'] == 'HUMAN'
    assert client.get(path + '/work').json()['notes'] == [edited.json()]


def test_task_completion_timestamp_is_stable_and_cleared_on_reopen(client, path):
    task = client.post(path + '/tasks', json={'title': 'Prepare assessment', 'description': 'Practice', 'due_at': '2026-09-25T14:00:00+02:00'})
    assert task.status_code == 201
    assert task.json()['due_at'] == '2026-09-25T12:00:00Z'
    assert task.json()['completed_at'] is None
    url = path + '/tasks/' + task.json()['id']
    completed = client.patch(url, json={'status': 'COMPLETED'}).json()
    assert completed['completed_at'].endswith('Z')
    assert client.patch(url, json={'status': 'COMPLETED'}).json()['completed_at'] == completed['completed_at']
    assert client.patch(url, json={'status': 'PENDING'}).json()['completed_at'] is None
    assert client.patch(url, json={'status': 'CANCELLED'}).json()['status'] == 'CANCELLED'
    edited = client.patch(url, json={'title': 'Updated task', 'description': None, 'due_at': None}).json()
    assert edited['title'] == 'Updated task'
    assert edited['due_at'] is None


def test_followup_defaults_sequences_and_unlimited_manual_creation(client, path):
    before = datetime.now(timezone.utc)
    records = [client.post(path + '/followups', json={}).json() for _ in range(4)]
    assert [item['sequence_number'] for item in records] == [1, 2, 3, 4]
    assert all(item['status'] == 'PENDING' and item['sent_at'] is None for item in records)
    assert all(item['channel'] == 'EMAIL' for item in records)
    due = datetime.fromisoformat(records[0]['due_at'])
    assert before + timedelta(days=7) <= due <= datetime.now(timezone.utc) + timedelta(days=7)
    other = create_application(client)
    assert client.post(other + '/followups', json={}).json()['sequence_number'] == 1
    assert client.get(path + '/work').json()['followups'] == records


def test_phone_and_both_followups_require_application_phone(client, path):
    assert client.post(path + '/followups', json={'channel': 'PHONE'}).status_code == 422
    assert client.patch(path, json={'phone_number': '+33 6 12 34 56 78'}).status_code == 200
    phone = client.post(path + '/followups', json={'channel': 'PHONE'})
    both = client.post(path + '/followups', json={'channel': 'BOTH'})
    assert phone.status_code == both.status_code == 201
    assert phone.json()['channel'] == 'PHONE'
    assert both.json()['channel'] == 'BOTH'


def test_followup_drafted_sent_cancelled_and_timestamp(client, path):
    response = client.post(path + '/followups', json={'due_at': '2026-09-28T12:00:00Z', 'template_reference': 'First reminder'})
    assert response.status_code == 201
    item = response.json()
    url = path + '/followups/' + item['id']
    drafted = client.patch(url, json={'status': 'DRAFTED'}).json()
    assert drafted['status'] == 'DRAFTED'
    assert drafted['sent_at'] is None
    sent = client.patch(url, json={'status': 'SENT'}).json()
    assert sent['sent_at'].endswith('Z')
    assert client.patch(url, json={'status': 'SENT'}).json()['sent_at'] == sent['sent_at']
    cancelled = client.patch(url, json={'status': 'CANCELLED'}).json()
    assert cancelled['status'] == 'CANCELLED' and cancelled['sent_at'] is None
    assert client.patch(url, json={'template_reference': None}).json()['template_reference'] is None
    assert client.get(path).json()['status'] == 'SUBMITTED'


@pytest.mark.parametrize('kind,payload', [('notes', {'content': 'Note'}), ('tasks', {'title': 'Task'}), ('followups', {})])
def test_children_are_scoped_and_require_parent(client, path, kind, payload):
    assert client.post('/api/applications/missing/' + kind, json=payload).status_code == 404
    created = client.post(path + '/' + kind, json=payload).json()
    other = create_application(client)
    assert client.patch(other + '/' + kind + '/' + created['id'], json={}).status_code == 404
    assert client.patch(path + '/' + kind + '/missing', json={}).status_code == 404
    assert client.get(other + '/work').json()[kind] == []
    assert len(client.get(path + '/work').json()[kind]) == 1


def test_missing_parent_work_returns_404(client):
    assert client.get('/api/applications/missing/work').status_code == 404


@pytest.mark.parametrize('item', [
    lambda: Note(application_id='missing', content='Note'),
    lambda: Task(application_id='missing', title='Task'),
    lambda: FollowUp(application_id='missing', sequence_number=1, due_at=utc_now()),
])
def test_database_foreign_keys_reject_orphans(client, item):
    with Session(client.app.state.engine) as session:
        session.add(item())
        with pytest.raises(IntegrityError, match='FOREIGN KEY'):
            session.commit()


@pytest.mark.parametrize('kind,payload', [
    ('notes', {'content': ' '}), ('notes', {'content': 'Note', 'type': 'INVALID'}),
    ('notes', {'content': 'Note', 'created_by': 'AGENT'}),
    ('tasks', {'title': ''}), ('tasks', {'title': 'Task', 'due_at': '2026-09-24T12:00:00'}),
    ('tasks', {'title': 'Task', 'status': 'COMPLETED'}),
    ('followups', {'due_at': 'invalid'}), ('followups', {'sequence_number': 100}),
])
def test_invalid_children_are_not_inserted(client, path, kind, payload):
    assert client.post(path + '/' + kind, json=payload).status_code == 422
    assert client.get(path + '/work').json()[kind] == []


@pytest.mark.parametrize('kind,create,patch', [
    ('notes', {'content': 'Note'}, {'content': None}),
    ('notes', {'content': 'Note'}, {'type': None}),
    ('notes', {'content': 'Note'}, {'application_id': 'other'}),
    ('tasks', {'title': 'Task'}, {'status': None}),
    ('tasks', {'title': 'Task'}, {'completed_at': '2026-09-24T12:00:00Z'}),
    ('followups', {}, {'due_at': None}), ('followups', {}, {'status': 'INVALID'}),
    ('followups', {}, {'sent_at': '2026-09-24T12:00:00Z'}),
])
def test_invalid_patch_does_not_modify_child(client, path, kind, create, patch):
    original = client.post(path + '/' + kind, json=create).json()
    assert client.patch(path + '/' + kind + '/' + original['id'], json=patch).status_code == 422
    assert client.get(path + '/work').json()[kind] == [original]


def test_overrides_and_global_settings(client, path, monkeypatch):
    defaults = client.get(path + '/work').json()
    assert defaults['followup_delay_days'] == 7 and defaults['max_followup_suggestions'] == 2
    assert client.patch(path, json={'followup_delay_days': 0, 'max_followup_suggestions': 0}).status_code == 200
    overridden = client.get(path + '/work').json()
    assert overridden['followup_delay_days'] == 0 and overridden['max_followup_suggestions'] == 0
    before = datetime.now(timezone.utc)
    followup = client.post(path + '/followups', json={})
    assert followup.status_code == 201
    assert before <= datetime.fromisoformat(followup.json()['due_at']) <= datetime.now(timezone.utc)
    assert client.patch(path, json={'followup_delay_days': None, 'max_followup_suggestions': None}).status_code == 200
    assert client.get(path + '/work').json()['followup_delay_days'] == 7
    assert client.patch(path, json={'followup_delay_days': -1}).status_code == 422
    monkeypatch.setenv('FOLLOWUP_DELAY_DAYS', '3')
    monkeypatch.setenv('MAX_FOLLOWUP_SUGGESTIONS', '0')
    config = Settings(_env_file=None)
    assert config.followup_delay_days == 3 and config.max_followup_suggestions == 0


def test_simultaneous_followups_get_unique_sequences(client, path):
    def create_one(_):
        with Session(client.app.state.engine) as session:
            return create_followup(session, path.rsplit('/', 1)[1], FollowUpCreate(), client.app.state.settings).sequence_number
    with ThreadPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(create_one, range(6)))
    assert sorted(sequences) == [1, 2, 3, 4, 5, 6]


def test_upgrade_from_030_and_work_persists_after_restart(tmp_path):
    engine = create_database(tmp_path)
    config = Config(str(PROJECT_ROOT / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0002_application_lifecycle')
        connection.execute(text("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('existing', 'Engineer', 'Example', '2026-09-24', 'Message 123')"))
    engine.dispose()
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/existing').json()['followup_delay_days'] is None
        for kind, payload in [('notes', {'content': 'Assessment'}), ('tasks', {'title': 'Prepare'}), ('followups', {})]:
            assert client.post('/api/applications/existing/' + kind, json=payload).status_code == 201
        original = client.get('/api/applications/existing/work').json()
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/existing/work').json() == original
