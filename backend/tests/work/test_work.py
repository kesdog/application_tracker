import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FollowUp, Note, Task, utc_now


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


@pytest.mark.parametrize('kind,payload', [('notes', {'content': 'Note'}), ('tasks', {'title': 'Task'}), ('followups', {})])
def test_children_are_scoped_and_require_parent(client, path, kind, payload):
    assert client.post('/api/applications/missing/' + kind, json=payload).status_code == 404
    created = client.post(path + '/' + kind, json=payload).json()
    other = create_application(client)
    assert client.patch(other + '/' + kind + '/' + created['id'], json={}).status_code == 404
    assert client.patch(path + '/' + kind + '/missing', json={}).status_code == 404
    other_items = client.get(other + '/work').json()[kind]
    if kind == 'followups':
        assert len(other_items) == 1 and other_items[0]['is_automatic'] is True
        assert len(client.get(path + '/work').json()[kind]) == 2
    else:
        assert other_items == []
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
    items = client.get(path + '/work').json()[kind]
    if kind == 'followups':
        assert len(items) == 1 and items[0]['is_automatic'] is True
    else:
        assert items == []


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
    items = client.get(path + '/work').json()[kind]
    if kind == 'followups':
        assert len(items) == 2 and items[0]['is_automatic'] is True and items[1] == original
    else:
        assert items == [original]
