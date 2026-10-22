"""Shared synthetic data and credential stores; never access a real workspace."""
from app.google_connection import GoogleConnectionError


class MemorySecrets:
    def __init__(self):
        self.values = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise GoogleConnectionError('Credential store locked')

    def get(self, key):
        self._check()
        return self.values.get(key)

    def put(self, key, value):
        self._check()
        self.values[key] = dict(value)

    def delete(self, key):
        self._check()
        self.values.pop(key, None)


def create_application(client, **changes):
    response = client.post('/api/applications', json={
        'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-01',
        'email_reference': 'message-123', **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


def prepare_followup(client):
    app = create_application(client, contact_email='recruiter@example.com')
    item = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    return app, item, f"/api/applications/{app['id']}/followups/{item['id']}"


def activate_agent(client):
    token = client.post('/api/settings/agent/token').json()['token']
    assert client.put('/api/settings/agent/permissions', json={'read': True, 'draft': True, 'tasks': True}).status_code == 200
    assert client.post('/api/agent/tools/get_tracker_info', headers={'Authorization': f'Bearer {token}'}, json={}).status_code == 200
    return token


def save_settings(client, **changes):
    values = client.get('/api/settings/general').json()
    revision = values.pop('revision')
    response = client.put('/api/settings/general', json={**values, **changes, 'expected_revision': revision})
    assert response.status_code == 200, response.text
    return response.json()
