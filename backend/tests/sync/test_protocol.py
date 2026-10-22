import itertools
import json
from uuid import uuid4

import pytest

from app.sync.crypto import canonical, open_envelope, seal
from app.sync.merge import merge_events
from app.sync.schemas import Batch, Mutation


def history():
    workspace, device, entity_id = (str(uuid4()) for _ in range(3))
    def event(sequence, changes, parents=(), op='patch', origin=device):
        return Mutation(event_id=uuid4(), workspace_id=workspace, device_id=origin, device_seq=sequence,
            entity='application', entity_id=entity_id, op=op, parents=list(parents), changes=changes).model_dump(mode='json')
    root = event(1, dict(company='Original', job_title='Engineer', date_applied='2026-10-20',
        job_url='https://example.com/job', email_reference=None, status='SUBMITTED', outcome=None, deleted=False), op='create')
    left = event(2, {'company': 'Left'}, [root['event_id']])
    right = event(1, {'job_title': 'Right'}, [root['event_id']], origin=str(uuid4()))
    third = event(1, {'date_applied': '2026-10-19'}, [root['event_id']], origin=str(uuid4()))
    return event, [root, left, right, third]


def test_three_branches_converge_for_every_delivery_order():
    _, events = history()
    expected = merge_events(events)
    assert expected.reason is None
    assert expected.state['company'] == 'Left' and expected.state['job_title'] == 'Right'
    for order in itertools.permutations(events):
        result = merge_events(list(order))
        assert (result.state, result.heads, result.reason) == (expected.state, expected.heads, expected.reason)


def test_missing_parents_remain_pending_and_simultaneous_resolutions_preserve_both():
    event, events = history()
    root, left, right, _ = events
    assert merge_events([right]).reason == 'missing_ancestors'
    competing = event(2, {'company': 'Other'}, [root['event_id']], origin=right['device_id'])
    conflicted = merge_events([root, left, competing])
    assert conflicted.reason == 'competing_values'
    first = event(3, dict(root['changes'], company='Resolved one'), conflicted.heads, op='resolution')
    second = event(3, dict(root['changes'], company='Resolved two'), conflicted.heads, op='resolution', origin=right['device_id'])
    result = merge_events([root, left, competing, first, second])
    assert result.reason == 'competing_values' and set(result.heads) == {first['event_id'], second['event_id']}


@pytest.mark.parametrize('tamper', ['ciphertext', 'workspace', 'batch_id', 'hash', 'version', 'wrong_key', 'oversized'])
def test_envelope_authentication_and_decoding_fail_closed(tamper, monkeypatch):
    _, events = history()
    batch = Batch(workspace_id=events[0]['workspace_id'], device_id=events[0]['device_id'], batch_id=uuid4(), mutations=events[:2])
    key = bytes(range(32))
    sealed = seal(batch, key)
    assert open_envelope(sealed, key, str(batch.workspace_id)) == batch
    value = json.loads(sealed)
    if tamper == 'ciphertext':
        # Always alter the byte; a fixed 'A' left 1/64 of random ciphertexts intact.
        first = 'B' if value['ciphertext'].startswith('A') else 'A'
        value['ciphertext'] = first + value['ciphertext'][1:]
    elif tamper == 'workspace':
        value['header']['workspace_id'] = str(uuid4())
    elif tamper == 'batch_id':
        value['header']['batch_id'] = str(uuid4())
    elif tamper == 'hash':
        value['header']['sha256'] = '0' * 64
    elif tamper == 'version':
        value['header']['version'] = 2
    elif tamper == 'wrong_key':
        key = bytes(reversed(range(32)))
    else:
        monkeypatch.setattr('app.sync.crypto.MAX_PLAINTEXT', 10)
    with pytest.raises(ValueError, match='no data was applied'):
        open_envelope(canonical(value), key, str(batch.workspace_id))


@pytest.mark.parametrize('field', ['description', 'body', 'subject', 'recipient_email', 'notes', 'result',
                                   'filename', 'document_hash', 'storage_path', 'refresh_token', 'agent_token'])
def test_patches_and_checkpoints_reject_every_excluded_category(field):
    _, events = history()
    bad = dict(events[1], changes={field: 'private'})
    with pytest.raises(ValueError):
        Mutation.model_validate(bad)
    with pytest.raises(ValueError):
        Batch(workspace_id=events[0]['workspace_id'], device_id=events[0]['device_id'], batch_id=uuid4(),
              kind='checkpoint', mutations=[bad])


def test_patch_values_are_typed_and_unknown_envelope_keys_rejected():
    _, events = history()
    with pytest.raises(ValueError):
        Mutation.model_validate(dict(events[1], changes={'company': {'embedded': 'secret'}}))
    with pytest.raises(ValueError):
        Mutation.model_validate(dict(events[1], audit={'private': 'data'}))


def test_invalid_single_branch_retains_its_valid_ancestor_for_human_resolution():
    event, events = history()
    root = events[0]
    invalid = event(2, {'job_url': None}, [root['event_id']])
    result = merge_events([root, invalid])
    assert result.reason == 'invalid_domain_state'
    assert result.base['job_url'] == root['changes']['job_url']
