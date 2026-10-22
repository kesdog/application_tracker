from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Application
from app.sync.schemas import ApplicationState
from sync_support import create_application

ORIGIN = 'http://127.0.0.1:8000'


def test_setup_requires_local_human_origin_and_explicit_storage_disclosure(replicas, tmp_path):
    factory, transport = replicas
    secrets = type(factory('store-host').secrets)()
    app = create_app(Settings(app_data_dir=tmp_path / 'routes', _env_file=None), sync_transport=transport, sync_store=secrets)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/api/sync/status').json()['initialized'] is False
        payload = {'label': 'Desktop', 'confirm_encrypted_google_storage': True}
        assert client.post('/api/sync/initialize', json=payload).status_code == 403
        assert client.post('/api/sync/initialize', json=payload, headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.post('/api/sync/initialize', json=payload, headers={'Origin': ORIGIN, 'Authorization': 'Bearer agent'}).status_code == 403
        assert client.post('/api/sync/initialize', json={**payload, 'confirm_encrypted_google_storage': False}, headers={'Origin': ORIGIN}).status_code == 422
        setup = client.post('/api/sync/initialize', json=payload, headers={'Origin': ORIGIN})
        assert setup.status_code == 200
        secret = setup.json()['recovery_export']
        assert secret.startswith('ats1.')
        assert secret not in client.get('/api/sync/status').text
        assert 'no-store' in setup.headers['cache-control']
        assert client.post('/api/sync/run', json={}, headers={'Origin': ORIGIN}).json()['error'] is None


def test_imported_messages_are_labelled_and_cannot_be_copied_approved_or_drafted(replicas, tmp_path):
    from datetime import datetime
    from app.models import FollowUp
    factory, remote = replicas
    source = factory('source')
    export = source.initialize('Source')['recovery_export']
    entity_id = create_application(source)
    with Session(source.engine) as session:
        followup = FollowUp(application_id=entity_id, sequence_number=1, due_at=datetime(2026, 11, 1), status='READY', body='Private', subject='Private')
        session.add(followup)
        session.commit()
        followup_id = followup.id
    source.run(manual=True)
    secrets = type(source.secrets)()
    app = create_app(Settings(app_data_dir=tmp_path / 'target', _env_file=None), sync_transport=remote, sync_store=secrets)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = {'Origin': ORIGIN}
        assert client.post('/api/sync/initialize', json={'label': 'Target', 'recovery_export': export,
            'confirm_encrypted_google_storage': True}, headers=headers).status_code == 200
        assert client.post('/api/sync/run', json={}, headers=headers).json()['error'] is None
        work = client.get(f'/api/applications/{entity_id}/work').json()
        item = work['followups'][0]
        assert item['content_available'] is False and item['body'] == ''
        base = f'/api/applications/{entity_id}/followups/{followup_id}'
        assert client.get(base + '/rendered-message').status_code == 422
        assert client.patch(base, json={'status': 'READY', 'expected_revision': item['revision']}).status_code == 422
        assert client.post(base + '/draft-task', json={'expected_revision': item['revision']}).status_code == 422
        # Explicitly preparing local content enables the existing review workflow.
        prepared = client.patch(base, json={'subject': 'My local subject', 'body': 'My reviewed local message', 'expected_revision': item['revision']})
        assert prepared.status_code == 200, prepared.text
        assert prepared.json()['content_available'] is True
