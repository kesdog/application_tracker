"""Single-workspace human login; opaque sessions never authorize agent operations."""
import argparse
import getpass
import hashlib
import hmac
import secrets
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


def authenticated(engine, settings, token: str | None) -> bool:
    if not token or len(token) > 100:
        return False
    with Session(engine) as session:
        item = session.get(HumanSession, digest(token))
        return bool(item and item.expires_at > utc_now() and hmac.compare_digest(item.credential_fingerprint, fingerprint(settings)))


def require_origin(request, settings):
    if request.headers.get("origin") != settings.app_public_url:
        raise HTTPException(403, "Request origin does not match this workspace")


def check_transport(request, settings):
    public = urlsplit(settings.app_public_url)
    if request.url.netloc.lower() != public.netloc:
        raise HTTPException(421, "Use the configured workspace address")
    if request.url.scheme != public.scheme:
        raise HTTPException(400, "Use HTTPS to access this workspace")


def record_attempt(engine, address: str):
    now = utc_now()
    keys = [(digest("ip:" + address), 10), (digest("workspace"), 100)]
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        session.execute(delete(LoginAttempt).where(LoginAttempt.window_started_at < now - WINDOW))
        rows = []
        for key, limit in keys:
            item = session.get(LoginAttempt, key)
            if item and item.attempts >= limit:
                seconds = max(1, int((item.window_started_at + WINDOW - now).total_seconds()))
                raise HTTPException(429, "Too many sign-in attempts. Try again later.", headers={"Retry-After": str(seconds)})
            if not item:
                item = LoginAttempt(key=key, attempts=0, window_started_at=now)
                session.add(item)
            rows.append(item)
        for item in rows:
            item.attempts += 1
        session.commit()


def create_session(engine, settings, old_token: str | None = None) -> str:
    now, token = utc_now(), secrets.token_urlsafe(32)
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        session.execute(delete(HumanSession).where(HumanSession.expires_at <= now))
        if old_token:
            session.execute(delete(HumanSession).where(HumanSession.token_hash == digest(old_token)))
        existing = session.scalars(select(HumanSession).order_by(HumanSession.created_at.desc())).all()
        for item in existing[19:]:
            session.delete(item)
        session.add(HumanSession(token_hash=digest(token), credential_fingerprint=fingerprint(settings),
                                 expires_at=now + timedelta(hours=settings.app_session_hours)))
        session.commit()
    return token


def revoke(engine, token: str | None):
    if token:
        with Session(engine) as session:
            session.execute(delete(HumanSession).where(HumanSession.token_hash == digest(token)))
            session.commit()


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
