"""OAuth, native secrets and the shared REST/MCP Gmail boundary, offline."""
import asyncio
import base64
import json
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.google_connection import GoogleConnectionError, NativeSecretStore, SCOPES
from app.main import create_app
from app.mcp_server import create_mcp_server
from app.models import AgentCredential, ExternalConnection

ORIGIN = 'http://127.0.0.1:8000'


class MemorySecrets:
    def __init__(self):
        self.values = {}
        self.fail = False

    def get(self, key):
        if self.fail:
            raise GoogleConnectionError('Credential store locked')
        return self.values.get(key)

    def put(self, key, value):
        if self.fail:
            raise GoogleConnectionError('Credential store locked')
        self.values[key] = dict(value)

    def delete(self, key):
        if self.fail:
            raise GoogleConnectionError('Credential store locked')
        self.values.pop(key, None)


@pytest.fixture
def google(tmp_path):
    store = MemorySecrets()
    state = {'nonce': '', 'subject': 'google-user-1', 'aud': 'test-client', 'iss': 'https://accounts.google.com',
             'refresh_status': 200, 'api_status': 200, 'scopes': list(SCOPES.values()), 'drafts': 0, 'calls': []}

    def handle(request):
        state['calls'].append((request.method, request.url.path, bytes(request.content)))
        if request.url.path == '/token':
            data = parse_qs(request.content.decode())
            if data['grant_type'] == ['refresh_token']:
                return httpx.Response(state['refresh_status'], json={'access_token': 'refreshed-secret', 'expires_in': 3600})
            assert data['code_verifier'][0]
            return httpx.Response(200, json={'access_token': 'access-secret', 'refresh_token': 'refresh-secret',
                'id_token': 'signed-token', 'scope': ' '.join(state['scopes']), 'expires_in': 3600})
        if state['api_status'] != 200:
            return httpx.Response(state['api_status'], json={'error': 'private error access-secret'})
        if request.url.path.endswith('/drafts'):
            state['drafts'] += 1
            if state.get('draft_timeout'):
                raise httpx.ReadTimeout('private refresh-secret')
            return httpx.Response(200, json={'id': 'draft-1'})
        if request.url.path.endswith('/messages'):
            return httpx.Response(200, json={'messages': [{'id': 'abcdef', 'threadId': '123'}]})
        if '/messages/' in request.url.path:
            return httpx.Response(200, json={'id': 'abcdef', 'payload': {'mimeType': 'text/plain',
                'headers': [{'name': 'Subject', 'value': 'Application received'}, {'name': 'X-Private', 'value': 'omit'}],
                'body': {'data': base64.urlsafe_b64encode(b'Hello applicant').decode()}}})
        if request.url.path.startswith('/upload/drive/'):
            boundary = request.headers['content-type'].split('boundary=')[1]
            state['encrypted'] = request.content.split(b'Content-Type: application/octet-stream\r\n\r\n')[1].split(('\r\n--' + boundary).encode())[0]
            assert b'appDataFolder' in request.content
            return httpx.Response(200, json={'id': 'test-object'})
        if '/drive/v3/files/' in request.url.path:
            return httpx.Response(204) if request.method == 'DELETE' else httpx.Response(200, content=state['encrypted'])
        raise AssertionError(str(request.url))

    def identity(token, audience):
        assert token == 'signed-token' and audience == 'test-client'
        return {'iss': state['iss'], 'aud': state['aud'], 'sub': state['subject'], 'email': 'owner@example.com',
                'email_verified': True, 'nonce': state['nonce']}

    settings = Settings(app_data_dir=tmp_path, google_client_id='test-client',
        google_redirect_uri=ORIGIN + '/api/connections/google/callback', _env_file=None)
    app = create_app(settings, google_store=store, google_transport=httpx.MockTransport(handle), google_verifier=identity)
    with TestClient(app, base_url=ORIGIN) as client:
        token = client.post('/api/settings/agent/token').json()['token']
        client.put('/api/settings/agent/permissions', json={key: True for key in ('read', 'create', 'edit', 'draft', 'tasks', 'interviews')})
        yield client, app, settings, store, state, token


def begin(google, capabilities=None):
    client, _, _, _, state, _ = google
    result = client.post('/api/connections/google/start', json={'capabilities': capabilities or list(SCOPES)}, headers={'Origin': ORIGIN})
    assert result.status_code == 200, result.text
    params = parse_qs(urlsplit(result.json()['authorization_url']).query)
    state['nonce'] = params['nonce'][0]
    assert params['code_challenge_method'] == ['S256'] and 'include_granted_scopes' not in params
    return params


def finish(google, params):
    return google[0].get('/api/connections/google/callback', params={'state': params['state'][0], 'code': 'authorization-code'}, follow_redirects=False)


def connect(google, capabilities=None):
    assert finish(google, begin(google, capabilities)).status_code == 303


def call(google, operation, args=None):
    return google[0].post('/api/agent/tools/' + operation, json=args or {}, headers={'Authorization': 'Bearer ' + google[-1]})


def test_google_once_shared_by_two_mcp_clients_permissions_and_rotation(google):
    client, app, settings, store, state, token = google
    connect(google)
    provider = app.state.mail_provider
    servers = [create_mcp_server(settings, token, mail_provider=provider) for _ in range(2)]
    for server in servers:
        result = json.loads(asyncio.run(server.call_tool('search_mail', {'query': 'subject:application'}))[0].text)
        assert result['messages'][0]['id'] == 'abcdef'
    message = call(google, 'get_mail_message', {'message_id': 'abcdef'}).json()
    assert message['text'] == 'Hello applicant' and len(message['headers']) == 1
    assert message['untrusted_content']
    client.put('/api/settings/agent/permissions', json={'read': False})
    for operation in ('search_mail', 'list_applications'):
        assert call(google, operation, {'query': 'x'}).status_code == 403
    from mcp.server.fastmcp.exceptions import ToolError
    for server in servers:
        with pytest.raises(ToolError, match='PERMISSION_DENIED'):
            asyncio.run(server.call_tool('search_mail', {'query': 'x'}))
    client.post('/api/settings/agent/token')
    for server in servers:
        with pytest.raises(ToolError, match='INVALID_TOKEN'):
            asyncio.run(server.call_tool('get_tracker_info', {}))
    assert client.get('/api/connections').json()['google']['status'] == 'CONNECTED'
    assert len(store.values) == 1
    with Session(app.state.engine) as session:
        assert len(list(session.scalars(select(AgentCredential)))) == 1
    public = client.get('/api/connections').text + client.get('/api/integrations').text
    assert all(secret not in public for secret in ['access-secret', 'refresh-secret', 'secret_reference'])
    assert all('/send' not in path for _, path, _ in state['calls'])


@pytest.mark.parametrize('kind', ['state', 'browser', 'nonce', 'issuer', 'audience', 'expired'])
def test_oauth_rejects_invalid_link_context_and_identity(google, kind):
    client, app, _, store, state, _ = google
    params = begin(google)
    if kind == 'state':
        params['state'] = ['wrong']
    elif kind == 'browser':
        client.cookies.clear()
    elif kind == 'nonce':
        state['nonce'] = 'wrong'
    elif kind == 'issuer':
        state['iss'] = 'https://attacker.example'
    elif kind == 'audience':
        state['aud'] = 'wrong-client'
    elif kind == 'expired':
        app.state.google.login.sessions.clock = lambda: float('inf')
    assert finish(google, params).status_code == 409
    assert not store.values
    assert not client.get('/api/connections').json()['google']['capabilities']['gmail_read']


def test_reauthorization_pins_account_and_invalidates_old_attempts(google):
    client, _, _, _, state, _ = google
    connect(google, ['gmail_read'])
    params = begin(google)
    state['subject'] = 'other-account'
    assert finish(google, params).status_code == 409
    assert client.get('/api/connections').json()['google']['capabilities'] == {'drive': False, 'gmail_read': True, 'gmail_drafts': False}
    state['subject'] = 'google-user-1'
    old = begin(google)
    latest = begin(google)
    assert finish(google, old).status_code == 409
    assert finish(google, latest).status_code == 303
    assert finish(google, latest).status_code == 409
    pending = begin(google)
    assert client.post('/api/connections/google/disconnect', headers={'Origin': ORIGIN}).status_code == 200
    assert finish(google, pending).status_code == 409
    assert call(google, 'list_applications').status_code == 200


def test_refused_and_revoked_scopes_and_locked_store_keep_offline_app(google):
    client, app, _, store, state, _ = google
    state['scopes'] = [SCOPES['gmail_read']]
    connect(google)
    status = client.get('/api/connections').json()['google']
    assert status['status'] == 'PARTIAL' and not status['capabilities']['gmail_drafts']
    state['api_status'] = 403
    assert call(google, 'search_mail', {'query': 'x'}).status_code == 409
    assert not client.get('/api/connections').json()['google']['capabilities']['gmail_read']
    store.fail = True
    assert client.get('/api/connections').json()['google']['status'] == 'CREDENTIALS_UNAVAILABLE'
    assert client.post('/api/connections/google/start', json={'capabilities': ['drive']}, headers={'Origin': ORIGIN}).status_code == 409
    assert call(google, 'list_applications').status_code == 200
    assert client.get('/api/health').status_code == 200
    store.fail = False
    state['api_status'], state['scopes'] = 200, list(SCOPES.values())
    connect(google)
    for value in store.values.values():
        value['expires_at'] = 0
    state['refresh_status'] = 400
    assert call(google, 'search_mail', {'query': 'x'}).status_code == 409
    assert client.get('/api/connections').json()['google']['status'] == 'RECONNECT_REQUIRED'
    assert call(google, 'list_applications').status_code == 200
    assert not app.state.mail_provider.is_connected()


def test_connection_management_requires_origin_host_and_cannot_be_agent_tool(google):
    client, _, _, _, _, _ = google
    payload = {'capabilities': ['gmail_read']}
    assert client.post('/api/connections/google/start', json=payload).status_code == 403
    assert client.post('/api/connections/google/start', json=payload, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/connections/google/start', json=payload, headers={'Origin': ORIGIN, 'Host': 'evil.example'}).status_code == 421
    assert call(google, 'google_disconnect').status_code == 404


def test_encrypted_drive_appdata_roundtrip_and_cleanup(google):
    connect(google, ['drive'])
    client, _, _, _, state, _ = google
    key = base64.urlsafe_b64encode(bytes(range(32))).decode()
    result = client.post('/api/connections/google/drive-test', json={'recovery_key': key}, headers={'Origin': ORIGIN})
    assert result.status_code == 200, result.text
    assert result.json()['verified'] and result.json()['deleted']
    assert len(state['encrypted']) == 60
    assert state['calls'][-1][:2] == ('DELETE', '/drive/v3/files/test-object')
    assert key not in result.text
    assert client.post('/api/connections/google/drive-test', json={'recovery_key': 'x' * 44}, headers={'Origin': ORIGIN}).status_code == 409


def test_native_store_rejects_plaintext_fallback_and_backend_failures(tmp_path, monkeypatch):
    import keyring
    class Plaintext:
        def set_password(self, *args):
            raise AssertionError('must not write')
    monkeypatch.setattr(keyring, 'get_keyring', lambda: Plaintext())
    with pytest.raises(GoogleConnectionError, match='native OS credential store'):
        NativeSecretStore(tmp_path).backend()


def test_real_signature_validator_rejects_expired_wrong_audience_and_forged_tokens(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from google.auth import crypt, jwt
    from app.google_connection import verify_identity
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    class Response:
        status = 200
        data = json.dumps({'key-1': public}).encode()
    def certificate_request(*args, **kwargs):
        assert kwargs['timeout'] == 10
        return Response()
    monkeypatch.setattr('google.auth.transport.requests.Request', lambda: certificate_request)
    signer = crypt.RSASigner.from_string(private, key_id='key-1')
    claims = {'iss': 'https://accounts.google.com', 'aud': 'test-client', 'sub': 'user', 'iat': int(time.time()), 'exp': int(time.time()) + 300}
    signed = jwt.encode(signer, claims).decode()
    assert verify_identity(signed, 'test-client')['sub'] == 'user'
    for token, audience in [(signed, 'wrong-client'), (jwt.encode(signer, {**claims, 'iat': 1, 'exp': 2}).decode(), 'test-client'), (signed[:-10] + 'invalid', 'test-client')]:
        with pytest.raises(GoogleConnectionError, match='identity verification failed'):
            verify_identity(token, audience)


def test_callback_log_redacts_codes_and_state():
    import logging
    from app.google_connection import CallbackLogFilter
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d',
        ('127.0.0.1', 'GET', '/api/connections/google/callback?code=private-code&state=private-state', '1.1', 303), None)
    assert CallbackLogFilter().filter(record)
    assert 'private-code' not in record.getMessage() and 'private-state' not in record.getMessage()


def test_google_draft_receipt_prevents_duplicate_side_effects_and_payload_reuse(google):
    client, app, _, _, state, _ = google
    connect(google)
    application = client.post('/api/applications', json={'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-18', 'email_reference': 'mail'}).json()
    item = client.get(f"/api/applications/{application['id']}/work").json()['followups'][0]
    item = client.patch(f"/api/applications/{application['id']}/followups/{item['id']}", json={'recipient_email': 'recruiter@example.com', 'subject': 'Follow up', 'body': 'Hello', 'expected_revision': item['revision']}).json()
    args = {'application_id': application['id'], 'followup_id': item['id'], 'content': 'Hello', 'expected_revision': item['revision'], 'idempotency_key': 'one-draft'}
    first = call(google, 'draft_followup', args)
    assert first.status_code == 200, first.text
    assert call(google, 'draft_followup', args).json() == first.json()
    assert state['drafts'] == 1
    assert call(google, 'draft_followup', {**args, 'content': 'Different'}).status_code == 409
    assert call(google, 'draft_followup', {**args, 'idempotency_key': 'stale', 'expected_revision': item['revision'] - 1}).status_code in {409, 422}
    current = client.get(f"/api/applications/{application['id']}/work").json()['followups'][0]
    assert current['status'] == 'PREPARED'
    state['draft_timeout'] = True
    uncertain = {**args, 'expected_revision': current['revision'], 'idempotency_key': 'uncertain'}
    failure = call(google, 'draft_followup', uncertain)
    assert failure.status_code == 409 and 'refresh-secret' not in failure.text
    state['draft_timeout'] = False
    assert call(google, 'draft_followup', uncertain).status_code == 409
    assert state['drafts'] == 2
    client.put('/api/settings/agent/permissions', json={'read': True, 'draft': False})
    assert call(google, 'draft_followup', args).status_code == 403
    assert call(google, 'search_mail', {'query': 'x'}).status_code == 200
