from datetime import datetime
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, Task, FollowUp, Interview
from app.sync.crypto import decode_key, open_envelope, pairing_export
from app.sync.engine import SyncError
from app.sync.models import SyncMutation, SyncOutbox, SyncRecord, SyncWorkspace
from sync_support import paired, converge, update, state, create_application


def test_offline_creation_disjoint_edits_and_replay_converge_without_local_text_upload(replicas):
    left, right, entity_id, store = paired(replicas)
    update(left, entity_id, company='Left', description='LOCAL PRIVATE DESCRIPTION')
    update(right, entity_id, job_title='Right')
    new_left, new_right = create_application(left, 'Offline left'), create_application(right, 'Offline right')
    converge(right, left)
    assert state(left, entity_id) == state(right, entity_id)
    assert state(left, entity_id)['company'] == 'Left' and state(left, entity_id)['job_title'] == 'Right'
    for entity in (new_left, new_right):
        assert state(left, entity) == state(right, entity)
    with Session(left.engine) as session:
        assert session.get(Application, entity_id).description == 'LOCAL PRIVATE DESCRIPTION'
        count = session.scalar(select(func.count()).select_from(SyncMutation))
        workspace = session.get(SyncWorkspace, 1)
        key = decode_key(left.secrets.get(workspace.secret_reference)['key'])
        workspace_id = workspace.workspace_id
    # Duplicate Drive filenames and independently encrypted duplicate payloads
    # must not duplicate domain records or journal events.
    _, ciphertext = next(iter(store.files.values()))
    batch = open_envelope(ciphertext, key, workspace_id)
    store.upload_immutable(str(batch.batch_id), ciphertext)
    converge(left, right)
    with Session(left.engine) as session:
        assert session.scalar(select(func.count()).select_from(SyncMutation)) == count
    for _, value in store.files.values():
        plaintext = open_envelope(value, key, workspace_id).model_dump_json()
        assert 'LOCAL PRIVATE DESCRIPTION' not in plaintext and 'description' not in plaintext


def test_same_field_conflict_resolution_propagates_and_stale_resolution_is_rejected(replicas):
    left, right, entity_id, _ = paired(replicas)
    update(left, entity_id, company='Left')
    update(right, entity_id, company='Right')
    converge(left, right)
    assert left.status()['conflicts'] == right.status()['conflicts'] == 1
    conflict = left.conflicts()[0]
    chosen = dict(state(left, entity_id), company='Reviewed')
    with pytest.raises(SyncError, match='changed'):
        left.resolve(conflict['id'], chosen, [str(uuid4())])
    left.resolve(conflict['id'], chosen, conflict['heads'])
    converge(left, right)
    assert left.status()['conflicts'] == right.status()['conflicts'] == 0
    assert state(left, entity_id) == state(right, entity_id) == chosen
    with Session(left.engine) as session:
        events = list(session.scalars(select(SyncMutation)))
        resolution = next(item for item in events if item.payload['op'] == 'resolution')
        assert len(resolution.payload['parents']) == 2


def test_unrelated_edit_does_not_discard_unresolved_conflict(replicas):
    left, right, entity_id, _ = paired(replicas)
    update(left, entity_id, company='Left')
    update(right, entity_id, company='Right')
    converge(left, right)
    update(left, entity_id, job_title='Further edit')
    converge(left, right)
    assert left.status()['conflicts'] and right.status()['conflicts']
    assert any(item['reason'] == 'competing_values' for item in left.conflicts())


@pytest.mark.parametrize('kind', ['delete_edit', 'lifecycle'])
def test_protected_transitions_never_silently_win(replicas, kind):
    left, right, entity_id, _ = paired(replicas)
    if kind == 'delete_edit':
        update(left, entity_id, deleted_at=datetime(2026, 10, 20))
        update(right, entity_id, company='Edited while offline')
    else:
        update(left, entity_id, status='CLOSED', outcome='UNSUCCESSFUL')
        update(right, entity_id, status='INTERVIEW')
    converge(left, right)
    assert left.status()['conflicts'] and right.status()['conflicts']


def test_edit_and_outbox_rollback_atomically(replicas):
    left, _, entity_id, _ = paired(replicas)
    with Session(left.engine) as session:
        before = session.scalar(select(func.count()).select_from(SyncOutbox))
        session.get(Application, entity_id).company = 'Rolled back'
        session.flush()
        session.rollback()
    with Session(left.engine) as session:
        assert session.get(Application, entity_id).company != 'Rolled back'
        assert session.scalar(select(func.count()).select_from(SyncOutbox)) == before


def test_uncertain_upload_recovers_from_durable_batch_without_duplicate_edit(replicas):
    left, right, entity_id, store = paired(replicas)
    update(left, entity_id, company='Saved offline')
    store.lose_upload_response = True
    result = left.run(manual=True)
    assert result['error'] and result['pending_uploads'] == 1
    converge(left, right)
    assert left.status()['pending_uploads'] == 0
    assert state(right, entity_id)['company'] == 'Saved offline'


def test_wrong_key_and_account_do_not_overwrite_local_data(replicas):
    left, right, entity_id, store = paired(replicas)
    with Session(left.engine) as session:
        workspace = session.get(SyncWorkspace, 1)
        recovery = pairing_export(workspace.workspace_id, decode_key(left.secrets.get(workspace.secret_reference)['key']), workspace.subject)
    store.account = 'another-account'
    update(left, entity_id, company='Preserved')
    assert 'account' in left.run(manual=True)['error']
    assert state(left, entity_id)['company'] == 'Preserved'
    factory, _ = replicas
    wrong_account = factory('wrong-account')
    with pytest.raises(SyncError, match='account'):
        wrong_account.initialize('Wrong account', recovery)
    assert not wrong_account.status()['initialized']
    store.account = 'verified-google-sub'
    third = factory('third')
    with pytest.raises(ValueError):
        third.initialize('Third', f'ats1.{left.status()["workspace_id"]}.{"A" * 43}')
    assert not third.status()['initialized']


def test_children_import_without_messages_notes_or_automatic_generation(replicas):
    left, right, entity_id, _ = paired(replicas)
    with Session(left.engine) as session:
        session.add(Task(application_id=entity_id, title='Call', status='COMPLETED', completed_at=datetime(2026, 10, 20)))
        session.add(Interview(application_id=entity_id, scheduled_at=datetime(2026, 11, 1, 12), type='HR', notes='private notes', result='private result'))
        followup = FollowUp(application_id=entity_id, sequence_number=1, due_at=datetime(2026, 10, 25), status='READY',
                            subject='private subject', body='private body', approved_revision=1)
        session.add(followup)
        session.commit()
        followup_id = followup.id
    converge(left, right)
    from app.config import Settings
    from app.work import ensure_initial_followups
    with Session(right.engine) as session:
        ensure_initial_followups(session, Settings(_env_file=None))
        assert session.scalar(select(func.count()).select_from(FollowUp)) == 1
        imported = session.get(FollowUp, followup_id)
        assert imported.body == imported.subject == '' and imported.approved_revision is None
        assert session.scalar(select(Interview)).notes is None
        assert session.scalar(select(Task)).completed_at is not None
        assert session.get(SyncRecord, 'followup:' + followup_id).imported
