"""Offline OAuth, credential isolation and provider usage recovery contracts."""
import base64
import copy
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from app.ai_connections import AIConnections, AIConnectionError, NativeAISecretStore, ISSUER, REFERENCE, RESOURCE, provider_error
from app.config import Settings
from app.google_connection import CallbackLogFilter
from app.human_auth import hash_password
from app.main import create_app
from tests.support import MemorySecrets

ORIGIN = 'http://127.0.0.1:8000'
BASE = '/api/connections/ai'
HEADERS = {'Origin': ORIGIN}


def record():
    return {'host_id': 'urn:uuid:fixture-host', 'active': 'oaiapp_fixture', 'accounts': {'oaiapp_fixture': {
        'subject': 'subject-1', 'email': 'owner@example.test', 'access_token': 'private-access',
        'refresh_token': 'private-refresh', 'expires_at': time.time() + 3600,
        'scopes': ['chatgpt.tokens.use.direct']}}}


@pytest.fixture
def ai(tmp_path):
    store = MemorySecrets()
    service = AIConnections(Settings(app_data_dir=tmp_path, _env_file=None), store)
    return service, store


def test_oauth_registration_is_bound_single_use_and_returns_no_tokens(ai):
    service, store = ai
    params = parse_qs(urlsplit(service.start(None, 'browser', 'owner')).query)
    assert params['client_id'] == ['dynamic_agent_client']
    assert params['agent_name_hint'] == ['Application Tracker']
    assert params['redirect_uri'] == [ORIGIN + BASE + '/chatgpt/callback']
    assert params['resource'] == [RESOURCE]
    assert params['code_challenge_method'] == ['S256']
    host = params['ext_agent_host_id']
    state = params['state'][0]
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={'access_token': 'private-access', 'refresh_token': 'private-refresh',
            'id_token': 'signed-id', 'scope': 'openid email chatgpt.tokens.use.direct', 'token_type': 'Bearer', 'expires_in': 3600})
    service.transport = httpx.MockTransport(transport)
    def verifier(token, audience, nonce):
        assert (token, audience, nonce) == ('signed-id', 'oaiapp_fixture', params['nonce'][0])
        return {'sub': 'subject-1', 'email': 'owner@example.test'}
    service.verifier = verifier
    with pytest.raises(AIConnectionError):
        service.finish(state, 'auth-code', 'oaiapp_fixture', 'wrong-browser', 'owner')
    assert calls == []
    service.finish(state, 'auth-code', 'oaiapp_fixture', 'browser', 'owner')
    body = parse_qs(calls[0].content.decode())
    assert body['client_id'] == ['oaiapp_fixture']
    assert body['redirect_uri'] == params['redirect_uri']
    assert 'client_secret' not in body
    public = json.dumps(service.status())
    assert 'private-' not in public and 'signed-id' not in public
    assert service.status()['chatgpt']['can_use']
    with pytest.raises(AIConnectionError):
        service.finish(state, 'auth-code', 'oaiapp_fixture', 'browser', 'owner')
    restarted = AIConnections(service.settings, store)
    returning = parse_qs(urlsplit(restarted.start('oaiapp_fixture', 'browser', 'owner')).query)
    assert returning['ext_agent_host_id'] == host
    assert returning['client_id'] == ['oaiapp_fixture']
    assert 'agent_name_hint' not in returning


@pytest.mark.parametrize('failure', ['denied', 'missing_client', 'changed_client', 'identity', 'stale'])
def test_failed_or_stale_authorization_keeps_existing_account(ai, failure):
    service, store = ai
    store.put(REFERENCE, record())
    before = copy.deepcopy(store.values)
    account = None if failure == 'missing_client' else 'oaiapp_fixture'
    params = parse_qs(urlsplit(service.start(account, 'browser', 'owner')).query)
    if failure == 'stale':
        service.start(account, 'browser', 'owner')
    service.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={
        'access_token': 'new-private-access', 'id_token': 'signed-id', 'token_type': 'Bearer', 'expires_in': 3600}))
    service.verifier = lambda *args: {'sub': 'another-subject' if failure == 'identity' else 'subject-1'}
    with pytest.raises(AIConnectionError):
        service.finish(params['state'][0], 'code', '' if failure == 'missing_client' else 'other-client' if failure == 'changed_client' else 'oaiapp_fixture',
                       'browser', 'owner', denied=failure == 'denied')
    assert store.values == before


def test_refresh_rotation_and_terminal_vs_temporary_failure(ai):
    service, store = ai
    saved = record(); saved['accounts']['oaiapp_fixture']['expires_at'] = 1
    store.put(REFERENCE, saved)
    def refreshed(request):
        data = parse_qs(request.content.decode())
        assert data['client_id'] == ['oaiapp_fixture'] and data['resource'] == [RESOURCE]
        assert 'scope' not in data
        return httpx.Response(200, json={'access_token': 'rotated-access', 'refresh_token': 'rotated-refresh',
                                        'token_type': 'Bearer', 'expires_in': 3600})
    service.transport = httpx.MockTransport(refreshed)
    assert service.credential('chatgpt') == 'rotated-access'
    assert store.get(REFERENCE)['accounts']['oaiapp_fixture']['refresh_token'] == 'rotated-refresh'
    saved = store.get(REFERENCE); saved['accounts']['oaiapp_fixture']['expires_at'] = 1; store.put(REFERENCE, saved)
    service.transport = httpx.MockTransport(lambda r: httpx.Response(503, text='temporarily unavailable'))
    with pytest.raises(AIConnectionError, match='temporarily unavailable'):
        service.credential('chatgpt')
    assert store.get(REFERENCE)['accounts']['oaiapp_fixture']['refresh_token'] == 'rotated-refresh'
    service.transport = httpx.MockTransport(lambda r: httpx.Response(400, json={'error': 'invalid_grant'}))
    with pytest.raises(AIConnectionError, match='Reconnect'):
        service.credential('chatgpt')
    assert not service.status()['chatgpt']['connected']
    assert 'oaiapp_fixture' in store.get(REFERENCE)['accounts']


@pytest.mark.parametrize('status,error,expected', [
    (429, {'code': 'subscription_sharing_usage_limit_exceeded'}, 'usage_limit'),
    (429, {'type': 'rate_limit_error'}, 'rate_limit'),
    (400, {'type': 'invalid_request_error', 'message': 'Your credit balance is too low'}, 'credits'),
    (400, {'type': 'invalid_request_error', 'message': 'Organization spending limit reached'}, 'credits'),
    (402, {'type': 'billing_error'}, 'credits'),
    (429, {'type': 'rate_limit_error', 'message': 'Your usage tier monthly spend cap has been reached'}, 'credits'),
    (401, {'type': 'authentication_error'}, 'authorization'),
    (403, {'code': 'subscription_sharing_user_not_eligible'}, 'permission'),
    (503, {}, 'unavailable'),
])
def test_fixed_errors_do_not_echo_provider_payloads(status, error, expected):
    error['diagnostic'] = 'private-provider-token'
    exc = provider_error('claude' if 'type' in error else 'chatgpt', httpx.Response(status, json={'error': error}, headers={'retry-after': '12'}))
    assert exc.kind == expected and exc.retry_after == 12
    assert 'private-provider-token' not in str(exc)


@pytest.mark.parametrize('event', ['response.completed', 'response.failed', 'response.incomplete', 'interrupted'])
def test_stream_terminal_events_and_mid_stream_usage_limit(ai, event):
    service, store = ai
    store.put(REFERENCE, record())
    requests = []
    def transport(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'models': [{'slug': 'available-model', 'display_name': 'Available model', 'visibility': 'list'}]})
        body = json.loads(request.content)
        assert body['store'] is False and body['stream'] is True
        assert str(request.url) == RESOURCE + '/responses'
        assert body['input'][0]['content'] == 'Reply with OK.'
        data = {'type': event, 'response': {'error': {'code': 'subscription_sharing_usage_limit_exceeded'}}}
        return httpx.Response(200, text='' if event == 'interrupted' else 'data: ' + json.dumps(data) + '\n\n', headers={'Content-Type': 'text/event-stream'})
    service.transport = httpx.MockTransport(transport)
    if event == 'response.completed':
        assert 'verified' in service.test('chatgpt', 'available-model')['message']
    else:
        with pytest.raises(AIConnectionError) as caught:
            service.test('chatgpt', 'available-model')
        assert caught.value.kind == ('usage_limit' if event == 'response.failed' else 'request' if event == 'response.incomplete' else 'unavailable')
    assert len(requests) == 2
    assert service.status()['chatgpt']['connected']


def test_claude_key_verified_before_replacement_and_disconnect_clears_it(ai):
    service, store = ai
    def good(request):
        assert request.headers['x-api-key'] == 'private-claude-key'
        return httpx.Response(200, json={'data': [{'id': 'claude-fixture', 'display_name': 'Claude fixture'}]})
    service.transport = httpx.MockTransport(good)
    assert service.connect_claude('private-claude-key')['claude']['connected']
    assert 'private-claude-key' not in json.dumps(service.status())
    service.transport = httpx.MockTransport(lambda r: httpx.Response(401, json={'error': {'type': 'authentication_error'}}))
    with pytest.raises(AIConnectionError):
        service.connect_claude('bad-private-key')
    assert store.get(REFERENCE)['claude_key'] == 'private-claude-key'
    service.disconnect('claude')
    assert 'claude_key' not in store.get(REFERENCE)


def test_disconnect_stops_pending_signins_and_retains_registration_on_revocation_failure(ai):
    service, store = ai
    store.put(REFERENCE, record())
    params = parse_qs(urlsplit(service.start('oaiapp_fixture', 'browser', 'owner')).query)
    service.transport = httpx.MockTransport(lambda r: httpx.Response(503))
    result = service.disconnect('chatgpt')
    assert 'not confirmed' in result['message']
    assert store.get(REFERENCE)['accounts']['oaiapp_fixture'] == {'subject': 'subject-1', 'email': 'owner@example.test'}
    with pytest.raises(AIConnectionError):
        service.finish(params['state'][0], 'code', 'oaiapp_fixture', 'browser', 'owner')


@pytest.mark.parametrize('mutation', [None, 'nonce', 'aud', 'iss', 'exp', 'signature', 'alg'])
def test_real_signature_and_claim_validation(ai, mutation):
    service, _ = ai
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    key = {'kid': 'fixture', 'kty': 'RSA', 'n': encode(numbers.n.to_bytes(256, 'big')), 'e': encode(numbers.e.to_bytes(3, 'big'))}
    service.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'keys': [key]}))
    header = {'kid': 'fixture', 'alg': 'none' if mutation == 'alg' else 'RS256'}
    claims = {'iss': ISSUER, 'aud': 'oaiapp_fixture', 'sub': 'subject-1', 'exp': time.time() + 300, 'nonce': 'nonce'}
    if mutation in claims:
        claims[mutation] = 0 if mutation == 'exp' else 'incorrect'
    parts = [encode(json.dumps(header).encode()), encode(json.dumps(claims).encode())]
    signature = private.sign('.'.join(parts).encode(), padding.PKCS1v15(), hashes.SHA256())
    token = '.'.join([*parts, encode(b'incorrect' if mutation == 'signature' else signature)])
    if mutation:
        with pytest.raises(AIConnectionError):
            service.verify_identity(token, 'oaiapp_fixture', 'nonce')
    else:
        assert service.verify_identity(token, 'oaiapp_fixture', 'nonce')['sub'] == 'subject-1'


def test_routes_require_owner_origin_and_never_echo_secrets(tmp_path):
    store = MemorySecrets()
    app = create_app(Settings(app_data_dir=tmp_path, _env_file=None), ai_store=store)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(BASE).status_code == 200
        assert client.post(BASE + '/chatgpt/start', json={}).status_code == 403
        assert client.get(BASE, headers={'Authorization': 'Bearer agent-token'}).status_code == 403
        assert client.put(BASE + '/claude', json={'api_key': 'secret'}, headers=HEADERS).status_code == 422
        assert 'secret' not in client.put(BASE + '/claude', json={'api_key': 'secret'}, headers=HEADERS).text
        started = client.post(BASE + '/chatgpt/start', json={}, headers=HEADERS)
        params = parse_qs(urlsplit(started.json()['authorization_url']).query)
        assert 'HttpOnly' in started.headers['set-cookie']
        result = client.get(BASE + '/chatgpt/callback', params={'state': params['state'][0], 'error': 'access_denied'}, follow_redirects=False)
        assert result.status_code == 303 and 'ai_result=permission' in result.headers['location']
        assert 'auth-code' not in result.text
        store.fail = True
        assert client.get(BASE).status_code == 409
        assert client.get('/api/applications').status_code == 200


def test_hosted_requires_session_csrf_and_disallows_direct_chatgpt(tmp_path):
    origin = 'https://tracker.example.test'
    app = create_app(Settings(app_mode='hosted', app_public_url=origin, app_data_dir=tmp_path,
        app_password_hash=hash_password('test workspace password only'), _env_file=None), ai_store=MemorySecrets())
    with TestClient(app, base_url=origin) as client:
        assert client.get(BASE).status_code == 401
        client.post('/api/auth/login', json={'password': 'test workspace password only'}, headers={'Origin': origin})
        assert client.get(BASE).json()['chatgpt']['available'] is False
        assert client.post(BASE + '/chatgpt/start', json={}, headers={'Origin': origin}).status_code == 403
        headers = {'Origin': origin, 'X-CSRF-Token': client.get('/api/auth/session').json()['csrf_token']}
        assert client.post(BASE + '/chatgpt/start', json={}, headers=headers).json()['code'] == 'local_required'


def test_callback_logs_hide_ai_authorization_codes():
    import logging
    record = logging.LogRecord('uvicorn.access', 20, '', 0, '%s', ('/api/connections/ai/chatgpt/callback?code=private-code&state=private-state',), None)
    CallbackLogFilter().filter(record)
    assert 'private-code' not in record.getMessage() and 'private-state' not in record.getMessage()


def test_large_oauth_bundles_use_encrypted_files_and_a_small_native_key(tmp_path):
    keys = MemorySecrets()
    protected = NativeAISecretStore(tmp_path, keys)
    value = record()
    value['accounts']['oaiapp_fixture']['access_token'] = 'private-large-token-' + 'x' * 12000
    protected.put(REFERENCE, value)
    assert protected.get(REFERENCE) == value
    assert len(json.dumps(keys.values)) < 256
    assert b'private-large-token' not in protected.path(REFERENCE).read_bytes()
    # Missing/locked keys must never be regenerated over an existing ciphertext.
    keys.values.clear()
    before = protected.path(REFERENCE).read_bytes()
    service = AIConnections(Settings(app_data_dir=tmp_path, _env_file=None), protected)
    with pytest.raises(AIConnectionError, match='secure credential store'):
        service.status()
    assert protected.path(REFERENCE).read_bytes() == before
    assert not keys.values
