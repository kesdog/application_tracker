"""Google login orchestration; connection use and OAuth session storage are separate."""
import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.google_connection import GoogleConnectionError, ISSUER, SCOPES, TOKEN_URL
from app.models import ExternalConnection, utc_now
from app.oauth_sessions import OAuthSessionError, OAuthSessionManager


@dataclass
class GoogleLoginClaims:
    verifier: str
    nonce: str
    capabilities: list[str]
    generation: int
    subject: str | None


class GoogleLoginManager:
    """Start consent, validate its callback, and persist the verified grant."""
    def __init__(self, connection, *, sessions=None):
        self.connection = connection
        self.sessions = sessions or OAuthSessionManager[GoogleLoginClaims]()

    def start(self, capabilities, binding, owner):
        if not self.connection.configured:
            raise GoogleConnectionError('Configure GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI before connecting Google.')
        if not capabilities or set(capabilities) - SCOPES.keys():
            raise GoogleConnectionError('Choose Drive, Gmail read and/or Gmail drafts.')
        probe = 'probe-' + str(uuid4())
        self.connection.store.put(probe, {'probe': secrets.token_hex(8)})
        self.connection.store.delete(probe)
        with Session(self.connection.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            item = session.get(ExternalConnection, 1)
            if not item:
                item = ExternalConnection(id=1, generation=0, scopes=[], status='DISCONNECTED')
                session.add(item)
            item.generation += 1
            item.updated_at = utc_now()
            session.commit()
            generation, subject = item.generation, item.subject
        nonce, verifier = (secrets.token_urlsafe(32) for _ in range(2))
        pending = GoogleLoginClaims(verifier, nonce, sorted(set(capabilities)), generation, subject)
        try:
            state = self.sessions.create(binding, owner, pending)
        except OAuthSessionError as exc:
            raise GoogleConnectionError(str(exc)) from None
        params = {'client_id': self.connection.settings.google_client_id, 'redirect_uri': self.connection.settings.google_redirect_uri,
                  'response_type': 'code', 'scope': ' '.join(['openid', 'email', *[SCOPES[key] for key in pending.capabilities]]),
                  'state': state, 'nonce': nonce, 'access_type': 'offline', 'prompt': 'consent select_account',
                  'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
                  'code_challenge_method': 'S256'}
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)

    def finish(self, state, code, binding, owner, denied=False, *, owner_validator=None):
        try:
            pending = self.sessions.consume(state, binding, owner, owner_validator=owner_validator)
        except OAuthSessionError as exc:
            raise GoogleConnectionError('Google ' + str(exc)) from None
        if denied or not code:
            raise GoogleConnectionError('Google consent was declined. Offline tracking remains available.')
        tokens = self._exchange_code(code, pending.verifier)
        identity, scopes, secret = self._validate_grant(tokens, pending)
        self._persist_connection(pending, identity, scopes, secret)
        return self.connection.status()

    def _exchange_code(self, code, verifier):
        data = {'client_id': self.connection.settings.google_client_id, 'redirect_uri': self.connection.settings.google_redirect_uri,
                'code': code, 'code_verifier': verifier, 'grant_type': 'authorization_code'}
        if self.connection.settings.google_client_secret:
            data['client_secret'] = self.connection.settings.google_client_secret.get_secret_value()
        response = self.connection._http('POST', TOKEN_URL, data=data)
        if response.status_code != 200:
            raise GoogleConnectionError('Google authorization failed. Start a new connection.')
        try:
            return response.json()
        except ValueError:
            raise GoogleConnectionError('Google returned an invalid credential response. Start again.') from None

    def _validate_grant(self, tokens, pending):
        try:
            identity = self.connection.verifier(tokens['id_token'], self.connection.settings.google_client_id)
            if (identity.get('iss') not in {ISSUER, 'accounts.google.com'}
                    or identity.get('aud') != self.connection.settings.google_client_id
                    or not isinstance(identity.get('sub'), str) or not identity.get('sub') or identity.get('email_verified') is not True
                    or not isinstance(identity.get('nonce'), str)
                    or not hmac.compare_digest(identity['nonce'], pending.nonce)):
                raise ValueError
            if pending.subject and pending.subject != identity['sub']:
                raise GoogleConnectionError('This is a different Google account. Reconnect the linked account, or disconnect it explicitly before changing accounts.')
            granted = set(tokens.get('scope', '').split())
            scopes = sorted(granted & {SCOPES[key] for key in pending.capabilities})
            if not tokens.get('access_token') or not tokens.get('refresh_token'):
                raise GoogleConnectionError('Google did not grant offline access. Reauthorize with consent before connecting.')
            secret = {'access_token': tokens['access_token'], 'refresh_token': tokens['refresh_token'],
                      'expires_at': time.time() + int(tokens.get('expires_in', 3600))}
        except GoogleConnectionError:
            raise
        except Exception:
            raise GoogleConnectionError('Google returned an invalid identity or credential response. Start again.') from None
        return identity, scopes, secret

    def _persist_connection(self, pending, identity, scopes, secret):
        with Session(self.connection.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            item = session.get(ExternalConnection, 1)
            if not item or item.generation != pending.generation or item.subject != pending.subject:
                raise GoogleConnectionError('The Google connection changed during sign-in. Start again.')
            old_ref, reference = item.secret_reference, str(uuid4())
            self.connection.store.put(reference, secret)
            item.issuer, item.subject, item.email = ISSUER, identity['sub'], identity.get('email')
            item.scopes, item.secret_reference = scopes, reference
            item.status = 'CONNECTED' if len(scopes) == len(pending.capabilities) else 'PARTIAL'
            item.updated_at = item.verified_at = utc_now()
            session.commit()
        if old_ref:
            self.connection.store.delete(old_ref)
