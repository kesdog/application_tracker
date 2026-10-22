from datetime import date

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models import Application
from app.sync.crypto import decode_key, open_envelope
from app.sync.engine import SyncEngine
from app.sync.models import SyncBatch, SyncDirty, SyncWorkspace
from sync_support import paired, converge, create_application, state, update


def test_idle_and_small_incremental_checks_do_not_scan_unrelated_history(replicas):
    left, right, entity_id, _ = paired(replicas)
    with Session(left.engine) as session:
        session.add_all([Application(company=f'Unrelated {index}', job_title='Engineer', date_applied=date(2026, 10, 20),
            job_url=f'https://example.invalid/{index}') for index in range(100)])
        session.commit()
    converge(left, right)
    statements = []
    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)
    event.listen(right.engine, 'before_cursor_execute', capture)
    try:
        assert right.run(manual=True)['error'] is None
        assert len(statements) < 50
        assert not any('sync_mutations.payload' in statement for statement in statements)
        update(left, entity_id, company='Only this record changed')
        assert left.run(manual=True)['error'] is None
        statements.clear()
        assert right.run(manual=True)['error'] is None
        assert len(statements) < 100
        assert state(right, entity_id)['company'] == 'Only this record changed'
    finally:
        event.remove(right.engine, 'before_cursor_execute', capture)


def test_staged_page_recovers_merge_work_after_an_interrupted_apply(replicas, monkeypatch):
    left, right, entity_id, remote = paired(replicas)
    update(left, entity_id, company='Recover staged work')
    left.run(manual=True)
    apply = right._apply
    def interrupted(*_args, **_kwargs):
        raise RuntimeError('Simulated interruption after durable staging')
    monkeypatch.setattr(right, '_apply', interrupted)
    assert right.run(manual=True)['error']
    with Session(right.engine) as session:
        assert session.scalar(select(func.count()).select_from(SyncDirty)) > 0
    # New engine object has no in-memory merge state, like a restarted process.
    restarted = SyncEngine(right.engine, remote, right.secrets)
    assert restarted.run(manual=True)['error'] is None
    assert state(restarted, entity_id)['company'] == 'Recover staged work'


def test_checkpoint_encoding_is_bounded_and_does_not_block_local_writes(replicas, monkeypatch):
    import app.sync.engine as engine_module
    import app.sync.checkpoints as checkpoint_module
    left, right, entity_id, remote = paired(replicas)
    for index in range(7):
        create_application(left, f'Checkpoint {index}')
    monkeypatch.setattr(checkpoint_module, 'MAX_EVENTS', 3)
    original_seal, new_record = engine_module.seal, []
    with Session(left.engine) as session:
        workspace = session.get(SyncWorkspace, 1)
        key = decode_key(left.secrets.get(workspace.secret_reference)['key'])
        workspace_id, device_id = workspace.workspace_id, workspace.device_id
        existing = set(session.scalars(select(SyncBatch.batch_id)))
    def encode_with_concurrent_edit(batch, key):
        if not new_record:
            # If encoding held BEGIN IMMEDIATE this independent transaction would
            # fail with database-locked instead of preserving offline editing.
            new_record.append(create_application(left, 'Edited during checkpoint'))
        return original_seal(batch, key)
    monkeypatch.setattr(engine_module, 'seal', encode_with_concurrent_edit)
    left._checkpoint(key, workspace_id, device_id)
    with Session(left.engine) as session:
        parts = [open_envelope(item.ciphertext, key, workspace_id) for item in session.scalars(select(SyncBatch)) if item.batch_id not in existing]
    assert len(parts) >= 3 and all(len(part.mutations) <= 3 for part in parts)
    assert all(str(mutation.entity_id) != new_record[0] for part in parts for mutation in part.mutations)
    converge(left, right)
    assert state(right, new_record[0])['company'] == 'Edited during checkpoint'


def test_existing_workspace_enrollment_never_loads_excluded_text(replicas):
    factory, _ = replicas
    replica = factory('existing')
    entity_id = create_application(replica, 'Existing local data', description='Private excluded description' * 1000)
    from app.models import FollowUp
    from datetime import datetime
    with Session(replica.engine) as session:
        session.add(FollowUp(application_id=entity_id, sequence_number=1, due_at=datetime(2026, 11, 1),
            body='Private excluded body' * 1000, subject='Private subject', status='PREPARED'))
        session.commit()
    statements = []
    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)
    event.listen(replica.engine, 'before_cursor_execute', capture)
    try:
        replica.initialize('Existing')
    finally:
        event.remove(replica.engine, 'before_cursor_execute', capture)
    reads = [statement.split('FROM')[0] for statement in statements if statement.lstrip().upper().startswith('SELECT')]
    assert not any('applications.description' in statement or 'followups.body' in statement or 'followups.subject' in statement for statement in reads)
    assert replica.run(manual=True)['error'] is None
