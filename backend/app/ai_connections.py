"""Human-controlled AI connections. Tokens never cross the browser/agent API."""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.google_connection import GoogleConnectionError
from app.oauth_sessions import OAuthSessionError, OAuthSessionManager
from app.secret_store import EncryptedFileSecretStore

ISSUER = 'https://auth.openai.com'
TOKEN = ISSUER + '/api/accounts/oauth/token'
RESOURCE = 'https://api.openai.com/v1'
COOKIE = 'tracker-ai-link'
REFERENCE = 'ai-connections-v1'
Provider = Literal['chatgpt', 'claude']


class NativeAISecretStore(EncryptedFileSecretStore):
    """Keep a small encryption key in the OS vault; OAuth bundles can exceed its blob limit."""
    def __init__(self, workspace, keys):
        self.workspace = workspace.resolve()
        self.folder = self.workspace / 'credentials'
        self.keys = keys

    def cipher(self):
        reference = 'ai-credential-encryption-key-v1'
        try:
            saved = self.keys.get(reference)
            if saved is None:
                if self.path(REFERENCE).exists():
                    raise ValueError()
                saved = {'key': base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()}
                self.keys.put(reference, saved)
                if self.keys.get(reference) != saved:
                    raise ValueError()
            return AESGCM(base64.urlsafe_b64decode(saved['key']))
        except Exception:
            raise GoogleConnectionError('AI credentials could not be unlocked in the native credential store.') from None


class AIConnectionError(ValueError):
    def __init__(self, kind, provider, *, retry_after=None):
        self.kind, self.provider, self.retry_after = kind, provider, retry_after
        name = 'ChatGPT' if provider == 'chatgpt' else 'Claude'
        messages = {
            'usage_limit': f'{name} usage limit reached. Review your app allowance in ChatGPT Settings → Usage, or try again when usage is available.',
            'credits': 'Claude API credits or spending limit reached. Review billing in Claude Console before trying again.' if provider == 'claude' else 'ChatGPT usage credits reached their limit. Review ChatGPT Settings → Usage before trying again.',
            'rate_limit': f'{name} is receiving too many requests. Wait before trying again.',
            'authorization': f'{name} access expired or was revoked. Reconnect this account.',
            'permission': f'{name} has not allowed this request. Check account eligibility, workspace policy and granted permissions.',
            'unavailable': f'{name} is temporarily unavailable. Your connection is kept; try again later.',
            'request': f'{name} could not complete this request. Refresh the model list or reconnect if the problem continues.',
            'identity': 'ChatGPT identity could not be verified. Start a new connection.',
            'storage': 'AI credentials could not be unlocked or saved. Unlock the secure credential store and try again.',
            'superseded': 'The AI connection changed during this attempt. Start again.',
            'local_required': 'Direct ChatGPT linking requires a local installation at http://127.0.0.1. Use the ChatGPT MCP connection for a hosted workspace.',
        }
        super().__init__(messages[kind])


def provider_error(provider, response=None, error=None):
    status = response.status_code if response is not None else 502
    if error is None:
        try:
            error = response.json().get('error', {})
        except (ValueError, AttributeError):
            error = {}
    if isinstance(error, str):
        error = {'code': error}
    if not isinstance(error, dict):
        error = {}
    code = error.get('code') or error.get('type')
    # Claude currently describes exhausted credits as an invalid_request_error.
    message = str(error.get('message', '')).lower()
    if code == 'subscription_sharing_usage_limit_exceeded':
        kind = 'usage_limit'
    elif code in {'insufficient_quota', 'billing_error'} or (provider == 'claude' and any(s in message for s in ('credit balance', 'spend limit', 'spending limit', 'spend cap'))):
        kind = 'credits'
    elif status == 429 or code == 'rate_limit_error':
        kind = 'rate_limit'
    elif status == 401 or code in {'invalid_grant', 'invalid_refresh_token', 'token_expired', 'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused', 'authentication_error'}:
        kind = 'authorization'
    elif status == 403 or code in {'subscription_sharing_user_not_eligible', 'subscription_sharing_route_not_supported', 'chatpass_v2_scope_not_authorized', 'chatpass_v2_invalid_authorization_context', 'permission_error'}:
        kind = 'permission'
    elif code in {'subscription_sharing_usage_unavailable', 'subscription_sharing_user_unavailable'} or status >= 500:
        kind = 'unavailable'
    else:
        kind = 'request'
    retry = response.headers.get('retry-after', '') if response is not None else ''
    seconds = min(int(retry), 86400) if retry.isdecimal() else None
    return AIConnectionError(kind, provider, retry_after=seconds)


class ClaudeKey(BaseModel):
    model_config = ConfigDict(extra='forbid')
    api_key: SecretStr = Field(min_length=10, max_length=4096)


class TestAI(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str = Field(min_length=1, max_length=200, pattern=r'^[a-zA-Z0-9._:/-]+$')


class StartChatGPT(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account: str | None = Field(default=None, max_length=256)


@dataclass(repr=False)
class Pending:
    verifier: str
    nonce: str
    client_id: str | None
    subject: str | None
    generation: int


class AIConnections:
    def __init__(self, settings, store, *, transport=None, verifier=None):
        self.settings, self.store, self.transport = settings, store, transport
        self.verifier = verifier or self.verify_identity
        self.pending = OAuthSessionManager[Pending]()
        self.lock = threading.RLock()
        self.generation = 0

    @property
    def local_chatgpt(self):
        return self.settings.app_mode == 'local' and self.settings.app_host == '127.0.0.1'

    @property
    def callback(self):
        return f'http://127.0.0.1:{self.settings.app_port}/api/connections/ai/chatgpt/callback'

    def _load(self):
        try:
            return self.store.get(REFERENCE) or {'host_id': 'urn:uuid:' + str(uuid4()), 'accounts': {}, 'active': None}
        except GoogleConnectionError:
            raise AIConnectionError('storage', 'chatgpt') from None

    def _save(self, value):
        try:
            self.store.put(REFERENCE, value)
        except GoogleConnectionError:
            raise AIConnectionError('storage', 'chatgpt') from None

    def http(self, provider, method, url, **kwargs):
        try:
            with httpx.Client(transport=self.transport, timeout=20, follow_redirects=False) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise AIConnectionError('unavailable', provider) from None
        if not 200 <= response.status_code < 300:
            raise provider_error(provider, response)
        return response

    def status(self):
        with self.lock:
            value = self._load()
            accounts = value['accounts'] if self.local_chatgpt else {}
            active = accounts.get(value['active'], {})
            return {
                'chatgpt': {'available': self.local_chatgpt, 'connected': bool(active.get('access_token')),
                            'account': value['active'] if self.local_chatgpt else None,
                            'email': active.get('email'), 'can_use': bool(active.get('access_token') and 'chatgpt.tokens.use.direct' in active.get('scopes', [])),
                            'accounts': [{'id': key, 'label': f"{item.get('email') or 'ChatGPT account'} · {key[-8:]}",
                                          'connected': bool(item.get('access_token'))} for key, item in accounts.items()]},
                'claude': {'available': True, 'connected': bool(value.get('claude_key')), 'method': 'api_key'},
            }

    def start(self, account, binding, owner):
        if not self.local_chatgpt:
            raise AIConnectionError('local_required', 'chatgpt')
        with self.lock:
            value = self._load()
            if account is not None and account not in value['accounts']:
                raise AIConnectionError('request', 'chatgpt')
            saved = value['accounts'].get(account, {})
            self._save(value)  # Persist the stable host ID and probe the vault before redirecting.
            self.generation += 1
            pending = Pending(secrets.token_urlsafe(32), secrets.token_urlsafe(32), account, saved.get('subject'), self.generation)
            try:
                state = self.pending.create(binding, owner, pending)
            except OAuthSessionError:
                raise AIConnectionError('rate_limit', 'chatgpt') from None
            params = {'client_id': account or 'dynamic_agent_client', 'ext_agent_host_id': value['host_id'],
                      'response_type': 'code', 'redirect_uri': self.callback,
                      'scope': 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct',
                      'resource': RESOURCE, 'state': state, 'nonce': pending.nonce,
                      'code_challenge_method': 'S256',
                      'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(pending.verifier.encode()).digest()).decode().rstrip('=')}
            if not account:
                params['agent_name_hint'] = 'Application Tracker'
            elif saved.get('email'):
                params['login_hint'] = saved['email']
            return ISSUER + '/api/accounts/authorize?' + urlencode(params)

    def finish(self, state, code, client_id, binding, owner, denied=False):
        if not self.local_chatgpt:
            raise AIConnectionError('local_required', 'chatgpt')
        try:
            pending = self.pending.consume(state, binding, owner)
        except OAuthSessionError:
            raise AIConnectionError('identity', 'chatgpt') from None
        if denied or not code:
            raise AIConnectionError('permission', 'chatgpt')
        issued = pending.client_id or client_id
        if not issued or issued == 'dynamic_agent_client' or (pending.client_id and client_id and client_id != pending.client_id):
            raise AIConnectionError('identity', 'chatgpt')
        with self.lock:
            if pending.generation != self.generation:
                raise AIConnectionError('superseded', 'chatgpt')
            try:
                tokens = self.http('chatgpt', 'POST', TOKEN, data={'grant_type': 'authorization_code',
                    'client_id': issued, 'code': code, 'code_verifier': pending.verifier,
                    'redirect_uri': self.callback, 'resource': RESOURCE}).json()
                claims = self.verifier(tokens['id_token'], issued, pending.nonce)
                if pending.subject and claims['sub'] != pending.subject:
                    raise ValueError()
                saved = self.token_record(tokens)
                value = self._load()
                existing = value['accounts'].get(issued)
                if existing and existing['subject'] != claims['sub']:
                    raise ValueError()
                value['accounts'][issued] = {**saved, 'subject': claims['sub'], 'email': claims.get('email')}
                value['active'] = issued
                self._save(value)
            except (KeyError, ValueError, TypeError) as exc:
                if isinstance(exc, AIConnectionError):
                    raise
                raise AIConnectionError('identity', 'chatgpt') from None

    @staticmethod
    def token_record(tokens, old=None):
        if not isinstance(tokens.get('access_token'), str) or not tokens['access_token'] or tokens.get('token_type', '').lower() != 'bearer':
            raise ValueError()
        expires = int(tokens['expires_in'])
        if expires <= 0:
            raise ValueError()
        record = {**(old or {}), 'access_token': tokens['access_token'], 'expires_at': time.time() + expires}
        for key in ('refresh_token', 'id_token'):
            if tokens.get(key):
                record[key] = tokens[key]
        if 'scope' in tokens:
            record['scopes'] = tokens['scope'].split()
        elif not old:
            record['scopes'] = []
        return record

    def verify_identity(self, token, audience, nonce):
        try:
            header_part, body_part, signature_part = token.split('.')
            decode = lambda part: base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))
            header, claims = json.loads(decode(header_part)), json.loads(decode(body_part))
            if header['alg'] != 'RS256':
                raise ValueError()
            keys = self.http('chatgpt', 'GET', ISSUER + '/.well-known/jwks.json').json()['keys']
            key = next(key for key in keys if key.get('kid') == header.get('kid') and key.get('kty') == 'RSA' and key.get('use', 'sig') == 'sig' and key.get('alg', 'RS256') == 'RS256')
            public = rsa.RSAPublicNumbers(int.from_bytes(decode(key['e']), 'big'), int.from_bytes(decode(key['n']), 'big')).public_key()
            public.verify(decode(signature_part), (header_part + '.' + body_part).encode(), padding.PKCS1v15(), hashes.SHA256())
            if (claims['iss'] != ISSUER or claims['aud'] != audience or claims['exp'] <= time.time()
                    or claims.get('iat', 0) > time.time() + 60 or claims.get('nbf', 0) > time.time() + 60
                    or not isinstance(claims['sub'], str) or not claims['sub']
                    or not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], nonce)):
                raise ValueError()
            return claims
        except AIConnectionError:
            raise
        except Exception:
            raise AIConnectionError('identity', 'chatgpt') from None

    def credential(self, provider):
        value = self._load()
        if provider == 'claude':
            if not value.get('claude_key'):
                raise AIConnectionError('authorization', provider)
            return value['claude_key']
        if not self.local_chatgpt:
            raise AIConnectionError('local_required', provider)
        saved = value['accounts'].get(value['active'], {})
        if not saved.get('access_token'):
            raise AIConnectionError('authorization', provider)
        if saved['expires_at'] < time.time() + 60:
            if not saved.get('refresh_token'):
                raise AIConnectionError('authorization', provider)
            try:
                tokens = self.http(provider, 'POST', TOKEN, data={'grant_type': 'refresh_token', 'client_id': value['active'],
                    'refresh_token': saved['refresh_token'], 'resource': RESOURCE}).json()
            except AIConnectionError as exc:
                if exc.kind == 'authorization':
                    value['accounts'][value['active']] = {k: v for k, v in saved.items() if k in {'subject', 'email'}}
                    self._save(value)
                raise
            try:
                saved = self.token_record(tokens, saved)
            except (ValueError, TypeError, KeyError):
                raise AIConnectionError('request', provider) from None
            value['accounts'][value['active']] = saved
            self._save(value)
        if 'chatgpt.tokens.use.direct' not in saved.get('scopes', []):
            raise AIConnectionError('permission', provider)
        return saved['access_token']

    def headers(self, provider, credential):
        return {'Authorization': 'Bearer ' + credential} if provider == 'chatgpt' else {'x-api-key': credential, 'anthropic-version': '2023-06-01'}

    def models(self, provider, credential=None):
        with self.lock:
            credential = credential or self.credential(provider)
            url = RESOURCE + '/models' if provider == 'chatgpt' else 'https://api.anthropic.com/v1/models'
            try:
                body = self.http(provider, 'GET', url, headers=self.headers(provider, credential)).json()
                entries = body['models'] if provider == 'chatgpt' else body['data']
                return [{'id': item['slug'] if provider == 'chatgpt' else item['id'], 'name': item['display_name']}
                        for item in entries if provider != 'chatgpt' or item.get('visibility') == 'list']
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, AIConnectionError):
                    raise
                raise AIConnectionError('request', provider) from None

    def connect_claude(self, key):
        with self.lock:
            self.models('claude', key)  # Verify before replacing an existing credential.
            value = self._load()
            value['claude_key'] = key
            self._save(value)
        return self.status()

    def disconnect(self, provider):
        if provider == 'chatgpt' and not self.local_chatgpt:
            raise AIConnectionError('local_required', provider)
        with self.lock:
            value = self._load()
            message = 'Claude API key removed from this tracker.'
            if provider == 'claude':
                value.pop('claude_key', None)
            else:
                self.generation += 1
                self.pending.clear()
                saved = value['accounts'].get(value['active'], {})
                message = 'ChatGPT disconnected.'
                if saved.get('refresh_token'):
                    try:
                        discovery = self.http(provider, 'GET', ISSUER + '/.well-known/openid-configuration').json()
                        endpoint = discovery['revocation_endpoint']
                        if urlsplit(endpoint).scheme != 'https' or urlsplit(endpoint).netloc != 'auth.openai.com':
                            raise ValueError()
                        self.http(provider, 'POST', endpoint, data={'token': saved['refresh_token'], 'token_type_hint': 'refresh_token', 'client_id': value['active']})
                    except (AIConnectionError, ValueError, KeyError, TypeError):
                        message = 'Disconnected locally. Remote revocation was not confirmed; remove this app in ChatGPT Settings → Usage.'
                if value['active'] in value['accounts']:
                    value['accounts'][value['active']] = {k: v for k, v in saved.items() if k in {'subject', 'email'}}
                value['active'] = None
            self._save(value)
        return {'message': message, 'connections': self.status()}

    def test(self, provider, model):
        with self.lock:
            credential = self.credential(provider)
            if model not in {item['id'] for item in self.models(provider, credential)}:
                raise AIConnectionError('request', provider)
            if provider == 'claude':
                self.http(provider, 'POST', 'https://api.anthropic.com/v1/messages', headers=self.headers(provider, credential),
                          json={'model': model, 'max_tokens': 16, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}]})
            else:
                try:
                    with httpx.Client(transport=self.transport, timeout=30, follow_redirects=False) as client:
                        with client.stream('POST', RESOURCE + '/responses', headers=self.headers(provider, credential),
                                           json={'model': model, 'input': [{'role': 'user', 'content': 'Reply with OK.'}], 'store': False, 'stream': True}) as response:
                            if response.status_code != 200:
                                response.read()
                                raise provider_error(provider, response)
                            completed, size, data = False, 0, []
                            for line in response.iter_lines():
                                size += len(line)
                                if size > 1024 * 1024:
                                    raise AIConnectionError('request', provider)
                                if line.startswith('data:'):
                                    data.append(line[5:].strip())
                                elif not line and data:
                                    event = json.loads('\n'.join(data)); data = []
                                    if event.get('type') in {'response.failed', 'error'}:
                                        raise provider_error(provider, error=event.get('response', {}).get('error') or event.get('error') or event)
                                    if event.get('type') == 'response.incomplete':
                                        raise AIConnectionError('request', provider)
                                    if event.get('type') == 'response.completed':
                                        completed = True
                            if not completed:
                                raise AIConnectionError('unavailable', provider)
                except httpx.HTTPError:
                    raise AIConnectionError('unavailable', provider) from None
                except (ValueError, TypeError) as exc:
                    if isinstance(exc, AIConnectionError):
                        raise
                    raise AIConnectionError('request', provider) from None
        return {'message': 'AI access verified. This test used a small amount of provider usage.'}


def router():
    routes = APIRouter(prefix='/api/connections/ai')

    def service(request):
        if request.headers.get('authorization'):
            raise HTTPException(403, 'Manage AI connections from the human workspace')
        request.app.state.human_access.require_local(request)
        settings = request.app.state.settings
        origin = settings.app_public_url if settings.app_mode == 'hosted' else f'http://{settings.app_host}:{settings.app_port}'
        if str(request.base_url).rstrip('/') != origin:
            raise HTTPException(421, 'Use the configured workspace address for AI connections')
        if request.method not in {'GET', 'HEAD'} and request.headers.get('origin') != origin:
            raise HTTPException(403, 'Manage AI connections from this workspace')
        return request.app.state.ai_connections

    @routes.get('')
    def status(request: Request):
        return service(request).status()

    @routes.post('/chatgpt/start')
    def start(data: StartChatGPT, request: Request):
        ai = service(request)
        binding = secrets.token_urlsafe(32)
        owner = request.app.state.human_access.connection_owner(request)
        url = ai.start(data.account, binding, owner)
        response = JSONResponse({'authorization_url': url})
        response.set_cookie(COOKIE, binding, httponly=True, samesite='lax', max_age=600, path='/api/connections/ai/chatgpt')
        return response

    @routes.get('/chatgpt/callback')
    def callback(request: Request, state: str = '', code: str = '', client_id: str = '', error: str = ''):
        ai = service(request)
        try:
            ai.finish(state, code, client_id, request.cookies.get(COOKIE, ''),
                      request.app.state.human_access.connection_owner(request), bool(error))
            result = 'connected'
        except AIConnectionError as exc:
            result = exc.kind
        response = RedirectResponse('/#/settings?tab=connections&provider=chatgpt&ai_result=' + result, status_code=303)
        response.delete_cookie(COOKIE, path='/api/connections/ai/chatgpt')
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @routes.put('/claude')
    def claude(data: ClaudeKey, request: Request):
        return service(request).connect_claude(data.api_key.get_secret_value().strip())

    @routes.get('/{provider}/models')
    def models(provider: Provider, request: Request):
        return service(request).models(provider)

    @routes.post('/{provider}/test')
    def test(provider: Provider, data: TestAI, request: Request):
        return service(request).test(provider, data.model)

    @routes.post('/{provider}/disconnect')
    def disconnect(provider: Provider, request: Request):
        return service(request).disconnect(provider)

    return routes
