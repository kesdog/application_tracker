"""Disposable local browser fixture. CLI only; never imported by the application.

Build with `pnpm --dir frontend exec vite build --mode phone-e2e` first.
Run: .venv/Scripts/python.exe backend/tests/sync/browser_server.py .run/phone-browser-fixture
Only synthetic Google tokens and test recovery keys are persisted under .run.
"""
import base64
from contextlib import asynccontextmanager
from datetime import date
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(Path(__file__).parent)]
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
import uvicorn
from app.config import Settings
from app.google_connection import SCOPES
from app.main import create_app
from app.models import Application, ExternalConnection, utc_now
from app.sync.models import SyncWorkspace
from http_drive import DriveHttpStore
from sync_support import MemorySecrets

directory = Path(sys.argv[1]).resolve()
if not directory.is_relative_to(ROOT / '.run'):
    raise ValueError('Browser fixtures must stay inside the ignored .run directory')
directory.mkdir(parents=True, exist_ok=True)
saved = directory / 'synthetic-remote.json'
remote, secrets = DriveHttpStore(), MemorySecrets()
state = json.loads(saved.read_text()) if saved.exists() else {}
remote.files = {key: (name, base64.b64decode(value)) for key, name, value in state.get('files', [])}
remote.feed = [tuple(item) for item in state.get('feed', [])]
secrets.values = state.get('secrets', {})
secrets.put('google', {'access_token': 'test-left', 'refresh_token': 'synthetic-refresh-only', 'expires_at': time.time() + 86400})


def save():
    state.update(files=[(key, name, base64.b64encode(value).decode()) for key, (name, value) in remote.files.items()], feed=remote.feed, secrets=secrets.values)
    saved.write_text(json.dumps(state), encoding='utf-8')


desktop = create_app(Settings(app_data_dir=directory / 'desktop', app_port=8025, google_client_id='desktop.apps.googleusercontent.com',
    google_redirect_uri='http://127.0.0.1:8025/api/connections/google/callback', app_static_dir=ROOT / '.run/phone-browser-build', _env_file=None),
    google_store=secrets, google_transport=httpx.MockTransport(remote.request), sync_background=False)


@asynccontextmanager
async def lifespan(_app):
    async with desktop.router.lifespan_context(desktop):
        with Session(desktop.state.engine) as session:
            if not session.get(ExternalConnection, 1):
                session.add(ExternalConnection(id=1, subject='synthetic-verified-subject', email='synthetic-desktop@example.invalid',
                    scopes=[SCOPES['drive']], status='CONNECTED', secret_reference='google', generation=1, updated_at=utc_now()))
                item = Application(company='Browser fixture employer', job_title='Engineer', date_applied=date(2026, 10, 28), job_url='https://example.invalid/browser-fixture', description='Private desktop fixture text')
                session.add(item); session.commit(); state['application_id'] = item.id
            enrolled = session.get(SyncWorkspace, 1) is not None
        if not enrolled:
            state['recovery'] = desktop.state.sync.initialize('Synthetic desktop')['recovery_export']
            assert desktop.state.sync.run(manual=True)['error'] is None
        save()
        try:
            yield
        finally:
            save()


app = FastAPI(lifespan=lifespan)


@app.api_route('/fixture/google/{path:path}', methods=['GET', 'POST', 'DELETE'])
async def google(request: Request, path: str):
    query = '?' + request.url.query if request.url.query else ''
    response = remote.request(httpx.Request(request.method, 'https://www.googleapis.com/' + path + query, headers=dict(request.headers), content=await request.body()))
    save()
    return Response(content=response.content, status_code=response.status_code, headers={'Content-Type': response.headers.get('content-type', 'application/octet-stream')})


@app.get('/fixture/setup')
def setup():
    return {'synthetic_only': True, 'recovery_export': state['recovery'], 'application_id': state['application_id']}


@app.post('/fixture/offline/{offline}')
def network(offline: bool):
    remote.offline = offline
    return {'synthetic_only': True, 'offline': offline}


@app.post('/fixture/desktop-edit')
async def desktop_edit(request: Request):
    data = await request.json()
    with Session(desktop.state.engine) as session:
        item = session.get(Application, state['application_id'])
        for field in ('company', 'job_title'):
            if field in data:
                setattr(item, field, str(data[field])[:300])
        session.commit()
    result = desktop.state.sync.run(manual=True); save()
    return result


@app.get('/fixture/desktop-state')
def desktop_state():
    result = desktop.state.sync.run(manual=True); save()
    with Session(desktop.state.engine) as session:
        item = session.get(Application, state['application_id'])
        return {'synthetic_only': True, 'company': item.company, 'job_title': item.job_title, 'description': item.description, 'sync': result}


app.mount('/', desktop)
uvicorn.run(app, host='127.0.0.1', port=8025, access_log=False)
