"""Causal multi-value registers. Neither arrival order nor device clocks pick winners."""
from dataclasses import dataclass

from app.sync.schemas import STATES


@dataclass
class MergeResult:
    state: dict
    heads: list[str]
    reason: str | None
    variants: list[dict]
    base: dict
    ready: set[str]


def merge_events(events: list[dict]) -> MergeResult:
    by_id = {item['event_id']: item for item in events}
    ancestors: dict[str, set[str]] = {}
    pending = set(by_id)
    while pending:
        ready = sorted(key for key in pending if set(by_id[key]['parents']) <= ancestors.keys())
        if not ready:
            break
        for key in ready:
            item = by_id[key]
            parents = set(item['parents'])
            if any(by_id[parent]['entity_id'] != item['entity_id'] or by_id[parent]['entity'] != item['entity'] for parent in parents):
                raise ValueError('Causal parents belong to another record')
            ancestors[key] = parents | set().union(*(ancestors[parent] for parent in parents))
            pending.remove(key)
    if not ancestors:
        return MergeResult({}, [], 'missing_ancestors', [], {}, set())
    consumed = set().union(*(set(by_id[key]['parents']) for key in ancestors))
    heads = sorted(set(ancestors) - consumed)
    fields = set().union(*(by_id[key]['changes'].keys() for key in ancestors))

    def registers(keys):
        result, conflicting = {}, False
        for field in sorted(fields):
            writers = [key for key in keys if field in by_id[key]['changes']]
            maximal = [key for key in writers if not any(key in ancestors[other] for other in writers)]
            if maximal:
                values = [by_id[key]['changes'][field] for key in sorted(maximal)]
                result[field] = values[0]
                conflicting |= any(value != values[0] for value in values)
        return result, conflicting

    state, conflicting = registers(ancestors.keys())
    common = ancestors[heads[0]] if len(heads) == 1 else set.intersection(*(ancestors[head] | {head} for head in heads))
    base, _ = registers(common)
    variants = [{'head': head, 'device_id': by_id[head]['device_id'], 'actor': by_id[head]['actor'],
                 'state': registers(ancestors[head] | {head})[0]} for head in heads]
    reason = 'competing_values' if conflicting else None
    if len(heads) > 1:
        # Protected transitions need explicit review even when concurrent edits
        # happen to touch different columns (e.g. close vs outcome, delete vs edit).
        protected = {'deleted'}
        entity = by_id[heads[0]]['entity']
        if entity == 'application':
            protected |= {'status', 'outcome'}
        elif entity == 'followup':
            protected |= {'status', 'sent_at', 'archived_at'}
        elif entity == 'interview':
            protected |= {'scheduled_at', 'type'}
        divergent = set().union(*(ancestors[head] | {head} for head in heads)) - common
        transition = any(set(by_id[key]['changes']) & protected for key in divergent)
        if transition and any(item['state'] != variants[0]['state'] for item in variants):
            reason = reason or 'concurrent_transition'
    if not reason:
        try:
            state = STATES[by_id[heads[0]]['entity']].model_validate(state).model_dump(mode='json')
        except ValueError:
            reason = 'invalid_domain_state'
    if pending:
        reason = reason or 'missing_ancestors'
    return MergeResult(state, heads, reason, variants, base, set(ancestors))
