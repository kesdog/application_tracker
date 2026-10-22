"""Tracker-owned Google connection. No token material crosses the human/agent API."""
import base64
import hashlib
import json
import logging
import re
import secrets
import time
from email.message import EmailMessage
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import ExternalConnection, utc_now
from app.authorized_api import AuthorizedApiClient, AuthorizedRequestError, TokenLease

SCOPES = {
    'drive': 'https://www.googleapis.com/auth/drive.appdata',
    'gmail_read': 'https://www.googleapis.com/auth/gmail.readonly',
    'gmail_drafts': 'https://www.googleapis.com/auth/gmail.compose',
}
COOKIE = 'tracker-google-link'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
ISSUER = 'https://accounts.google.com'


class CallbackLogFilter(logging.Filter):
    """Uvicorn access logs must not retain authorization codes or state."""
    def filter(self, record):
        message = record.getMessage()
        if '/api/connections/google/callback?' in message:
            record.msg = re.sub(r'(/api/connections/google/callback)\?[^\s"\']+', r'\1?[redacted]', message)
            record.args = ()
        return True


class GoogleConnectionError(ValueError):
    """Only fixed, non-sensitive messages are exposed to API callers."""
    def __init__(self, message, *, kind='authorization', retry_after=None):
        super().__init__(message)
        self.kind, self.retry_after = kind, retry_after


class GoogleStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    capabilities: list[str] = Field(min_length=1, max_length=3)


class DriveTest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recovery_key: str = Field(min_length=43, max_length=44)


class MailSearch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=25)


class MailLookup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str = Field(pattern=r'^[a-fA-F0-9]{1,64}$')


class NativeSecretStore:
    """Reject fallback/chained/plaintext backends, including keyrings.alt."""
    def __init__(self, workspace):
        self.service = 'ApplicationTracker:google:' + hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()

    def backend(self):
        try:
            import keyring
            backend = keyring.get_keyring()
            allowed = {
                ('keyring.backends.Windows', 'WinVaultKeyring'),
                ('keyring.backends.macOS', 'Keyring'),
                ('keyring.backends.SecretService', 'Keyring'),
                ('keyring.backends.kwallet', 'DBusKeyring'),
                ('keyring.backends.kwallet', 'DBusKeyringKWallet4'),
                ('keyring.backends.kwallet', 'DBusKeyringKWallet5'),
            }
            if (type(backend).__module__, type(backend).__name__) not in allowed:
                raise RuntimeError
            return backend
        except Exception:
            raise GoogleConnectionError('Unlock or configure a native OS credential store (Windows Credential Manager, macOS Keychain or Secret Service/KWallet), then reconnect Google.') from None

    def get(self, reference):
        try:
            value = self.backend().get_password(self.service, reference)
            return json.loads(value) if value else None
        except GoogleConnectionError:
            raise
        except Exception:
            raise GoogleConnectionError('Google credentials are unavailable in the OS credential store. Unlock it or reconnect Google.') from None

    def put(self, reference, value):
        try:
            encoded = json.dumps(value)
            backend = self.backend()
            backend.set_password(self.service, reference, encoded)
            if backend.get_password(self.service, reference) != encoded:
                raise RuntimeError
        except Exception:
            raise GoogleConnectionError('Unable to save Google credentials safely. Unlock the native OS credential store and reconnect.') from None

    def delete(self, reference):
        if not reference:
            return
        try:
            backend = self.backend()
            if backend.get_password(self.service, reference) is not None:
                backend.delete_password(self.service, reference)
        except Exception:
            raise GoogleConnectionError('Unable to remove Google credentials from the OS store. Unlock it and disconnect again.') from None


def verify_identity(encoded, audience):
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import verify_oauth2_token
    request = Request()
    def bounded_request(*args, **kwargs):
        kwargs['timeout'] = 10
        return request(*args, **kwargs)
    try:
        return verify_oauth2_token(encoded, bounded_request, audience=audience)
    except Exception:
        raise GoogleConnectionError('Google identity verification failed. Start a new connection.') from None


class GoogleConnection:
    def __init__(self, engine, settings, *, store=None, transport=None, verifier=None):
        self.engine, self.settings = engine, settings
        if store is None and settings.app_credential_key_file:
            from app.secret_store import EncryptedFileSecretStore
            store = EncryptedFileSecretStore(settings.app_data_dir, settings.app_credential_key_file)
        self.store = store or NativeSecretStore(settings.app_data_dir)
        self.transport = transport
        self.verifier = verifier or verify_identity
        from app.google_login import GoogleLoginManager
        self.login = GoogleLoginManager(self)

    @property
    def configured(self):
        return bool(self.settings.google_client_id and self.settings.google_redirect_uri)

    def _http(self, method, url, **kwargs):
        try:
            with httpx.Client(transport=self.transport, timeout=10, follow_redirects=False) as client:
                return client.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise GoogleConnectionError('Google could not be reached. Check your connection; retry reads, but reconcile any uncertain mailbox draft before retrying.') from None

    def status(self):
        with Session(self.engine) as session:
            item = session.get(ExternalConnection, 1)
            result = {'configured': self.configured, 'status': item.status if item else 'DISCONNECTED',
                      'email': item.email if item else None, 'capabilities': {key: False for key in SCOPES},
                      'updated_at': item.updated_at.isoformat() + 'Z' if item else None,
                      'verified_at': item.verified_at.isoformat() + 'Z' if item and item.verified_at else None,
                      'message': None}
            if item and item.status in {'CONNECTED', 'PARTIAL'}:
                try:
                    if not item.secret_reference or not self.store.get(item.secret_reference):
                        raise GoogleConnectionError('Google credentials are missing. Reconnect Google on this computer.')
                    result['capabilities'] = {key: scope in item.scopes for key, scope in SCOPES.items()}
                except GoogleConnectionError as exc:
                    result['status'], result['message'] = 'CREDENTIALS_UNAVAILABLE', str(exc)
            return result

    def start(self, capabilities, binding, owner):
        return self.login.start(capabilities, binding, owner)

    def finish(self, state, code, binding, owner, denied=False, *, owner_validator=None):
        return self.login.finish(state, code, binding, owner, denied, owner_validator=owner_validator)

    def disconnect(self):
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            item = session.get(ExternalConnection, 1)
            if not item:
                return self.status()
            self.store.delete(item.secret_reference)
            item.secret_reference, item.subject, item.issuer, item.email = None, None, None, None
            item.status, item.scopes = 'DISCONNECTED', []
            item.generation += 1
            item.updated_at, item.verified_at = utc_now(), None
            session.commit()
        self.login.sessions.clear()
        return self.status()

    def access_token(self, capability):
        # Serialize refreshes with other tracker/MCP processes using SQLite's lock.
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            item = session.get(ExternalConnection, 1)
            if (not item or item.status not in {'CONNECTED', 'PARTIAL'}
                    or SCOPES[capability] not in item.scopes or not item.secret_reference):
                raise GoogleConnectionError('This Google capability is disconnected or needs reauthorization in Settings.')
            secret = self.store.get(item.secret_reference)
            if not secret:
                raise GoogleConnectionError('Google credentials are missing. Reconnect Google on this computer.')
            if secret['expires_at'] <= time.time() + 60:
                data = {'client_id': self.settings.google_client_id, 'refresh_token': secret['refresh_token'], 'grant_type': 'refresh_token'}
                if self.settings.google_client_secret:
                    data['client_secret'] = self.settings.google_client_secret.get_secret_value()
                response = self._http('POST', TOKEN_URL, data=data)
                if response.status_code in {400, 401}:
                    item.status, item.updated_at = 'RECONNECT_REQUIRED', utc_now()
                    session.commit()
                    raise GoogleConnectionError('Google authorization was revoked or expired. Reconnect Google; local tracking and the agent token still work.')
                if response.status_code != 200:
                    raise GoogleConnectionError('Google refresh is temporarily unavailable. Try again later.')
                value = response.json()
                if not value.get('access_token'):
                    raise GoogleConnectionError('Google returned an invalid refresh response. Reconnect Google.')
                secret.update(access_token=value['access_token'], expires_at=time.time() + int(value.get('expires_in', 3600)))
                if value.get('refresh_token'):
                    secret['refresh_token'] = value['refresh_token']
                if 'scope' in value:
                    item.scopes = sorted(set(item.scopes) & set(value['scope'].split()))
                self.store.put(item.secret_reference, secret)
            session.commit()
            if SCOPES[capability] not in item.scopes:
                raise GoogleConnectionError('Google revoked this capability. Reauthorize the requested scopes in Settings.')
            return secret['access_token'], item.generation

    def api(self, capability, method, path, **kwargs):
        def rejected(capability, lease, error):
            with Session(self.engine) as session:
                session.execute(text('BEGIN IMMEDIATE'))
                item = session.get(ExternalConnection, 1)
                if item and item.generation == lease.generation:
                    if error.status == 401:
                        item.status = 'RECONNECT_REQUIRED'
                    else:
                        item.scopes = [scope for scope in item.scopes if scope != SCOPES[capability]]
                        item.status = 'PARTIAL'
                    item.updated_at = utc_now()
                    session.commit()
        leases = []
        def acquire(capability):
            lease = TokenLease(*self.access_token(capability))
            leases.append(lease)
            return lease
        client = AuthorizedApiClient('https://www.googleapis.com/', acquire, self._http, rejected)
        try:
            response = client.call(capability, method, path, **kwargs)
        except AuthorizedRequestError as exc:
            raise GoogleConnectionError(str(exc), kind=exc.kind, retry_after=exc.retry_after) from None
        with Session(self.engine) as session:
            item = session.get(ExternalConnection, 1)
            if item and item.generation == leases[0].generation:
                item.verified_at = utc_now()
                session.commit()
        return response


class GoogleMailProvider:
    def __init__(self, connection):
        self.connection = connection

    def is_connected(self):
        return self.connection.status()['capabilities']['gmail_drafts']

    def create_draft(self, application, followup, content):
        message = EmailMessage()
        message['To'] = followup.recipient_email
        message['Subject'] = followup.subject or f'Follow-up: {application.job_title}'
        message.set_content(content)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = self.connection.api('gmail_drafts', 'POST', 'gmail/v1/users/me/drafts', json={'message': {'raw': raw}}).json()
        account = urlencode({'authuser': self.connection.status()['email'] or ''})
        return 'https://mail.google.com/mail/?' + account + '#drafts/' + result.get('message', {}).get('id', result['id'])

    def open_message(self, reference):
        value = MailLookup(message_id=reference)
        account = urlencode({'authuser': self.connection.status()['email'] or ''})
        return 'https://mail.google.com/mail/?' + account + '#all/' + value.message_id

    def application_messages(self, page_token=None):
        # Fixed query: read application evidence, never mutate mailbox labels or messages.
        params = {'q': '-in:spam -in:trash -in:drafts {candidature application postulé "CV a été envoyé" interview entretien}',
                  'maxResults': 100, 'fields': 'messages(id,threadId),nextPageToken'}
        if page_token:
            params['pageToken'] = page_token
        return self.connection.api('gmail_read', 'GET', 'gmail/v1/users/me/messages', params=params).json()

    def application_message(self, message_id):
        data = MailLookup(message_id=message_id)
        value = self.connection.api('gmail_read', 'GET', f'gmail/v1/users/me/messages/{data.message_id}',
            params={'format': 'full', 'fields': 'id,threadId,internalDate,payload(mimeType,headers,body,parts)'}).json()
        # Bounded MIME body, no attachments or instruction execution. HTML is parsed locally.
        def content(part, depth=0):
            if depth > 12 or part.get('filename'):
                return ''
            if part.get('mimeType') in ('text/html', 'text/plain'):
                try:
                    raw = part.get('body', {}).get('data', '')[:180000]
                    decoded = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8', errors='replace')
                    if part.get('mimeType') == 'text/plain':
                        from html import escape
                        return '<pre>' + escape(decoded[:120000]) + '</pre>'
                    return decoded[:120000]
                except (ValueError, TypeError):
                    return ''
            return ''.join(content(child, depth + 1) for child in part.get('parts', [])[:30])[:120000]
        return {'id': value['id'], 'thread_id': value.get('threadId', ''), 'internal_date': value.get('internalDate'),
                'headers': value.get('payload', {}).get('headers', []), 'content': content(value.get('payload', {}))}

    def search(self, query, limit=10):
        data = MailSearch(query=query, limit=limit)
        value = self.connection.api('gmail_read', 'GET', 'gmail/v1/users/me/messages',
                                    params={'q': data.query, 'maxResults': data.limit, 'fields': 'messages(id,threadId),nextPageToken'}).json()
        return {'messages': value.get('messages', []), 'has_more': bool(value.get('nextPageToken'))}

    def lookup(self, message_id):
        data = MailLookup(message_id=message_id)
        value = self.connection.api('gmail_read', 'GET', f'gmail/v1/users/me/messages/{data.message_id}',
                                    params={'format': 'full', 'fields': 'id,threadId,snippet,internalDate,payload(mimeType,headers,body,parts)'}).json()
        # Bounded plain text only. HTML/attachments remain outside this narrow tool.
        def plain(part):
            result = ''
            if part.get('mimeType') == 'text/plain':
                encoded = part.get('body', {}).get('data', '')[:90000]
                try:
                    result = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode('utf-8', errors='replace')
                except ValueError:
                    pass
            for child in part.get('parts', [])[:20]:
                result += plain(child)
            return result[:60000]
        payload = value.get('payload', {})
        return {'id': value['id'], 'thread_id': value.get('threadId'), 'snippet': value.get('snippet', '')[:2000],
                'headers': [h for h in payload.get('headers', []) if h['name'].lower() in {'from', 'to', 'subject', 'date', 'message-id'}],
                'text': plain(payload), 'untrusted_content': True}


class GoogleDriveProvider:
    def __init__(self, connection):
        self.connection = connection

    def test(self, recovery_key):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            key = base64.b64decode(recovery_key + '=' * (-len(recovery_key) % 4), altchars=b'-_', validate=True)
            if len(key) != 32:
                raise ValueError
        except ValueError:
            raise GoogleConnectionError('Use a user-owned 32-byte base64 recovery key, saved outside Google Drive and tracker tokens.') from None
        cipher, nonce, value = AESGCM(key), secrets.token_bytes(12), secrets.token_bytes(32)
        encrypted = nonce + cipher.encrypt(nonce, value, b'tracker-drive-test-v1')
        metadata = {'name': 'tracker-encrypted-test-' + str(uuid4()), 'parents': ['appDataFolder']}
        boundary = secrets.token_hex(16)
        body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n'
                f'--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + encrypted + f'\r\n--{boundary}--\r\n'.encode()
        # appDataFolder is enforced by the scope and explicit parent; never list user files.
        response = self.connection.api('drive', 'POST', 'upload/drive/v3/files',
            params={'uploadType': 'multipart', 'fields': 'id'},
            headers={'Content-Type': 'multipart/related; boundary=' + boundary}, content=body)
        if response.status_code not in {200, 201}:
            raise GoogleConnectionError('Encrypted Drive test upload failed. Check Drive access and reauthorize if needed.')
        file_id = response.json()['id']
        try:
            downloaded = self.connection.api('drive', 'GET', f'drive/v3/files/{file_id}', params={'alt': 'media'}).content
            if cipher.decrypt(downloaded[:12], downloaded[12:], b'tracker-drive-test-v1') != value:
                raise GoogleConnectionError('Encrypted Drive test verification failed.')
        finally:
            self.connection.api('drive', 'DELETE', f'drive/v3/files/{file_id}')
        return {'verified': True, 'deleted': True, 'message': 'Encrypted app-data test verified and removed. Phone synchronization is not enabled.'}
