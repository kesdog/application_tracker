"""Write synthetic Python/browser protocol fixtures; never reads a workspace."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.sync.crypto import canonical, encode_key, seal, pairing_export
from app.sync.merge import merge_events
from app.sync.schemas import Batch, Mutation


def identifier(name):
    return str(uuid5(NAMESPACE_URL, 'phone-protocol-fixture/' + name))


def vectors():
    workspace, device, entity_id = (identifier(name) for name in ['workspace', 'desktop', 'application'])
    sequence = 0
    def event(name, changes, *, parents=(), entity='application', record=entity_id, op=None, origin=device):
        nonlocal sequence
        sequence += 1
        return Mutation(event_id=identifier(name), workspace_id=workspace, device_id=origin, device_seq=sequence,
            entity=entity, entity_id=record, parents=list(parents), op=op or ('patch' if parents else 'create'),
            changes=changes, actor='HUMAN').model_dump(mode='json')
    root = event('root', dict(company='Équipe 東京 😀', job_title='Engineer', date_applied='2026-10-28',
        job_url='https://example.invalid/phone', email_reference=None, status='SUBMITTED', outcome=None, deleted=False))
    phone = identifier('phone')
    a = event('a', {'company': 'Desktop employer'}, parents=[root['event_id']])
    b = event('b', {'job_title': 'Phone title'}, parents=[root['event_id']], origin=phone)
    c = event('c', {'company': 'Competing employer'}, parents=[root['event_id']], origin=phone)
    close = event('close', {'status': 'CLOSED', 'outcome': 'WITHDRAWN'}, parents=[root['event_id']])
    delete = event('delete', {'deleted': True}, parents=[root['event_id']], op='delete')
    resolution = event('resolution', dict(root['changes'], company='Reviewed employer'), parents=[a['event_id'], c['event_id']], op='resolution')
    histories = {'root': [root], 'disjoint': [root, a, b], 'competing': [root, a, c], 'close_edit': [root, close, b],
        'delete_edit': [root, delete, b], 'missing': [a], 'resolved': [root, a, c, resolution]}
    events = [root]
    for entity, state in [
        ('task', dict(application_id=entity_id, title='Call employer', status='COMPLETED', due_at=None, completed_at='2026-10-28T12:00:00Z', deleted=False)),
        ('interview', dict(application_id=entity_id, scheduled_at='2026-11-04T10:00:00Z', type='HR', duration=45, deleted=False)),
        ('followup', dict(application_id=entity_id, sequence_number=1, due_at='2026-11-01T09:00:00Z', status='PREPARED', sent_at=None,
            archived_at=None, snoozed_until=None, is_automatic=True, parent_followup_id=None, deleted=False)),
    ]:
        item = event(entity, state, entity=entity, record=identifier(entity)); events.append(item); histories[entity] = [item]
    cases = []
    for name, history in histories.items():
        result = asdict(merge_events(history)); result['ready'] = sorted(result['ready'])
        cases.append(dict(name=name, events=history, expected=result))
    batch = Batch(workspace_id=workspace, device_id=device, batch_id=identifier('batch'), kind='checkpoint', mutations=events)
    key = bytes(range(32))
    return dict(cases=cases, crypto=dict(key=encode_key(key), workspace=workspace, subject='synthetic-verified-subject',
        recovery=pairing_export(workspace, key, 'synthetic-verified-subject'), batch=batch.model_dump(mode='json'),
        canonical=canonical(batch.model_dump(mode='json')).decode(), envelope=json.loads(seal(batch, key))))


if __name__ == '__main__':
    destination = ROOT / 'frontend/tests/sync/fixtures/protocol.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(vectors(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Synthetic protocol fixtures written; no workspace data was read.')
