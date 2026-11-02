from uuid import uuid4

import pytest

from app.sync.crypto import decode_key, seal, open_envelope
from app.sync.probe import LiveSyncProbe
from app.sync.schemas import Batch
from sync_support import ObjectStore


class Probes(ObjectStore):
    def remove_probe(self, file_id, workspace, key, batch_id):
        batch = open_envelope(self.download(file_id), key, workspace)
        assert batch.kind == 'ack' and not batch.mutations and str(batch.batch_id) == batch_id
        del self.files[file_id]
        self.feed.append(file_id)

    def changes(self, cursor):
        ids = self.feed[int(cursor):]
        return ([{'id': key, 'name': 'tracker-sync-v1-' + self.files[key][0]} for key in ids if key in self.files],
            [key for key in ids if key not in self.files], str(len(self.feed)), False)


def answer(remote, challenge):
    batch = Batch(workspace_id=challenge['workspace_id'], batch_id=challenge['phone_batch_id'], device_id=uuid4(), kind='ack')
    file_id = remote.upload_immutable(str(batch.batch_id), seal(batch, decode_key(challenge['test_key'])))
    return file_id, str(batch.batch_id)


def test_cross_client_probe_requires_independent_clients_and_observes_both_directions():
    remote = Probes()
    probe = LiveSyncProbe(remote, lambda: 'desktop.apps.googleusercontent.com')
    with pytest.raises(ValueError, match='separate'):
        probe.begin('desktop.apps.googleusercontent.com')
    challenge = probe.begin('phone.apps.googleusercontent.com')
    file_id, batch_id = answer(remote, challenge)
    assert probe.verify(challenge['probe_id'], file_id, batch_id)['verified']
    assert probe.cleanup(challenge['probe_id']) == {'cleaned': True}
    assert not remote.files


def test_probe_cleanup_reconciles_an_upload_whose_response_was_lost_and_never_deletes_unrelated_data():
    remote = Probes()
    unrelated = remote.upload_immutable(str(uuid4()), b'unrelated encrypted workspace data')
    probe = LiveSyncProbe(remote, lambda: 'desktop.apps.googleusercontent.com')
    challenge = probe.begin('phone.apps.googleusercontent.com')
    answer(remote, challenge)  # Browser never reached the verification call.
    probe.cleanup(challenge['probe_id'])
    assert set(remote.files) == {unrelated}


def test_expired_or_changed_account_probe_does_not_accept_the_phone_response():
    remote, now = Probes(), [0]
    probe = LiveSyncProbe(remote, lambda: 'desktop.apps.googleusercontent.com', clock=lambda: now[0])
    challenge = probe.begin('phone.apps.googleusercontent.com')
    file_id, batch_id = answer(remote, challenge)
    remote.account = 'another-account'
    with pytest.raises(ValueError, match='changed'):
        probe.verify(challenge['probe_id'], file_id, batch_id)
    with pytest.raises(ValueError, match='original Google account'):
        probe.cleanup(challenge['probe_id'])
    remote.account = 'verified-google-sub'; now[0] = 601
    with pytest.raises(ValueError, match='expired'):
        probe.verify(challenge['probe_id'], file_id, batch_id)
    probe.cleanup(challenge['probe_id'])


def test_probe_requires_change_feed_visibility_even_if_listing_succeeds(monkeypatch):
    remote = Probes()
    waits = []
    probe = LiveSyncProbe(remote, lambda: 'desktop.apps.googleusercontent.com', wait=waits.append, retry_delays=(0, 0))
    challenge = probe.begin('phone.apps.googleusercontent.com')
    file_id, batch_id = answer(remote, challenge)
    monkeypatch.setattr(remote, 'changes', lambda cursor: ([], [], cursor, False))
    with pytest.raises(ValueError, match='change feed'):
        probe.verify(challenge['probe_id'], file_id, batch_id)
    assert waits == [0, 0]
    probe.cleanup(challenge['probe_id'])


@pytest.mark.parametrize('delayed', ['list', 'feed', 'both'])
def test_probe_waits_for_provider_visibility_without_replaying_uploads(monkeypatch, delayed):
    remote, waits = Probes(), []
    probe = LiveSyncProbe(remote, lambda: 'desktop.apps.googleusercontent.com', wait=waits.append, retry_delays=(0, 0))
    challenge = probe.begin('phone.apps.googleusercontent.com')
    file_id, batch_id = answer(remote, challenge)
    original_files = set(remote.files)
    listed, changed = remote.list_files, remote.changes
    list_calls, feed_cursors = [], []
    def lagged_list():
        list_calls.append(True)
        return [] if len(list_calls) == 1 else listed()
    def lagged_feed(cursor):
        feed_cursors.append(cursor)
        return ([], [], 'empty-new-cursor', False) if len(feed_cursors) == 1 else changed(cursor)
    if delayed in {'list', 'both'}:
        monkeypatch.setattr(remote, 'list_files', lagged_list)
    if delayed in {'feed', 'both'}:
        monkeypatch.setattr(remote, 'changes', lagged_feed)
    assert probe.verify(challenge['probe_id'], file_id, batch_id)['verified']
    assert len(waits) == (2 if delayed == 'both' else 1)
    assert len(set(feed_cursors)) <= 1
    assert set(remote.files) == original_files
    probe.cleanup(challenge['probe_id'])
    assert not remote.files
