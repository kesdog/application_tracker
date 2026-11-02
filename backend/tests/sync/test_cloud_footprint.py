from app.sync.crypto import decode_key, open_envelope
from app.sync.models import SyncWorkspace
from sqlalchemy.orm import Session
from sync_support import create_application, update, converge, state


def test_empty_workspace_has_one_bootstrap_and_idle_pairing_uploads_nothing(replicas):
    factory, remote = replicas
    desktop, phone = factory('empty-desktop'), factory('empty-phone')
    recovery = desktop.initialize('Desktop')['recovery_export']
    assert desktop.run()['error'] is None
    assert len(remote.files) == 1
    initial = dict(remote.files)
    phone.initialize('Phone', recovery)
    converge(desktop, phone)
    converge(phone, desktop)
    assert remote.files == initial


def test_one_action_prepares_new_or_existing_workspace_without_duplicate_cloud_data(replicas):
    factory, remote = replicas
    desktop, phone = factory('one-action-desktop'), factory('one-action-phone')
    prepared = desktop.prepare_phone()
    assert prepared['status']['last_success']
    assert not prepared['status']['running']
    assert len(remote.files) == 1
    assert 'recovery_export' not in desktop.status()
    assert desktop.prepare_phone()['recovery_export'] == prepared['recovery_export']
    assert len(remote.files) == 1
    phone.initialize('Phone', prepared['recovery_export'])
    entity = create_application(phone, company='Phone paired in one flow')
    converge(phone, desktop)
    assert state(desktop, entity)['company'] == 'Phone paired in one flow'


def test_compact_cloud_bootstraps_and_syncs_both_ways_without_duplicate_snapshots_or_receipts(replicas):
    factory, remote = replicas
    left, right = factory('cloud-desktop'), factory('cloud-phone-peer')
    export = left.initialize('Desktop')['recovery_export']
    entity = create_application(left, description='private description ' * 5000)
    assert left.run()['error'] is None
    initial_files = set(remote.files)
    initial_bytes = sum(len(value) for _, value in remote.files.values())
    right.initialize('Phone peer', export)
    converge(left, right)
    assert set(remote.files) == initial_files  # Pairing/receipts do not grow Drive.
    assert initial_bytes < 4096
    update(right, entity, company='Phone edit')
    converge(right, left)
    assert state(left, entity)['company'] == 'Phone edit'
    update(left, entity, job_title='Desktop edit')
    converge(left, right)
    assert state(right, entity)['job_title'] == 'Desktop edit'
    before_idle = set(remote.files)
    for _ in range(3):
        converge(left, right)
    assert set(remote.files) == before_idle
    with Session(left.engine) as session:
        workspace = session.get(SyncWorkspace, 1)
        key = decode_key(left.secrets.get(workspace.secret_reference)['key'])
        for _, value in remote.files.values():
            batch = open_envelope(value, key, workspace.workspace_id)
            assert batch.kind == 'events'
            assert 'private description' not in str(batch.model_dump())


def test_explicit_checkpoint_still_supports_existing_recovery_protocol(replicas):
    factory, remote = replicas
    left, right = factory('explicit-checkpoint'), factory('checkpoint-reader')
    export = left.initialize('Desktop')['recovery_export']
    entity = create_application(left)
    assert left.run(checkpoint=True)['error'] is None
    right.initialize('Reader', export)
    assert right.run()['error'] is None
    assert state(right, entity)['company'] == 'Company'
