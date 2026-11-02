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


def test_pair_phone_requires_explicit_human_action_and_never_caches_recovery(http_replicas):
    peers, remote = http_replicas
    client = peers[0][0]
    assert client.post('/api/sync/pair-phone', json={'confirm_encrypted_google_storage': False}).status_code == 422
    assert client.post('/api/sync/pair-phone', json={'confirm_encrypted_google_storage': True}, headers={'Authorization': 'Bearer agent'}).status_code == 403
    response = client.post('/api/sync/pair-phone', json={'confirm_encrypted_google_storage': True})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['recovery_export'].startswith('ats1.')
    assert response.json()['status']['last_success']
    assert 'recovery_export' not in client.get('/api/sync/status').json()


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
    followup_id = work['followups'][0]['id']
    assert left.get(f'/api/applications/{entity_id}/followups/{followup_id}/versions').json()['versions']
    assert right.get(f'/api/applications/{entity_id}/followups/{followup_id}/versions').status_code == 422
    from sqlalchemy import select
    from app.models import FollowUpMessageVersion
    with Session(peers[1][1].state.engine) as session:
        assert session.scalar(select(FollowUpMessageVersion).where(FollowUpMessageVersion.followup_id == followup_id)) is None
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


def test_human_live_probe_exchanges_through_production_drive_adapters_and_cleanup_does_not_block_sync(http_replicas):
    from uuid import uuid4
    from app.sync.crypto import decode_key, open_envelope, seal
    from app.sync.drive import DriveTransport
    from app.sync.schemas import Batch
    peers, remote = http_replicas
    left, _ = pair(peers)
    existing = set(remote.files)
    phone = DriveTransport(peers[1][1].state.google)
    cursor = phone.start_cursor()
    response = left.post('/api/sync/probe/start', json={'phone_client_id': 'phone.apps.googleusercontent.com'})
    assert response.status_code == 200, response.text
    challenge = response.json()
    assert challenge['desktop_file_id'] in {file['id'] for file in phone.list_files()}
    batch = open_envelope(phone.download(challenge['desktop_file_id']), decode_key(challenge['test_key']), challenge['workspace_id'])
    assert str(batch.batch_id) == challenge['desktop_batch_id']
    observed = set()
    while True:
        files, _, cursor, more = phone.changes(cursor)
        observed.update(file['id'] for file in files)
        if not more:
            break
    assert challenge['desktop_file_id'] in observed
    answer = Batch(workspace_id=challenge['workspace_id'], batch_id=challenge['phone_batch_id'], device_id=uuid4(), kind='ack')
    file_id = phone.upload_immutable(str(answer.batch_id), seal(answer, decode_key(challenge['test_key'])))
    response = left.post('/api/sync/probe/verify', json={'probe_id': challenge['probe_id'], 'phone_file_id': file_id, 'phone_batch_id': str(answer.batch_id)})
    assert response.status_code == 200 and response.json()['verified']
    assert 'test_key' not in left.get('/api/sync/status').text
    assert left.post('/api/sync/probe/cleanup', json={'probe_id': challenge['probe_id']}).json()['cleaned']
    assert set(remote.files) == existing
    assert run(left)['error'] is None


def test_live_probe_rejects_agent_and_wrong_origin_before_creating_files(http_replicas):
    peers, remote = http_replicas
    client = peers[0][0]
    payload = {'phone_client_id': 'phone.apps.googleusercontent.com'}
    assert client.post('/api/sync/probe/start', json=payload, headers={'Authorization': 'Bearer agent'}).status_code == 403
    assert client.post('/api/sync/probe/start', json=payload, headers={'Origin': 'https://other.invalid'}).status_code == 403
    assert not remote.files
