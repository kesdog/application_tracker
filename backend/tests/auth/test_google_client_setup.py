"""In-app Google registration uses owner access and the existing credential vault."""
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.google_client_setup import REFERENCE
from app.main import create_app
from tests.support import MemorySecrets

ORIGIN = 'http://127.0.0.1:8000'
CLIENT = '123456-fixture.apps.googleusercontent.com'
SECRET = 'fixture-client-secret-never-returned'


def test_owner_can_import_then_start_google_without_restarting_and_registration_survives_restart(tmp_path):
    store = MemorySecrets()
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    app = create_app(settings, google_store=store)
    with TestClient(app, base_url=ORIGIN) as client:
        setup = client.get('/api/connections/google/setup')
        assert setup.status_code == 200
        assert setup.json()['redirect_uri'] == ORIGIN + '/api/connections/google/callback'
        registration = {'client_id': CLIENT, 'client_secret': SECRET}
        assert client.put('/api/connections/google/setup', json=registration).status_code == 403
        response = client.put('/api/connections/google/setup', json=registration, headers={'Origin': ORIGIN})
        assert response.status_code == 200 and response.json()['configured']
        assert SECRET not in response.text and SECRET not in client.get('/api/connections/google/setup').text
        assert store.values[REFERENCE]['client_secret'] == SECRET
        assert SECRET not in (tmp_path / '.google-client-registered').read_text()
        assert settings.google_client_id == CLIENT
        started = client.post('/api/connections/google/start', json={'capabilities': ['gmail_read']}, headers={'Origin': ORIGIN})
        assert started.status_code == 200
        parameters = parse_qs(urlsplit(started.json()['authorization_url']).query)
        assert parameters['client_id'] == [CLIENT]
        assert parameters['redirect_uri'] == [ORIGIN + '/api/connections/google/callback']
        assert SECRET not in started.text
    fresh = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(fresh, google_store=store), base_url=ORIGIN) as restarted:
        assert restarted.get('/api/connections/google/setup').json()['configured']
        assert fresh.google_client_id == CLIENT
        assert fresh.google_client_secret.get_secret_value() == SECRET
    # Independent MCP and sync consumers construct GoogleConnection directly.
    from app.google_connection import GoogleConnection
    standalone = Settings(app_data_dir=tmp_path, _env_file=None)
    GoogleConnection(app.state.engine, standalone, store=store)
    assert standalone.google_client_id == CLIENT


def test_locked_vault_cannot_apply_an_unpersisted_registration_or_block_local_tracking(tmp_path):
    store = MemorySecrets()
    store.fail = True
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    (tmp_path / '.google-client-registered').write_text('vault\n')
    with TestClient(create_app(settings, google_store=store), base_url=ORIGIN) as client:
        response = client.put('/api/connections/google/setup', json={'client_id': CLIENT, 'client_secret': SECRET}, headers={'Origin': ORIGIN})
        assert response.status_code == 409
        assert settings.google_client_id is None
        assert client.get('/api/applications').status_code == 200


@pytest.mark.parametrize('registration', [{'client_id': 'not-a-google-client'}, {'client_id': CLIENT, 'redirect_uri': 'https://attacker.example/callback'}])
def test_import_rejects_non_google_clients_and_arbitrary_redirects(tmp_path, registration):
    store = MemorySecrets()
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None), google_store=store), base_url=ORIGIN) as client:
        assert client.put('/api/connections/google/setup', json=registration, headers={'Origin': ORIGIN}).status_code == 422
        assert store.values == {}
