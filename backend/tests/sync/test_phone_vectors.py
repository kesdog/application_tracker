import json
from dataclasses import asdict
from pathlib import Path

from app.sync.crypto import canonical, decode_key, open_envelope
from app.sync.merge import merge_events
from app.sync.schemas import Mutation


def test_browser_shared_vectors_still_match_the_current_python_protocol():
    source = Path(__file__).resolve().parents[3] / 'frontend/tests/sync/fixtures/protocol.json'
    fixture = json.loads(source.read_text(encoding='utf-8'))
    for case in fixture['cases']:
        events = [Mutation.model_validate(item).model_dump(mode='json') for item in case['events']]
        actual = asdict(merge_events(events)); actual['ready'] = sorted(actual['ready'])
        assert actual == case['expected'], case['name']
    sample = fixture['crypto']
    batch = open_envelope(canonical(sample['envelope']), decode_key(sample['key']), sample['workspace'])
    assert batch.model_dump(mode='json') == sample['batch']
    assert canonical(sample['batch']).decode() == sample['canonical']
