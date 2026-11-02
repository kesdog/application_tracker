/** Compact Sync v1. No UI, persistence, Google or tracker API dependencies. */
export type Entity = 'application' | 'task' | 'interview' | 'followup'
export type State = Record<string, string | number | boolean | null>
export interface Mutation {
  version: 1; event_id: string; workspace_id: string; device_id: string; device_seq: number
  entity: Entity; entity_id: string; op: 'create' | 'patch' | 'delete' | 'resolution'
  parents: string[]; changes: State; actor: 'HUMAN' | 'AGENT' | 'SYSTEM'
}
export interface Batch {
  version: 1; workspace_id: string; batch_id: string; device_id: string
  kind: 'events' | 'checkpoint' | 'ack'; mutations: Mutation[]; acknowledgments: Record<string, number>
}
const fields: Record<Entity, string[]> = {
  application: ['company', 'job_title', 'date_applied', 'job_url', 'email_reference', 'status', 'outcome', 'deleted'],
  task: ['application_id', 'title', 'status', 'due_at', 'completed_at', 'deleted'],
  interview: ['application_id', 'scheduled_at', 'type', 'duration', 'deleted'],
  followup: ['application_id', 'sequence_number', 'due_at', 'status', 'sent_at', 'archived_at', 'snoozed_until', 'is_automatic', 'parent_followup_id', 'deleted'],
}
export function requireValue(condition: unknown, message = 'Invalid compact sync data'): asserts condition {
  if (!condition) throw new Error(message)
}
export function object(value: unknown): Record<string, any> {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value))
  return value as Record<string, any>
}
export function exact(value: Record<string, any>, keys: string[]) {
  requireValue(Object.keys(value).every(key => keys.includes(key)))
}
export function uuid(value: unknown): asserts value is string {
  requireValue(typeof value === 'string' && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value))
}
function integer(value: unknown, min: number) { requireValue(Number.isSafeInteger(value) && (value as number) >= min) }
function string(value: unknown, max: number, nullable = false) {
  requireValue((nullable && value === null) || (typeof value === 'string' && (nullable || value.length > 0) && value.length <= max))
}
function timestamp(value: unknown, nullable = false) {
  requireValue((nullable && value === null) || (typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(value) && Number.isFinite(Date.parse(value))))
}
function choice(value: unknown, values: unknown[]) { requireValue(values.includes(value)) }
export function validateState(entity: Entity, input: unknown, partial = false): State {
  const value = { ...object(input) }
  requireValue(entity in fields); exact(value, fields[entity])
  for (const [name, item] of Object.entries(value)) {
    if (name === 'deleted' || name === 'is_automatic') requireValue(typeof item === 'boolean')
    else if (name.endsWith('_id')) { if (name !== 'parent_followup_id' || item !== null) uuid(item) }
    else if (name === 'sequence_number' || name === 'duration') { if (item !== null || name !== 'duration') integer(item, 1) }
    else if (name === 'date_applied') {
      requireValue(typeof item === 'string' && /^\d{4}-\d\d-\d\d$/.test(item) && new Date(item).toISOString().slice(0, 10) === item)
    } else if (name.endsWith('_at') || name === 'snoozed_until') timestamp(item, !['due_at', 'scheduled_at'].includes(name) || entity === 'task')
    else if (name === 'status') choice(item, entity === 'application' ? ['SUBMITTED', 'INTERVIEW', 'CLOSED'] : entity === 'task' ? ['PENDING', 'COMPLETED', 'CANCELLED'] : ['PREPARED', 'READY', 'SENT'])
    else if (name === 'outcome') choice(item, [null, 'SUCCESSFUL', 'UNSUCCESSFUL', 'WITHDRAWN', 'JOB_CANCELLED', 'GHOSTED'])
    else if (name === 'type') choice(item, ['PHONE', 'HR', 'TECHNICAL', 'ONSITE', 'FINAL', 'OTHER'])
    else string(item, ['job_url', 'email_reference'].includes(name) ? 2048 : 300, ['job_url', 'email_reference'].includes(name))
  }
  if (partial) return value
  const defaults: Record<Entity, State> = {
    application: { job_url: null, email_reference: null, outcome: null, deleted: false },
    task: { due_at: null, completed_at: null, deleted: false },
    interview: { duration: null, deleted: false },
    followup: { sent_at: null, archived_at: null, snoozed_until: null, is_automatic: false, parent_followup_id: null, deleted: false },
  }
  const state = { ...defaults[entity], ...value }
  requireValue(fields[entity].every(name => name in state))
  if (entity === 'application') requireValue(String(state.company).trim() && String(state.job_title).trim() && (String(state.job_url ?? '').trim() || String(state.email_reference ?? '').trim()) && (!state.outcome || state.status === 'CLOSED'))
  if (entity === 'task') requireValue(String(state.title).trim() && (state.status === 'COMPLETED') === (state.completed_at !== null))
  if (entity === 'followup') requireValue((state.status === 'SENT') === (state.sent_at !== null))
  return state
}
export function validateMutation(input: unknown): Mutation {
  const value = object(input)
  exact(value, ['version', 'event_id', 'workspace_id', 'device_id', 'device_seq', 'entity', 'entity_id', 'op', 'parents', 'changes', 'actor'])
  requireValue(value.version === 1); ['event_id', 'workspace_id', 'device_id', 'entity_id'].forEach(key => uuid(value[key]))
  integer(value.device_seq, 1); requireValue(Object.hasOwn(fields, value.entity))
  choice(value.op, ['create', 'patch', 'delete', 'resolution']); choice(value.actor, ['HUMAN', 'AGENT', 'SYSTEM'])
  requireValue(Array.isArray(value.parents) && value.parents.length <= 1000 && new Set(value.parents).size === value.parents.length && !value.parents.includes(value.event_id))
  value.parents.forEach(uuid); requireValue((value.op === 'create') === (value.parents.length === 0))
  requireValue(Object.keys(object(value.changes)).length > 0)
  validateState(value.entity, value.changes, !['create', 'resolution'].includes(value.op))
  if (value.op === 'delete') requireValue(Object.keys(value.changes).length === 1 && value.changes.deleted === true)
  return structuredClone(value) as Mutation
}
export function validateBatch(input: unknown): Batch {
  const value = object(input); exact(value, ['version', 'workspace_id', 'batch_id', 'device_id', 'kind', 'mutations', 'acknowledgments'])
  requireValue(value.version === 1); ['workspace_id', 'batch_id', 'device_id'].forEach(key => uuid(value[key]))
  choice(value.kind, ['events', 'checkpoint', 'ack'])
  requireValue(Array.isArray(value.mutations) && value.mutations.length <= 1_000_000)
  const mutations = value.mutations.map(validateMutation) as Mutation[]
  requireValue(mutations.every(item => item.workspace_id === value.workspace_id && (value.kind !== 'events' || item.device_id === value.device_id)))
  requireValue(value.kind !== 'ack' || mutations.length === 0)
  for (const [device, sequence] of Object.entries(object(value.acknowledgments))) { uuid(device); integer(sequence, 0) }
  return { ...value, mutations } as Batch
}
export function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') { const result = JSON.stringify(value); requireValue(result !== undefined && !(typeof value === 'number' && !Number.isFinite(value))); return result }
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical((value as any)[key])).join(',') + '}'
}
export interface MergeResult { state: State; heads: string[]; reason: string | null; base: State; variants: { head: string; device_id: string; actor: string; state: State }[]; ready: Set<string> }
export function mergeEvents(events: Mutation[]): MergeResult {
  const byId = new Map(events.map(item => [item.event_id, item])), ancestors = new Map<string, Set<string>>()
  const pending = new Set(byId.keys())
  while (pending.size) {
    const ready = [...pending].filter(key => byId.get(key)!.parents.every(parent => ancestors.has(parent))).sort()
    if (!ready.length) break
    for (const key of ready) {
      const item = byId.get(key)!, all = new Set(item.parents)
      for (const parent of item.parents) {
        requireValue(byId.get(parent)!.entity === item.entity && byId.get(parent)!.entity_id === item.entity_id, 'Causal parents belong to another record')
        ancestors.get(parent)!.forEach(id => all.add(id))
      }
      ancestors.set(key, all); pending.delete(key)
    }
  }
  if (!ancestors.size) return { state: {}, heads: [], reason: 'missing_ancestors', base: {}, variants: [], ready: new Set() }
  const consumed = new Set([...ancestors.keys()].flatMap(key => byId.get(key)!.parents)), heads = [...ancestors.keys()].filter(key => !consumed.has(key)).sort()
  const fields = [...new Set([...ancestors.keys()].flatMap(key => Object.keys(byId.get(key)!.changes)))].sort()
  function registers(keys: Iterable<string>): [State, boolean] {
    const available = [...keys], state: State = {}; let conflict = false
    for (const field of fields) {
      const writers = available.filter(key => field in byId.get(key)!.changes)
      const maximal = writers.filter(key => !writers.some(other => ancestors.get(other)!.has(key))).sort()
      if (maximal.length) { const values = maximal.map(key => byId.get(key)!.changes[field]); state[field] = values[0]!; conflict ||= values.some(value => value !== values[0]) }
    }
    return [state, conflict]
  }
  let [state, conflicting] = registers(ancestors.keys())
  const branch = (head: string) => new Set([...ancestors.get(head)!, head])
  const common = heads.length === 1 ? ancestors.get(heads[0]!)! : new Set([...branch(heads[0]!)].filter(key => heads.every(head => branch(head).has(key))))
  const [base] = registers(common), variants = heads.map(head => ({ head, device_id: byId.get(head)!.device_id, actor: byId.get(head)!.actor, state: registers(branch(head))[0] }))
  let reason: string | null = conflicting ? 'competing_values' : null
  const entity = byId.get(heads[0]!)!.entity
  if (heads.length > 1) {
    const protectedFields = ['deleted', ...(entity === 'application' ? ['status', 'outcome'] : entity === 'followup' ? ['status', 'sent_at', 'archived_at'] : entity === 'interview' ? ['scheduled_at', 'type'] : [])]
    const divergent = new Set(heads.flatMap(head => [...branch(head)]).filter(key => !common.has(key)))
    if ([...divergent].some(key => Object.keys(byId.get(key)!.changes).some(field => protectedFields.includes(field))) && variants.some(item => canonical(item.state) !== canonical(variants[0]!.state))) reason ||= 'concurrent_transition'
  }
  if (!reason) { try { state = validateState(entity, state) } catch { reason = 'invalid_domain_state' } }
  if (pending.size) reason ||= 'missing_ancestors'
  return { state, heads, reason, base, variants, ready: new Set(ancestors.keys()) }
}
