from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import AgentCredential, utc_now


def prepare(client):
    app = client.post('/api/applications', json={'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-01', 'email_reference': 'message-123', 'contact_email': 'recruiter@example.com'}).json()
    item = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    return app, item, f"/api/applications/{app['id']}/followups/{item['id']}"


def activate(client):
    token = client.post('/api/settings/agent/token').json()['token']
    permissions = {'read': True, 'draft': True, 'tasks': True}
    assert client.put('/api/settings/agent/permissions', json=permissions).status_code == 200
    assert client.post('/api/agent/tools/get_tracker_info', headers={'Authorization': f'Bearer {token}'}, json={}).status_code == 200
    return token


def test_requires_actual_agent_use_and_expires_or_revokes_access(client):
    app, item, url = prepare(client)
    assert client.get('/api/followups/agent-status').json() == {'active': False, 'can_draft': False}
    token = client.post('/api/settings/agent/token').json()['token']
    assert client.get('/api/followups/agent-status').json()['active'] is False
    assert client.post(url + '/draft-task', json={'expected_revision': item['revision']}).status_code == 422
    assert client.post('/api/agent/tools/get_tracker_info', headers={'Authorization': 'Bearer invalid'}, json={}).status_code == 401
    assert client.get('/api/followups/agent-status').json()['active'] is False
    token = activate(client)
    assert client.get('/api/followups/agent-status').json() == {'active': True, 'can_draft': True}
    with Session(client.app.state.engine) as session:
        session.get(AgentCredential, 1).last_used_at = utc_now() - timedelta(minutes=16)
        session.commit()
    assert client.get('/api/followups/agent-status').json()['can_draft'] is False
    assert client.post(url + '/draft-task', json={'expected_revision': item['revision']}).status_code == 422
    client.post('/api/agent/tools/get_tracker_info', headers={'Authorization': f'Bearer {token}'}, json={})
    client.put('/api/settings/agent/permissions', json={'read': True, 'draft': False, 'tasks': True})
    assert client.get('/api/followups/agent-status').json() == {'active': True, 'can_draft': False}
    client.post('/api/settings/agent/token')
    assert client.get('/api/followups/agent-status').json()['active'] is False


def test_queues_one_resolved_task_without_changing_followup_status(client):
    app, item, url = prepare(client)
    activate(client)
    saved = client.patch(url, json={'body': 'Hello {company_name}', 'expected_revision': item['revision']}).json()
    result = client.post(url + '/draft-task', json={'expected_revision': saved['revision']})
    assert result.status_code == 200, result.text
    task = result.json()
    assert task['status'] == 'PENDING'
    assert task['title'] == 'AI: Write follow-up #1 to draft'
    assert 'Hello Example' in task['description'] and 'never send email' in task['description']
    assert client.post(url + '/draft-task', json={'expected_revision': saved['revision']}).json()['id'] == task['id']
    work = client.get(f"/api/applications/{app['id']}/work").json()
    assert len(work['tasks']) == 1
    assert work['followups'][0]['status'] == 'PREPARED'
    assert work['followups'][0]['revision'] == saved['revision']
    assert client.post(url + '/draft-task', json={'expected_revision': saved['revision'] - 1}).status_code == 409


def test_resolves_copy_values_and_rejects_missing_fields_or_closed_followups(client):
    app, item, url = prepare(client)
    activate(client)
    saved = client.patch(url, json={'body': '{company_name} — {contact_name} — {unknown}', 'expected_revision': item['revision']}).json()
    result = client.get(url + '/rendered-message').json()
    assert result['body']['text'].startswith('Example — ')
    assert result['body']['missing'] == ['contact_name']
    assert result['body']['unknown'] == ['unknown']
    assert client.post(url + '/draft-task', json={'expected_revision': saved['revision']}).status_code == 422
    saved = client.patch(url, json={'body': 'Hello', 'archived': True, 'expected_revision': saved['revision']}).json()
    assert client.post(url + '/draft-task', json={'expected_revision': saved['revision']}).status_code == 422
    assert client.get(f"/api/applications/{app['id']}/work").json()['tasks'] == []
