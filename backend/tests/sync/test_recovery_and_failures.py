from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backup import backup_workspace, restore_workspace
from app.database import create_database, migrate_database
from app.google_connection import GoogleConnectionError
from app.models import Application, FollowUp
from app.sync.engine import SyncEngine
from app.sync.models import SyncWorkspace, SyncRecord, SyncMutation
from app.sync.schemas import Mutation, Batch
from app.sync.crypto import decode_key, open_envelope, pairing_export, seal
from app.sync.worker import SyncWorker
from sync_support import paired, converge, update, state, create_application


@pytest.mark.parametrize('kind', ['rate_limit', 'storage_full', 'unavailable', 'authorization'])
def test_provider_failures_preserve_edits_and_schedule_backoff(replicas, kind):
    left, right, entity_id, remote = paired(replicas)
    update(left, entity_id, company='Durable while offline')
    remote.failure = GoogleConnectionError('Provider temporarily unavailable', kind=kind, retry_after=30)
    result = left.run(manual=True)
    assert result['pending_uploads'] == 1 and result['retry_at'] and result['error']
    update(left, entity_id, job_title='Another offline edit')
    assert state(left, entity_id)['job_title'] == 'Another offline edit'
    remote.failure = None
    converge(left, right)
    assert state(left, entity_id) == state(right, entity_id)


def test_expired_cursor_requires_safe_rediscovery_and_never_turns_missing_files_into_deletes(replicas, monkeypatch):
    left, right, entity_id, remote = paired(replicas)
    original = remote.changes
    monkeypatch.setattr(remote, 'changes', lambda cursor: (_ for _ in ()).throw(GoogleConnectionError('Expired cursor', kind='invalid_cursor')))
    assert 'expired' in left.run(manual=True)['error']
    with Session(left.engine) as session:
        assert session.get(SyncWorkspace, 1).cursor is None
    monkeypatch.setattr(remote, 'changes', original)
    converge(left, right)
    monkeypatch.setattr(remote, 'changes', lambda cursor: ([], ['removed-object'], 'new-cursor', False))
    assert 'removed' in left.run(manual=True)['error']
    assert not state(left, entity_id)['deleted']


def test_corrupt_batch_does_not_advance_cursor_or_apply_its_mutations(replicas):
    left, right, entity_id, remote = paired(replicas)
    with Session(right.engine) as session:
        cursor = session.get(SyncWorkspace, 1).cursor
    remote.upload_immutable(str(uuid4()), b'{"header":{"workspace_id":"' + right.status()['workspace_id'].encode() + b'"},"ciphertext":"corrupt"}')
    assert right.run(manual=True)['error']
    with Session(right.engine) as session:
        assert session.get(SyncWorkspace, 1).cursor == cursor
        assert session.get(Application, entity_id).company == 'Company'


def test_backup_restore_rotates_device_identity_preserves_pending_edits_and_requires_recovery(replicas, tmp_path):
    left, right, entity_id, remote = paired(replicas)
    export = next(value['key'] for value in left.secrets.values.values())
    recovery = pairing_export(left.status()['workspace_id'], decode_key(export), remote.identity())
    original_device = left.status()['device_id']
    update(left, entity_id, company='Unsynced backup edit')
    source = tmp_path / 'desktop'
    backup_workspace(source, tmp_path / 'portable')
    restore_workspace(tmp_path / 'portable', tmp_path / 'restored')
    engine = create_database(tmp_path / 'restored')
    migrate_database(engine)
    try:
        restored = SyncEngine(engine, remote, type(left.secrets)())
        assert restored.status()['recovery_required'] and restored.status()['device_id'] != original_device
        assert restored.run(manual=True)['error']
        update(restored, entity_id, job_title='Offline after restore')
        restored.initialize('Restored', recovery)
        converge(restored, right)
        assert state(right, entity_id)['company'] == 'Unsynced backup edit'
        assert state(right, entity_id)['job_title'] == 'Offline after restore'
    finally:
        engine.dispose()


def test_background_debounce_and_backoff_do_not_block_local_edits(replicas):
    left, _, entity_id, _ = paired(replicas)
    now = [0.0]
    worker = SyncWorker(left, clock=lambda: now[0])
    worker.last_poll = 0
    update(left, entity_id, company='Debounced')
    assert not worker.due()
    now[0] = 3.1
    assert worker.due()
    with Session(left.engine) as session:
        session.get(SyncWorkspace, 1).retry_at = datetime(2099, 1, 1)
        session.commit()
    assert not worker.due()


def test_background_worker_recovers_after_a_failed_check_without_logging_secrets(monkeypatch, caplog):
    import asyncio
    from types import SimpleNamespace

    checks, completed = [], []
    sync = SimpleNamespace(run=lambda: completed.append(True))
    worker = SyncWorker(sync)

    def due():
        checks.append(True)
        if len(checks) == 1:
            raise RuntimeError('credential-secret-must-not-appear')
        return True

    monkeypatch.setattr(worker, 'due', due)
    # Stop only after the second check has successfully reached the sync engine.
    original_run = sync.run
    monkeypatch.setattr(sync, 'run', lambda: (original_run(), worker.stop.set()))
    asyncio.run(asyncio.wait_for(worker.run(), timeout=5))
    assert len(checks) == 2 and completed == [True]
    assert 'will be retried' in caplog.text
    assert 'credential-secret' not in caplog.text


def test_same_sequence_children_are_preserved_in_a_durable_conflict(replicas):
    left, right, entity_id, _ = paired(replicas)
    for replica in (left, right):
        with Session(replica.engine) as session:
            session.add(FollowUp(application_id=entity_id, sequence_number=1, due_at=datetime(2026, 11, 1), status='PREPARED'))
            session.commit()
    converge(left, right)
    assert any(item['reason'] == 'followup_sequence_collision' for item in left.conflicts())
    assert any(item['reason'] == 'followup_sequence_collision' for item in right.conflicts())
