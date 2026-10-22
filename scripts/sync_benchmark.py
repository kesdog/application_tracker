"""Reproducible synthetic Compact Sync sizing, never reads a real workspace.

Run: .venv/Scripts/python.exe scripts/sync_benchmark.py --sizes 100 1000 10000
Results describe protocol projections and SQLite, not browser IndexedDB or live
Google latency. No provider requests, keys, tokens or private text are logged.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.sync.crypto import seal
from app.sync.crypto import open_envelope
from app.sync.checkpoints import checkpoint_batches
from app.sync.schemas import Batch
from app.database import create_database, migrate_database


def identifier(value):
    return str(uuid5(NAMESPACE_URL, 'tracker-synthetic-benchmark/' + value))


def benchmark(size):
    tracemalloc.start()
    start = time.perf_counter()
    workspace, device = identifier('workspace'), identifier('device')
    sequence = 0
    def event(entity, entity_id, changes, parent=None):
        nonlocal sequence
        sequence += 1
        value = {'version': 1, 'event_id': identifier(f'event/{sequence}'), 'workspace_id': workspace,
            'device_id': device, 'device_seq': sequence, 'entity': entity, 'entity_id': entity_id,
            'op': 'patch' if parent else 'create', 'parents': [parent] if parent else [], 'changes': changes, 'actor': 'HUMAN'}
        connection.execute('INSERT INTO sync_mutations(event_id,workspace_id,device_id,device_seq,entity,entity_id,payload,applied) VALUES(?,?,?,?,?,?,?,1)',
            (value['event_id'], workspace, device, sequence, entity, entity_id, json.dumps(value)))
        return value['event_id']
    run_root = Path(__file__).resolve().parents[1] / '.run'
    run_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tracker-synthetic-', dir=run_root) as directory:
        engine = create_database(Path(directory))
        migrate_database(engine)
        engine.dispose()
        connection = sqlite3.connect(Path(directory) / 'tracker.sqlite3')
        for index in range(size):
            application_id = identifier(f'application/{index}')
            compact = dict(company=f'Synthetic company {index}', job_title=f'Engineer {index % 12}', date_applied='2026-10-20',
                status='SUBMITTED', outcome=None, job_url=f'https://example.invalid/jobs/{index}', email_reference=None, deleted=False)
            connection.execute('INSERT INTO applications(id,company,job_title,date_applied,job_url,description,requirements) VALUES(?,?,?,?,?,?,?)',
                (application_id, compact['company'], compact['job_title'], compact['date_applied'], compact['job_url'],
                 'Excluded synthetic description. ' * 400, 'Excluded synthetic requirements. ' * 200))
            parent = event('application', application_id, compact)
            for edit in range(5 + index % 11):
                parent = event('application', application_id, {'job_title': f'Engineer revision {edit}'}, parent)
            for interview in range(index % 3):
                event('interview', identifier(f'interview/{index}/{interview}'), dict(application_id=application_id,
                    scheduled_at='2026-11-01T12:00:00Z', type='HR', duration=45, deleted=False))
            for followup in range(index % 4):
                event('followup', identifier(f'followup/{index}/{followup}'), dict(application_id=application_id,
                    sequence_number=followup + 1, due_at='2026-11-02T10:00:00Z', status='PREPARED', sent_at=None,
                    archived_at=None, snoozed_until=None, is_automatic=True, parent_followup_id=None, deleted=False))
        connection.commit()
        local_bytes = connection.execute('PRAGMA page_count').fetchone()[0] * connection.execute('PRAGMA page_size').fetchone()[0]
        checkpoint_bytes, checkpoint_objects, checkpoint_seconds, decode_seconds = 0, 0, 0.0, 0.0
        payloads = (json.loads(row[0]) for row in connection.execute('SELECT payload FROM sync_mutations ORDER BY device_id,device_seq'))
        for batch in checkpoint_batches(workspace, device, payloads, {}):
            checkpoint_start = time.perf_counter()
            encrypted = seal(batch, bytes(range(32)))
            checkpoint_seconds += time.perf_counter() - checkpoint_start
            checkpoint_bytes += len(encrypted)
            checkpoint_objects += 1
            decode_start = time.perf_counter()
            assert len(open_envelope(encrypted, bytes(range(32)), workspace).mutations) == len(batch.mutations)
            decode_seconds += time.perf_counter() - decode_start
        journal_bytes, objects = 0, 0
        cursor = connection.execute('SELECT payload FROM sync_mutations ORDER BY device_seq')
        while rows := cursor.fetchmany(100):
            chunk = Batch(workspace_id=workspace, device_id=device, batch_id=identifier(f'batch/{size}/{objects}'),
                mutations=[json.loads(row[0]) for row in rows])
            journal_bytes += len(seal(chunk, bytes(range(32))))
            objects += 1
        incremental = Batch(workspace_id=workspace, device_id=device, batch_id=identifier(f'incremental/{size}'),
            mutations=[json.loads(row[0]) for row in connection.execute('SELECT payload FROM sync_mutations ORDER BY device_seq DESC LIMIT 10')])
        connection.close()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {'applications': size, 'mutations': sequence, 'local_sqlite_bytes': local_bytes,
        'encrypted_checkpoint_bytes': checkpoint_bytes, 'checkpoint_objects': checkpoint_objects, 'encrypted_journal_bytes': journal_bytes,
        'drive_objects_with_checkpoint': objects + checkpoint_objects,
        # Discovery currently reads journals as well as checkpoint parts because
        # safe history pruning/manifest-based bootstrap is not implemented.
        'initial_download_payload_bytes': checkpoint_bytes + journal_bytes,
        'checkpoint_only_payload_bytes': checkpoint_bytes,
        'incremental_10_event_payload_bytes': len(seal(incremental, bytes(range(32)))),
        'checkpoint_encoding_seconds': round(checkpoint_seconds, 3), 'elapsed_seconds': round(time.perf_counter() - start, 3),
        'checkpoint_decoding_seconds': round(decode_seconds, 3),
        'peak_python_bytes': peak, 'live_requests_measured': False, 'indexeddb_measured': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[100, 1000, 10000])
    parser.add_argument('--output', type=Path, default=Path('.run/sync-benchmark.json'))
    args = parser.parse_args()
    results = []
    for size in args.sizes:
        result = benchmark(size)
        results.append(result)
        print(json.dumps(result), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
