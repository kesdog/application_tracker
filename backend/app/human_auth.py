"""Single-workspace human login; opaque sessions never authorize agent operations."""
import argparse
import getpass
import hashlib
import hmac
import secrets
import threading
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models import HumanSession, LoginAttempt, utc_now

COOKIE = "__Host-tracker-session"
N, R, P = 32768, 8, 3
WINDOW = timedelta(minutes=15)


def hash_password(password: str) -> str:
    if len(password) < 14 or len(password) > 1024:
        raise ValueError("Use a password of 14–1024 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, maxmem=128 * 1024 * 1024)
    return f"scrypt${N}${R}${P}${salt.hex()}${derived.hex()}"


def validate_password_hash(value: str) -> bool:
    try:
        kind, n, r, p, salt, derived = value.split("$")
        return (kind == "scrypt" and (int(n), int(r), int(p)) == (N, R, P)
                and len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(derived)) == 64)
    except (ValueError, TypeError):
        return False


def verify_password(password: str, encoded: str) -> bool:
    if not validate_password_hash(encoded):
        return False
    _, _, _, _, salt, expected = encoded.split("$")
    derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=N, r=R, p=P, maxmem=128 * 1024 * 1024)
    return hmac.compare_digest(derived, bytes.fromhex(expected))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(settings) -> str:
    return digest(settings.app_password_hash.get_secret_value())


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"tracker-human-csrf-v1", hashlib.sha256).hexdigest()


def require_origin(request, settings):
    if request.headers.get("origin") != settings.app_public_url:
        raise HTTPException(403, "Request origin does not match this workspace")


def check_transport(request, settings):
    public = urlsplit(settings.app_public_url)
    if request.url.netloc.lower() != public.netloc:
        raise HTTPException(421, "Use the configured workspace address")
    if request.url.scheme != public.scheme:
        raise HTTPException(400, "Use HTTPS to access this workspace")


class HumanSessionManager:
    """Own browser session persistence, expiry, revocation and cookie lifecycle."""
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def is_authenticated_reference(self, reference: str) -> bool:
        """Validate a server-held session digest, including pending OAuth owners."""
        if not reference or len(reference) != 64:
            return False
        with Session(self.engine) as session:
            item = session.get(HumanSession, reference)
            return bool(item and item.expires_at > utc_now()
                and hmac.compare_digest(item.credential_fingerprint, fingerprint(self.settings)))

    def is_authenticated(self, token: str | None) -> bool:
        return bool(token and len(token) <= 100 and self.is_authenticated_reference(digest(token)))

    def status(self, token: str | None) -> dict:
        if self.settings.app_mode == 'local':
            return {'enabled': False, 'authenticated': True, 'csrf_token': None}
        valid = self.is_authenticated(token)
        return {'enabled': True, 'authenticated': valid, 'csrf_token': csrf_token(token) if valid else None}

    def create(self, old_token: str | None = None) -> str:
        now, token = utc_now(), secrets.token_urlsafe(32)
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            session.execute(delete(HumanSession).where(HumanSession.expires_at <= now))
            if old_token:
                session.execute(delete(HumanSession).where(HumanSession.token_hash == digest(old_token)))
            existing = session.scalars(select(HumanSession).order_by(HumanSession.created_at.desc())).all()
            for item in existing[19:]:
                session.delete(item)
            session.add(HumanSession(token_hash=digest(token), credential_fingerprint=fingerprint(self.settings),
                expires_at=now + timedelta(hours=self.settings.app_session_hours)))
            session.commit()
        return token

    def revoke(self, token: str | None):
        if token:
            with Session(self.engine) as session:
                session.execute(delete(HumanSession).where(HumanSession.token_hash == digest(token)))
                session.commit()

    def set_cookie(self, response, token: str):
        response.set_cookie(COOKIE, token, max_age=self.settings.app_session_hours * 3600,
            secure=True, httponly=True, samesite='strict', path='/')

    def clear_cookie(self, response):
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict', path='/')


class LoginAttemptLimiter:
    """Persistent per-address and workspace limits, independent of session state."""
    def __init__(self, engine):
        self.engine = engine

    def record(self, address: str):
        now = utc_now()
        keys = [(digest('ip:' + address), 10), (digest('workspace'), 100)]
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            session.execute(delete(LoginAttempt).where(LoginAttempt.window_started_at < now - WINDOW))
            rows = []
            for key, limit in keys:
                item = session.get(LoginAttempt, key)
                if item and item.attempts >= limit:
                    seconds = max(1, int((item.window_started_at + WINDOW - now).total_seconds()))
                    raise HTTPException(429, 'Too many sign-in attempts. Try again later.', headers={'Retry-After': str(seconds)})
                if not item:
                    item = LoginAttempt(key=key, attempts=0, window_started_at=now)
                    session.add(item)
                rows.append(item)
            for item in rows:
                item.attempts += 1
            session.commit()


class HumanLoginManager:
    """Verify a login attempt, then ask the session manager to issue a session."""
    def __init__(self, settings, sessions: HumanSessionManager, *, limiter=None, password_verifier=None):
        self.settings, self.sessions = settings, sessions
        self.limiter = limiter or LoginAttemptLimiter(sessions.engine)
        self.password_verifier = password_verifier or verify_password
        self.password_slots = threading.BoundedSemaphore(2)

    def sign_in(self, password: str, request, response) -> dict:
        if self.settings.app_mode != 'hosted':
            raise HTTPException(404, 'Hosted sign-in is not enabled')
        require_origin(request, self.settings)
        if request.headers.get('content-type', '').split(';')[0].lower() != 'application/json':
            raise HTTPException(415, 'Use a JSON sign-in request')
        self.limiter.record(request.client.host if request.client else 'unknown')
        if not self.password_slots.acquire(blocking=False):
            raise HTTPException(429, 'Sign-in is busy. Try again shortly.', headers={'Retry-After': '2'})
        try:
            if not self.password_verifier(password, self.settings.app_password_hash.get_secret_value()):
                raise HTTPException(401, 'Incorrect workspace password')
        finally:
            self.password_slots.release()
        token = self.sessions.create(request.cookies.get(COOKIE))
        self.sessions.set_cookie(response, token)
        return {'enabled': True, 'authenticated': True, 'csrf_token': csrf_token(token)}

    def sign_out(self, request, response) -> dict:
        if self.settings.app_mode == 'hosted':
            self.sessions.revoke(request.cookies.get(COOKIE))
        self.sessions.clear_cookie(response)
        return {'authenticated': False}


class HumanAccessPolicy:
    """Shared request policy for API routes, event streams and OAuth linking."""
    def __init__(self, settings, sessions: HumanSessionManager):
        self.settings, self.sessions = settings, sessions

    def require_local(self, request):
        if self.settings.app_mode == 'local' and request.client and request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
            raise HTTPException(403, 'Local access required')

    def authorize(self, request):
        path = request.url.path
        if self.settings.app_mode == 'local':
            if not path.startswith('/api/agent/'):
                self.require_local(request)
            return
        if path == '/api/health':
            return
        check_transport(request, self.settings)
        public = path in {'/api/auth/session', '/api/auth/login', '/api/connections/google/callback'}
        if not path.startswith('/api/') or path.startswith('/api/agent/') or public:
            return
        token = request.cookies.get(COOKIE)
        if not self.sessions.is_authenticated(token):
            raise HTTPException(401, 'Sign in to your workspace')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            require_origin(request, self.settings)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf_token(token)):
                raise HTTPException(403, 'Refresh the page before saving; the security token is missing or invalid')

    def connection_owner(self, request) -> str | None:
        self.require_local(request)
        origin = self.settings.app_public_url if self.settings.app_mode == 'hosted' else f'http://{self.settings.app_host}:{self.settings.app_port}'
        if str(request.base_url).rstrip('/') != origin:
            raise HTTPException(421, 'Use the configured workspace address for Google connections')
        if request.method == 'POST' and request.headers.get('origin') != origin:
            raise HTTPException(403, 'Start Google connection actions from this workspace')
        token = request.cookies.get(COOKIE)
        return digest(token) if token else (digest('local') if self.settings.app_mode == 'local' else None)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)


def password_cli():
    parser = argparse.ArgumentParser(description="Create a hosted-workspace password hash without storing the password")
    parser.add_argument("--output", type=Path, required=True, help="New secret file to create (never overwrites an existing file)")
    args = parser.parse_args()
    password = getpass.getpass("Workspace password (at least 14 characters): ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    try:
        encoded = hash_password(password)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            args.output.chmod(0o600)
            handle.write(encoded + "\n")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Password hash saved to {args.output}; keep this file out of version control.")


if __name__ == "__main__":
    password_cli()
