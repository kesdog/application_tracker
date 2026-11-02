"""Synthetic SQLite peer for browser-engine interoperability tests (stdin/stdout JSON)."""
import base64
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).parent))
from sqlalchemy.orm import Session
from app.database import create_database, migrate_database
from app.models import Application
from app.sync.engine import SyncEngine
from app.sync.models import SyncWorkspace
from sync_support import MemorySecrets, ObjectStore


def exchange(directory, payload):
    fixture = json.loads((ROOT / 'frontend/tests/sync/fixtures/protocol.json').read_text(encoding='utf-8'))['crypto']
    remote, secrets = ObjectStore(), MemorySecrets()
    remote.account = fixture['subject']
    remote.files = {item['id']: (item['name'].removeprefix('tracker-sync-v1-'), base64.b64decode(item['bytes'])) for item in payload['files']}
    remote.feed = list(remote.files)
    engine = create_database(Path(directory)); migrate_database(engine)
    try:
        with Session(engine) as session:
            workspace = session.get(SyncWorkspace, 1)
            if workspace:
                secrets.put(workspace.secret_reference, {'key': fixture['key']})
        peer = SyncEngine(engine, remote, secrets)
        for method_name in ('_receive', '_prepare', '_checkpoint'):
            original = getattr(peer, method_name)
            def diagnostic(*args, _original=original, **kwargs):
                try:
                    return _original(*args, **kwargs)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    raise
            setattr(peer, method_name, diagnostic)
        if not workspace:
            peer.initialize('Synthetic SQLite desktop', fixture['recovery'])
        status = peer.run(manual=True)
        if status['error']:
            raise RuntimeError(status['error'])
        root_id = fixture['batch']['mutations'][0]['entity_id']
        with Session(engine) as session:
            item = session.get(Application, root_id)
            if payload.get('edit'):
                for field, value in payload['edit'].items():
                    if field not in {'company', 'job_title', 'description'}:
                        raise ValueError('Unexpected synthetic edit field')
                    setattr(item, field, value)
                session.commit()
        status = peer.run(manual=True)
        if status['error']:
            raise RuntimeError(status['error'])
        with Session(engine) as session:
            item = session.get(Application, root_id)
            application = {'company': item.company, 'job_title': item.job_title, 'description': item.description}
        return dict(application=application, status=status, files=[dict(id=file_id, name='tracker-sync-v1-' + name,
            bytes=base64.b64encode(content).decode()) for file_id, (name, content) in remote.files.items()])
    finally:
        engine.dispose()


if __name__ == '__main__':
    result = exchange(sys.argv[1], json.load(sys.stdin))
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
