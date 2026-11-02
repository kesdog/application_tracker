"""Google Identity Services sign-in, separate from optional Gmail/Drive consent."""
import hmac
import secrets

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.google_connection import GoogleConnectionError, ISSUER
from app.human_auth import COOKIE, csrf_token, require_origin
from app.oauth_sessions import OAuthSessionError, OAuthSessionManager

CHALLENGE_COOKIE = '__Host-tracker-signin'


class GoogleCredential(BaseModel):
    model_config = ConfigDict(extra='forbid')
    credential: str = Field(min_length=1, max_length=16384)
    state: str = Field(min_length=1, max_length=128)


class GoogleWorkspaceLogin:
    def __init__(self, settings, sessions, limiter, verifier):
        self.settings, self.sessions = settings, sessions
        self.limiter, self.verifier = limiter, verifier
        self.pending = OAuthSessionManager[str](lifetime=300, capacity=100)

    @property
    def subjects(self):
        return {value.strip() for value in self.settings.google_login_subjects.split(',') if value.strip()}

    @property
    def configured(self):
        return bool(self.settings.app_mode == 'hosted' and self.settings.google_client_id and self.subjects)

    def providers(self):
        return {'google': {'available': self.configured,
                           'client_id': self.settings.google_client_id if self.configured else None}}

    def require_request(self, request):
        if not self.configured:
            raise HTTPException(409, 'Google sign-in requires GOOGLE_CLIENT_ID and GOOGLE_LOGIN_SUBJECTS on a hosted workspace. Use the workspace password or contact its owner.')
        require_origin(request, self.settings)
        if request.headers.get('content-type', '').split(';')[0].lower() != 'application/json':
            raise HTTPException(415, 'Use a JSON sign-in request')
        self.limiter.record(request.client.host if request.client else 'unknown')

    def start(self, request, response):
        self.require_request(request)
        binding, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        try:
            state = self.pending.create(binding, 'google-workspace', nonce)
        except OAuthSessionError:
            raise HTTPException(429, 'Sign-in is busy. Try again in five minutes.') from None
        response.set_cookie(CHALLENGE_COOKIE, binding, max_age=300, secure=True,
                            httponly=True, samesite='strict', path='/')
        return {'state': state, 'nonce': nonce}

    def finish(self, data, request, response):
        self.require_request(request)
        try:
            nonce = self.pending.consume(data.state, request.cookies.get(CHALLENGE_COOKIE, ''), 'google-workspace')
        except OAuthSessionError:
            raise HTTPException(401, 'Google sign-in expired or belongs to another browser. Try again.') from None
        try:
            claims = self.verifier(data.credential, self.settings.google_client_id)
            if (claims.get('iss') not in {ISSUER, 'accounts.google.com'}
                    or claims.get('aud') != self.settings.google_client_id
                    or claims.get('email_verified') is not True
                    or not isinstance(claims.get('nonce'), str)
                    or not hmac.compare_digest(claims['nonce'], nonce)
                    or claims.get('sub') not in self.subjects):
                raise ValueError
        except (GoogleConnectionError, ValueError, TypeError, AttributeError):
            raise HTTPException(401, 'This Google identity could not be verified for this workspace. Use an allowed account or the workspace password.') from None
        token = self.sessions.create(request.cookies.get(COOKIE))
        self.sessions.set_cookie(response, token)
        response.delete_cookie(CHALLENGE_COOKIE, secure=True, httponly=True, samesite='strict', path='/')
        return {'enabled': True, 'authenticated': True, 'csrf_token': csrf_token(token)}
