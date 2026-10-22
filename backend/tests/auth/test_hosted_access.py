import asyncio
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.human_auth import COOKIE, csrf_token, digest, hash_password, validate_password_hash, verify_password
from app.models import HumanSession, LoginAttempt, utc_now
from app import invalidation
from app.backup import backup_workspace, restore_workspace

ORIGIN = "https://tracker.example.test"
PASSWORD = "test workspace password only"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def hosted(tmp_path, password_hash):
    settings = Settings(app_data_dir=tmp_path / "source", app_mode="hosted", app_public_url=ORIGIN, app_password_hash=password_hash, _env_file=None)
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN, client=("198.51.100.5", 12345)) as client:
        yield client, app, settings


def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"password": password}, headers={"Origin": ORIGIN})


def headers(client):
    return {"Origin": ORIGIN, "X-CSRF-Token": client.get("/api/auth/session").json()["csrf_token"]}


def test_workspace_recovery_requires_login_and_csrf(hosted):
    client, _, _ = hosted
    assert client.get('/api/workspace/trash').status_code == 401
    assert client.post('/api/workspace/backup').status_code == 401
    login(client)
    assert client.post('/api/workspace/backup').status_code == 403
    assert client.get('/api/workspace/trash').status_code == 200
    assert client.get('/api/workspace/trash', headers={'Authorization': 'Bearer agent'}).status_code == 403


def test_google_connection_management_uses_human_session_csrf_and_callback_binding(hosted):
    client, _, _ = hosted
    assert client.get('/api/connections').status_code == 401
    assert client.get('/api/connections/google/callback?code=x&state=x').status_code == 409
    assert login(client).status_code == 200
    assert client.post('/api/connections/google/start', json={'capabilities': ['gmail_read']}).status_code == 403
    assert client.post('/api/connections/google/disconnect', headers={'Origin': ORIGIN}).status_code == 403
    assert client.post('/api/connections/google/disconnect', headers=headers(client)).status_code == 200
    assert client.get('/api/connections/google/callback?code=x&state=x').status_code == 409


def test_password_hashes_and_fail_closed_configuration(tmp_path, password_hash):
    assert validate_password_hash(password_hash)
    assert verify_password(PASSWORD, password_hash) and not verify_password("wrong", password_hash)
    assert PASSWORD not in password_hash and hash_password(PASSWORD) != password_hash
    for changes in ({"app_mode": "hosted"}, {"app_allow_remote_human": True},
                    {"app_mode": "hosted", "app_public_url": "http://example.test", "app_password_hash": password_hash},
                    {"app_mode": "hosted", "app_public_url": ORIGIN + "/path", "app_password_hash": password_hash},
                    {"app_mode": "hosted", "app_public_url": "http://localhost", "app_host": "0.0.0.0", "app_password_hash": password_hash}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **changes)
    secret = tmp_path / "password.hash"
    secret.write_text(password_hash)
    config = Settings(app_mode="hosted", app_public_url=ORIGIN, app_password_hash_file=secret, _env_file=None)
    assert config.app_password_hash.get_secret_value() == password_hash
    assert password_hash not in repr(config)


def test_local_operation_remains_local_and_requires_no_sign_in(tmp_path):
    app = create_app(Settings(app_data_dir=tmp_path, _env_file=None))
    with TestClient(app) as client:
        assert client.get("/api/auth/session").json() == {"enabled": False, "authenticated": True, "csrf_token": None}
        assert client.get("/api/applications").status_code == 200
    with TestClient(app, client=("198.51.100.5", 12345)) as remote:
        assert remote.get("/api/applications").status_code == 403


def test_unauthenticated_requests_cannot_read_workspace_or_use_agent_tokens(hosted):
    client, _, _ = hosted
    for path in ("/api/applications", "/api/settings/general", "/api/settings/agent", "/api/followups", "/api/events", "/api/documents/x", "/api/exports/applications.csv", "/api/interviews/x/calendar.ics"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/applications", json={}).status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/session").json()["authenticated"] is False
    login(client)
    token = client.post("/api/settings/agent/token", headers=headers(client)).json()["token"]
    client.cookies.clear()
    assert client.get("/api/applications", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert client.post("/api/agent/tools/list_applications", headers={"Authorization": "Bearer " + token}, json={}).status_code == 200


def test_login_cookie_session_storage_logout_and_csrf(hosted):
    client, app, _ = hosted
    assert login(client, "wrong password").status_code == 401
    signed_in = login(client)
    assert signed_in.status_code == 200
    assert client.get('/api/settings/agent/connection').json()['rest_endpoint'] == ORIGIN + '/api/agent/'
    cookie = signed_in.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie and "Domain=" not in cookie
    token = client.cookies.get(COOKIE)
    with Session(app.state.engine) as session:
        stored = session.get(HumanSession, digest(token))
        assert stored and token not in str(stored.__dict__) and PASSWORD not in str(stored.__dict__)
    assert client.get("/api/applications").status_code == 200
    assert client.post("/api/settings/agent/token").status_code == 403
    assert client.post("/api/settings/agent/token", headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf_token(token)}).status_code == 403
    assert client.post("/api/settings/agent/token", headers=headers(client)).status_code == 200
    assert client.post("/api/agent/tools/list_applications", json={}).status_code == 401
    assert client.post("/api/auth/logout", headers=headers(client)).status_code == 200
    client.cookies.set(COOKIE, token)
    assert client.get("/api/applications").status_code == 401


def test_login_requires_same_origin_and_transport_checks_cannot_be_forged(hosted):
    client, _, _ = hosted
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 403
    assert client.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.get("http://tracker.example.test/api/auth/session").status_code == 400
    assert client.get("https://evil.test/api/auth/session").status_code == 421
    assert client.get("http://tracker.example.test/api/auth/session", headers={"X-Forwarded-Proto": "https"}).status_code == 400


def test_expiration_password_change_and_restart(hosted, password_hash):
    client, app, config = hosted
    login(client)
    token = client.cookies.get(COOKIE)
    restarted = create_app(config)
    with TestClient(restarted, base_url=ORIGIN) as second:
        second.cookies.set(COOKIE, token)
        assert second.get("/api/applications").status_code == 200
    with Session(app.state.engine) as session:
        session.get(HumanSession, digest(token)).expires_at = utc_now() - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/applications").status_code == 401
    login(client)
    token = client.cookies.get(COOKIE)
    changed = config.model_copy(update={"app_password_hash": Settings(app_mode="hosted", app_public_url=ORIGIN, app_password_hash=hash_password("changed test password only"), _env_file=None).app_password_hash})
    with TestClient(create_app(changed), base_url=ORIGIN) as other:
        other.cookies.set(COOKIE, token)
        assert other.get("/api/applications").status_code == 401


def test_login_rate_limit_survives_restart_without_storing_passwords(hosted):
    client, app, config = hosted
    for _ in range(10):
        assert login(client, "wrong").status_code == 401
    limited = login(client)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    with TestClient(create_app(config), base_url=ORIGIN, client=("198.51.100.5", 12345)) as restarted:
        assert login(restarted).status_code == 429
    with Session(app.state.engine) as session:
        assert all(len(item.key) == 64 and PASSWORD not in str(item.__dict__) for item in session.scalars(select(LoginAttempt)))


def test_sse_stops_when_authorization_is_revoked(hosted):
    _, app, _ = hosted
    allowed = [True]
    async def read():
        source = invalidation.stream(app.state.engine, authorized=lambda: allowed[0])
        assert await anext(source) == ": connected\n\n"
        allowed[0] = False
        assert "auth.expired" in await anext(source)
        with pytest.raises(StopAsyncIteration):
            await anext(source)
    asyncio.run(read())


def test_portable_backup_restore_preserves_messages_documents_and_revokes_sessions(hosted, tmp_path):
    client, _, config = hosted
    login(client)
    app = client.post("/api/applications", headers=headers(client), json={"company": "Backup Example", "job_title": "Engineer", "date_applied": "2026-10-01", "email_reference": "Reference"}).json()
    document = client.post(f"/api/applications/{app['id']}/documents", headers=headers(client), data={"document_type": "CV"}, files={"file": ("cv.txt", b"CV content", "text/plain")})
    assert document.status_code == 201, document.text
    backup = tmp_path / "backup"
    backup_workspace(config.app_data_dir, backup)
    target = tmp_path / "restored"
    restore_workspace(backup, target)
    with TestClient(create_app(Settings(app_data_dir=target, _env_file=None))) as restored:
        assert restored.get("/api/applications").json()[0]['id'] == app['id']
        assert restored.get(f"/api/applications/{app['id']}/work").json()['followups'][0]['body']
        content = restored.get(f"/api/applications/{app['id']}/documents/{document.json()['id']}/content")
        assert content.content == b"CV content"
        with Session(restored.app.state.engine) as session:
            assert session.scalars(select(HumanSession)).all() == []
    with pytest.raises(ValueError, match="empty"):
        restore_workspace(backup, target)


def test_restore_relocates_windows_paths_on_any_platform_and_rejects_corruption(tmp_path):
    from app.backup import checksum
    source = tmp_path / "windows-backup"
    document = source / "documents" / "job" / "cv.txt"
    document.parent.mkdir(parents=True)
    document.write_text("Portable CV")
    database = source / "tracker.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE application_documents (id TEXT, storage_path TEXT)")
        connection.execute("INSERT INTO application_documents VALUES (?, ?)", ("doc", r"D:\Tracker\data\documents\job\cv.txt"))
    metadata = {"version": 1, "source_platform": "nt", "source_data_dir": r"D:\Tracker\data", "database_sha256": checksum(database)}
    (source / "backup.json").write_text(json.dumps(metadata))
    target = tmp_path / "relocated"
    restore_workspace(source, target)
    with sqlite3.connect(target / "tracker.sqlite3") as connection:
        stored = connection.execute("SELECT storage_path FROM application_documents").fetchone()[0]
    assert Path(stored) == target / "documents" / "job" / "cv.txt"
    assert Path(stored).read_text() == "Portable CV"
    with database.open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        restore_workspace(source, tmp_path / "corrupt-destination")
    assert not (tmp_path / "corrupt-destination").exists()


@pytest.mark.parametrize('context', ['valid', 'revoked', 'expired', 'password_changed', 'other_session', 'missing_browser'])
def test_google_callback_without_strict_cookie_requires_the_active_initiating_session(hosted, context):
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlsplit
    import httpx
    from pydantic import SecretStr
    from app.google_connection import COOKIE as LINK_COOKIE, SCOPES

    client, app, settings = hosted
    google = app.state.google
    settings.google_client_id = 'test-client'
    settings.google_redirect_uri = ORIGIN + '/api/connections/google/callback'
    credentials = {}
    google.store = SimpleNamespace(put=lambda key, value: credentials.update({key: value}),
        get=credentials.get, delete=lambda key: credentials.pop(key, None))
    google.transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        'id_token': 'verified-test-token', 'access_token': 'access', 'refresh_token': 'refresh',
        'scope': SCOPES['gmail_read'], 'expires_in': 3600}))
    assert login(client).status_code == 200
    owner = client.cookies.get(COOKIE)
    started = client.post('/api/connections/google/start', json={'capabilities': ['gmail_read']}, headers=headers(client))
    assert started.status_code == 200
    assert 'SameSite=lax' in started.headers['set-cookie']
    params = parse_qs(urlsplit(started.json()['authorization_url']).query)
    google.verifier = lambda token, audience: {'iss': 'https://accounts.google.com', 'aud': audience,
        'sub': 'google-owner', 'email': 'owner@example.test', 'email_verified': True, 'nonce': params['nonce'][0]}
    binding = client.cookies.get(LINK_COOKIE)
    if context == 'revoked':
        assert client.post('/api/auth/logout', headers=headers(client)).status_code == 200
    elif context == 'expired':
        with Session(app.state.engine) as session:
            session.get(HumanSession, digest(owner)).expires_at = utc_now() - timedelta(seconds=1)
            session.commit()
    elif context == 'password_changed':
        settings.app_password_hash = SecretStr(hash_password('replacement workspace test password'))
    # Simulate the real cross-site return: Lax link cookie present, Strict cookie absent.
    client.cookies.clear()
    if context != 'missing_browser':
        client.cookies.set(LINK_COOKIE, binding, path='/api/connections/google')
    if context == 'other_session':
        client.cookies.set(COOKIE, app.state.human_sessions.create())
    callback = {'state': params['state'][0], 'code': 'test-code'}
    response = client.get('/api/connections/google/callback', params=callback, follow_redirects=False)
    assert response.status_code == (303 if context == 'valid' else 409)
    assert len(credentials) == (1 if context == 'valid' else 0)
    if context == 'valid':
        assert client.get('/api/connections/google/callback', params=callback, follow_redirects=False).status_code == 409


def test_session_managers_share_persistence_and_revocation(hosted):
    from app.human_auth import HumanSessionManager
    _, app, settings = hosted
    first = app.state.human_sessions
    second = HumanSessionManager(app.state.engine, settings)
    token = first.create()
    assert second.is_authenticated(token)
    replacement = second.create(token)
    assert not first.is_authenticated(token)
    assert first.is_authenticated(replacement)
    second.revoke(replacement)
    assert not first.is_authenticated_reference(digest(replacement))
