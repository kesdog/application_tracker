"""Two real FastAPI lifespans, independent SQLite/auth stores and Drive HTTP APIs."""
from contextlib import ExitStack
import time

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.google_connection import SCOPES
from app.models import ExternalConnection, utc_now
from app.sync.models import SyncWorkspace
from sync_support import MemorySecrets
from http_drive import DriveHttpStore


@pytest.fixture
def http_replicas(tmp_path):
    remote, peers = DriveHttpStore(), []
    with ExitStack() as stack:
        for label, port in (('left', 8000), ('right', 8002)):
            origin = f'http://127.0.0.1:{port}'
            secrets = MemorySecrets()
            secrets.put('google', {'access_token': 'test-' + label, 'refresh_token': 'local-' + label, 'expires_at': time.time() + 3600})
            app = create_app(Settings(app_data_dir=tmp_path / label, app_port=port, google_client_id='synthetic-' + label,
                google_redirect_uri=origin + '/api/connections/google/callback', _env_file=None),
                google_store=secrets, google_transport=httpx.MockTransport(remote.request), sync_background=False)
            client = stack.enter_context(TestClient(app, base_url=origin, headers={'Origin': origin}))
            with Session(app.state.engine) as session:
                session.add(ExternalConnection(id=1, subject='same-verified-subject', scopes=[SCOPES['drive']],
                    status='CONNECTED', secret_reference='google', generation=1, updated_at=utc_now()))
                session.commit()
            peers.append((client, app))
        yield peers, remote


def application(client, company):
    response = client.post('/api/applications', json={'company': company, 'job_title': 'Engineer',
        'date_applied': '2026-10-20', 'job_url': 'https://example.invalid/job', 'email_reference': None,
        'phone_number': None, 'description': 'Desktop-only private description'})
    assert response.status_code == 201, response.text
    return response.json()


def run(client):
    response = client.post('/api/sync/run', json={})
    assert response.status_code == 200, response.text
    return response.json()


def pair(peers):
    left, right = [peer[0] for peer in peers]
    response = left.post('/api/sync/initialize', json={'label': 'Left', 'confirm_encrypted_google_storage': True})
    assert response.status_code == 200, response.text
    assert run(left)['error'] is None
    response = right.post('/api/sync/initialize', json={'label': 'Right', 'confirm_encrypted_google_storage': True,
        'recovery_export': response.json()['recovery_export']})
    assert response.status_code == 200, response.text
    assert run(right)['error'] is None
    return left, right


def test_offline_api_edits_paginated_drive_conflict_resolution_and_private_fields(http_replicas):
    peers, remote = http_replicas
    left, right = pair(peers)
    remote.offline = True
    left_item, right_item = application(left, 'Left offline'), application(right, 'Right offline')
    assert run(left)['error'] and run(right)['error']
    remote.offline = False
    for _ in range(2):
        assert run(left)['error'] is None
        assert run(right)['error'] is None
    entity_id = left_item['id']
    assert right.get('/api/applications/' + entity_id).json()['description'] is None
    assert left.get('/api/applications/' + right_item['id']).status_code == 200
    for client, company in ((left, 'Left conflict'), (right, 'Right conflict')):
        current = client.get('/api/applications/' + entity_id).json()
        response = client.patch('/api/applications/' + entity_id, json={'company': company, 'expected_revision': current['revision']})
        assert response.status_code == 200, response.text
    for _ in range(2):
        assert run(left)['error'] is None
        assert run(right)['error'] is None
    conflict = left.get('/api/sync/conflicts').json()[0]
    final_state = dict(conflict['variants'][0]['state'], company='Human reviewed')
    resolved = left.post(f'/api/sync/conflicts/{conflict["id"]}/resolve', json={'state': final_state, 'expected_heads': conflict['heads']})
    assert resolved.status_code == 200 and resolved.json()['conflicts'] == 0
    for _ in range(2):
        assert run(left)['error'] is None
        assert run(right)['error'] is None
    assert left.get('/api/applications/' + entity_id).json()['description'] == 'Desktop-only private description'
    assert right.get('/api/applications/' + entity_id).json()['company'] == 'Human reviewed'
    assert right.get('/api/sync/status').json()['conflicts'] == 0
    work = right.get('/api/applications/' + entity_id + '/work').json()
    assert len(work['followups']) == 1 and work['followups'][0]['content_available'] is False
    assert remote.upload_bytes > 0 and remote.download_bytes > 0
    assert not any('/gmail/' in path for _, path in remote.calls)


def test_real_adapter_rate_limit_upload_uncertainty_and_cursor_recovery(http_replicas):
    peers, remote = http_replicas
    left, right = pair(peers)
    item = application(left, 'Uncertain upload')
    remote.rate_limit_next = True
    assert run(left)['error']
    assert left.get('/api/connections').json()['google']['capabilities']['drive']
    remote.lose_upload_response = True
    assert run(left)['error']
    assert run(left)['error'] is None
    assert run(right)['error'] is None
    assert right.get('/api/applications/' + item['id']).status_code == 200
    with Session(peers[1][1].state.engine) as session:
        session.get(SyncWorkspace, 1).cursor = 'expired'
        session.commit()
    assert 'expired' in run(right)['error']
    assert run(right)['error'] is None


def test_followup_sequence_resolution_unblocks_both_replicas_without_another_edit(http_replicas):
    peers, _ = http_replicas
    left, right = pair(peers)
    item = application(left, 'Follow-up collision')
    assert run(left)['error'] is None and run(right)['error'] is None
    base = '/api/applications/' + item['id'] + '/followups'
    created = []
    for client in (left, right):
        response = client.post(base, json={'due_at': '2026-11-01T10:00:00Z'})
        assert response.status_code == 201, response.text
        created.append(response.json()['id'])
    # Force the blocked child to be visited before the record whose incoming
    # resolution frees its sequence; convergence must not depend on UUID order.
    if created[0] > created[1]:
        left, right = right, left
    for _ in range(2):
        assert run(left)['error'] is None and run(right)['error'] is None
    conflict = next(item for item in left.get('/api/sync/conflicts').json() if item['reason'] == 'followup_sequence_collision')
    state = dict(conflict['variants'][0]['state'], sequence_number=3)
    response = left.post('/api/sync/conflicts/' + conflict['id'] + '/resolve', json={'state': state, 'expected_heads': conflict['heads']})
    assert response.status_code == 200, response.text
    for _ in range(2):
        assert run(left)['error'] is None and run(right)['error'] is None
    for client in (left, right):
        assert client.get('/api/sync/status').json()['conflicts'] == 0
        followups = client.get('/api/applications/' + item['id'] + '/work').json()['followups']
        assert sorted(row['sequence_number'] for row in followups) == [1, 2, 3]
