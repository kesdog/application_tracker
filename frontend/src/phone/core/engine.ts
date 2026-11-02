/** Local-first replica. Inject storage, transport and clock; no Vue or HTTP dependencies. */
import { canonical, mergeEvents, requireValue, validateMutation, validateState, type Batch, type Entity, type Mutation, type State } from './protocol'
import { decode64, encode64, hashJson, openEnvelope, recoveryKey, seal, unwrapKey, wrapKey } from './crypto'
import { ProviderError, type RemoteFile, type SyncTransport } from './drive'
import type { Change, RecordState, ReplicaStore, Workspace } from './storage'
interface Outbox { id: string; mutation: Mutation; batchId: string | null }
interface Upload { id: string; payload: Batch; bytes: string; events: string[] }
export class PhoneSyncEngine {
  private key?: CryptoKey
  private queue: Promise<unknown> = Promise.resolve()
  private running = false
  private generation = 0
  constructor(readonly store: ReplicaStore, private readonly transport: SyncTransport, private readonly clock = Date.now,
    private readonly pairingPolling: { sleep?: (ms: number) => Promise<void>; retryDelays?: readonly number[] } = {}) {}
  get unlocked() { return Boolean(this.key) }
  get syncing() { return this.running }
  private serial<T>(operation: () => Promise<T>): Promise<T> {
    const pending = this.queue.then(operation); this.queue = pending.catch(() => {}); return pending
  }
  private async metadata() { const value = await this.store.metadata(); requireValue(value && this.key, 'Unlock or pair this device first'); return value }
  lock() { this.generation++; this.key = undefined; this.store.lock() }
  async unlock(passphrase: string) {
    const generation = this.generation
    const meta = await this.store.metadata(); requireValue(meta, 'Pair this device first')
    const key = await unwrapKey(meta.vault, passphrase, meta.workspace)
    requireValue(generation === this.generation, 'Unlock was cancelled because this device was locked')
    this.key = key; this.store.setKey(key, meta.workspace)
    await this.serial(() => this.applyDirty())
  }
  async pair(recovery: string, passphrase: string, identity: { subject: string; email: string }, clientId: string) {
    return this.serial(async () => {
      const generation = this.generation
      requireValue(!await this.store.metadata(), 'This browser already has a paired workspace')
      requireValue(this.transport.identity() === identity.subject, 'Connect the pairing Google account first')
      const secret = await recoveryKey(recovery, identity.subject)
      // Authenticate a real remote checkpoint/event before committing enrollment.
      let found = false
      // Newly uploaded Drive objects can take seconds to become visible to the
      // independent OAuth client. Retry reads only; enrollment commits once.
      for (const delay of [0, ...(this.pairingPolling.retryDelays ?? [250, 500, 1000, 2000, 4000])]) {
        if (delay) await (this.pairingPolling.sleep ?? (ms => new Promise(resolve => setTimeout(resolve, ms))))(delay)
        requireValue(generation === this.generation && this.transport.identity() === identity.subject, 'Pairing was cancelled because this device was locked or the Google account changed')
        for (const file of await this.transport.list()) {
          const bytes = await this.transport.download(file.id)
          if (JSON.parse(new TextDecoder().decode(bytes)).header?.workspace_id !== secret.workspace) continue
          const batch = await openEnvelope(bytes, secret.key, secret.workspace)
          if (['events', 'checkpoint'].includes(batch.kind)) { found = true; break }
        }
        if (found) break
      }
      requireValue(found, 'No authenticated sync data found. Run Sync now on desktop first.')
      const vault = await wrapKey(secret.raw, passphrase, secret.workspace); secret.raw.fill(0)
      requireValue(generation === this.generation && this.transport.identity() === identity.subject, 'Pairing was cancelled because this device was locked or the Google account changed')
      const meta: Workspace = { version: 0, workspace: secret.workspace, device: crypto.randomUUID(), nextSequence: 1, subject: identity.subject, email: identity.email,
        clientId, vault, cursor: null, lastSuccess: null, retryAt: 0, failures: 0, error: null }
      this.store.setKey(secret.key, meta.workspace)
      try { await this.store.commit(undefined, meta, []); this.key = secret.key } catch (error) { this.lock(); throw error }
    })
  }
  async records() { await this.metadata(); return this.store.all<RecordState>('records') }
  async status() {
    const meta = await this.store.metadata()
    if (!meta || !this.key) return { paired: Boolean(meta), unlocked: false, syncing: this.running, pending: null, conflicts: null, error: meta?.error ?? null, lastSuccess: meta?.lastSuccess ?? null }
    return { paired: true, unlocked: true, syncing: this.running, pending: (await this.store.all<Outbox>('outbox')).length,
      conflicts: (await this.store.all<RecordState>('records', { index: 'pending', key: 1 })).length, error: meta.error, lastSuccess: meta.lastSuccess }
  }
  private recordChange(record: RecordState): Change {
    return { store: 'records', id: record.id, value: record, parent: String(record.candidate.application_id ?? record.state.application_id ?? ''), pending: record.reason ? 1 : 0 }
  }
  private async domainReason(entity: Entity, entityId: string, state: State, previous: RecordState | undefined, proposed: Map<string, RecordState>) {
    if (entity === 'application') return null
    const parentKey = 'application:' + state.application_id
    const parent = proposed.get(parentKey) ?? await this.store.read<RecordState>('records', parentKey)
    if (!parent || !Object.keys(parent.state).length) return 'missing_application'
    if (previous?.state.application_id && previous.state.application_id !== state.application_id) return 'reparenting_forbidden'
    if (parent.state.deleted && !state.deleted) return 'deleted_application'
    if (entity === 'followup' && !state.deleted) {
      const siblings = new Map((await this.store.all<RecordState>('records', { index: 'parent', key: String(state.application_id) })).map(row => [row.id, row]))
      for (const [id, row] of proposed) if (row.state.application_id === state.application_id) siblings.set(id, row)
      if ([...siblings.values()].some(row => row.entity === 'followup' && row.entityId !== entityId && !row.state.deleted && row.state.sequence_number === state.sequence_number)) return 'followup_sequence_collision'
    }
    return null
  }
  private async reconcile(touched: Set<string>, added: Mutation[] = []): Promise<Change[]> {
    const proposed = new Map<string, RecordState>(), allKeys = new Set(touched), parents = new Set<string>()
    for (const id of touched) {
      const previous = await this.store.read<RecordState>('records', id)
      if (id.startsWith('application:')) parents.add(id.slice('application:'.length))
      else if (previous?.candidate.application_id ?? previous?.state.application_id) parents.add(String(previous?.candidate.application_id ?? previous?.state.application_id))
    }
    for (const item of added) { if (item.entity === 'application') parents.add(item.entity_id); else if (item.changes.application_id) parents.add(String(item.changes.application_id)) }
    // Retry only dependent records previously blocked by missing parents/sequence slots.
    const pending = await this.store.all<RecordState>('records', { index: 'pending', key: 1 })
    for (const row of pending) if (parents.has(String(row.candidate.application_id ?? row.state.application_id))) allKeys.add(row.id)
    const keys = [...allKeys].sort((a, b) => Number(!a.startsWith('application:')) - Number(!b.startsWith('application:')) || a.localeCompare(b))
    for (let pass = 0; pass < 2; pass++) {
      for (const id of keys) {
        const history = await this.store.all<Mutation>('events', { index: 'record', key: id })
        for (const item of added) if (item.entity + ':' + item.entity_id === id) history.push(item)
        const unique = [...new Map(history.map(item => [item.event_id, item])).values()]
        const result = mergeEvents(unique), [entity, entityId] = id.split(':') as [Entity, string]
        const previous = proposed.get(id) ?? await this.store.read<RecordState>('records', id)
        const reason = result.reason ?? await this.domainReason(entity, entityId, result.state, previous, proposed)
        proposed.set(id, { id, entity, entityId, state: reason ? previous?.state ?? {} : result.state,
          appliedHeads: reason ? previous?.appliedHeads ?? [] : result.heads, heads: result.heads, reason, base: result.base, variants: result.variants, candidate: result.state })
      }
    }
    return [...proposed.values()].map(row => this.recordChange(row))
  }
  async edit(entity: Entity, entityId: string, input: State, expectedHeads: string[] | null = null, resolution = false) {
    return this.serial(async () => {
      const meta = await this.metadata(), id = entity + ':' + entityId, record = await this.store.read<RecordState>('records', id)
      const heads = record?.heads ?? []
      requireValue(canonical(heads) === canonical(expectedHeads ?? []), 'This record changed. Refresh and review before saving.')
      const state = validateState(entity, input), reason = await this.domainReason(entity, entityId, state, record, new Map())
      requireValue(!reason, reason ?? undefined)
      const changes = !record || resolution ? state : Object.fromEntries(Object.entries(state).filter(([field, value]) => record.state[field] !== value)) as State
      if (!Object.keys(changes).length) return
      requireValue(!record || resolution || record.appliedHeads.length, 'Resolve the imported conflict before editing this record')
      const mutation = validateMutation({ version: 1, event_id: crypto.randomUUID(), workspace_id: meta.workspace, device_id: meta.device, device_seq: meta.nextSequence,
        entity, entity_id: entityId, op: resolution ? 'resolution' : record ? state.deleted ? 'delete' : 'patch' : 'create',
        parents: record ? resolution ? record.heads : record.appliedHeads : [], changes: record && state.deleted && !resolution ? { deleted: true } : changes, actor: 'HUMAN' })
      const remaining = resolution ? [] : heads.filter(head => !mutation.parents.includes(head))
      const local: RecordState = { id, entity, entityId, state, appliedHeads: [mutation.event_id], heads: [...remaining, mutation.event_id].sort(), reason: record?.reason ?? null, base: record?.base ?? {}, variants: record?.variants ?? [], candidate: state }
      // Domain record, causal event, sequence and durable outbox commit together.
      await this.store.commit(meta, { ...meta, nextSequence: meta.nextSequence + 1, dirty: [...new Set([...(meta.dirty ?? []), id])] }, [
        { store: 'events', id: mutation.event_id, record: id, value: mutation }, { store: 'sequences', id: mutation.device_id + ':' + mutation.device_seq, value: mutation.event_id },
        { store: 'outbox', id: mutation.event_id, value: { id: mutation.event_id, mutation, batchId: null } }, this.recordChange(local),
      ])
      // Reconcile after local commit too, so offline resolutions unblock siblings.
      await this.applyDirty()
    })
  }
  private async applyDirty() {
    const meta = await this.metadata()
    if (!meta.dirty?.length) return
    const changes = await this.reconcile(new Set(meta.dirty))
    await this.store.commit(meta, { ...meta, dirty: [] }, changes)
  }
  private async stage(fileId: string, batch: Batch) {
    return this.serial(async () => {
      const meta = await this.metadata(); requireValue(meta.workspace === batch.workspace_id)
      if (await this.store.read('inbox', fileId)) return
      const digest = await hashJson(batch), receipt = await this.store.read<string>('receipts', batch.batch_id)
      requireValue(!receipt || receipt === digest, 'A batch ID was reused with different contents')
      const incoming: Mutation[] = [], changes: Change[] = [], sequences = new Map<string, string>(), ids = new Map<string, Mutation>()
      if (!receipt) for (const item of batch.mutations) {
        const previous = ids.get(item.event_id) ?? await this.store.read<Mutation>('events', item.event_id)
        requireValue(!previous || canonical(previous) === canonical(item), 'An event ID was reused with different contents')
        if (previous) continue
        const sequence = item.device_id + ':' + item.device_seq, used = sequences.get(sequence) ?? await this.store.read<string>('sequences', sequence)
        requireValue(!used || used === item.event_id, 'Device sequence collision. Preserve local data and re-pair a clean device.')
        ids.set(item.event_id, item); sequences.set(sequence, item.event_id); incoming.push(item)
        changes.push({ store: 'events', id: item.event_id, record: item.entity + ':' + item.entity_id, value: item }, { store: 'sequences', id: sequence, value: item.event_id })
      }
      changes.push(...await this.reconcile(new Set(incoming.map(item => item.entity + ':' + item.entity_id)), incoming))
      const local = await this.store.read<Upload>('batches', batch.batch_id)
      if (local) { requireValue(await hashJson(local.payload) === digest, 'Remote batch differs from its durable upload intent'); changes.push({ store: 'batches', id: local.id }, ...local.events.map(id => ({ store: 'outbox' as const, id }))) }
      changes.push({ store: 'inbox', id: fileId, value: true }, { store: 'receipts', id: batch.batch_id, value: digest })
      await this.store.commit(meta, meta, changes)
    })
  }
  private async receive(files: RemoteFile[]) {
    for (const file of files) {
      await this.metadata(); if (await this.store.read('inbox', file.id)) continue
      const bytes = await this.transport.download(file.id), meta = await this.metadata()
      if (JSON.parse(new TextDecoder().decode(bytes)).header?.workspace_id !== meta.workspace) continue
      await this.stage(file.id, await openEnvelope(bytes, this.key!, meta.workspace))
    }
  }
  private async updateMeta(change: Partial<Workspace>) { return this.serial(async () => { const meta = await this.metadata(); await this.store.commit(meta, { ...meta, ...change }, []) }) }
  private async prepare() {
    return this.serial(async () => {
      const meta = await this.metadata(), pending = (await this.store.all<Outbox>('outbox')).filter(item => !item.batchId)
      for (let offset = 0; offset < pending.length;) {
        const events: Outbox[] = []; let bytes = 0
        while (offset < pending.length && events.length < 100) {
          const item = pending[offset]!, size = new TextEncoder().encode(canonical(item.mutation)).length
          if (events.length && bytes + size > 65536) break
          events.push(item); bytes += size; offset++
        }
        const current = await this.metadata(), id = crypto.randomUUID(), payload: Batch = { version: 1, workspace_id: meta.workspace, device_id: meta.device, batch_id: id, kind: 'events', mutations: events.map(item => item.mutation), acknowledgments: {} }
        const upload: Upload = { id, payload, bytes: encode64(await seal(payload, this.key!)), events: events.map(item => item.id) }
        await this.store.commit(current, current, [{ store: 'batches', id, value: upload }, ...events.map(item => ({ store: 'outbox' as const, id: item.id, value: { ...item, batchId: id } }))])
      }
    })
  }
  async sync(manual = false): Promise<void> {
    if (this.running) return
    this.running = true
    try {
      const meta = await this.metadata(); if (!manual && meta.retryAt > this.clock()) return
      await this.serial(() => this.applyDirty())
      requireValue(this.transport.identity() === meta.subject, 'The connected Google account does not match this workspace')
      let cursor = meta.cursor
      if (cursor === null) { cursor = await this.transport.startCursor(); await this.receive(await this.transport.list()); await this.updateMeta({ cursor }) }
      const seen = new Set<string>()
      while (true) {
        const page = await this.transport.changes(cursor)
        for (const id of page.removed) requireValue(!await this.store.read('inbox', id), 'Remote sync files were removed. Preserve local data and review recovery.')
        requireValue(!page.more || (!seen.has(page.cursor) && page.cursor !== cursor), 'Drive returned a repeated change page')
        await this.receive(page.files); await this.updateMeta({ cursor: page.cursor }); cursor = page.cursor; seen.add(cursor)
        if (!page.more) break
      }
      await this.prepare()
      for (const upload of await this.store.all<Upload>('batches')) {
        await this.metadata(); await this.transport.upload(upload.id, decode64(upload.bytes))
        await this.serial(async () => { const current = await this.metadata(); await this.store.commit(current, current, [{ store: 'batches', id: upload.id }, ...upload.events.map(id => ({ store: 'outbox' as const, id }))]) })
      }
      await this.updateMeta({ lastSuccess: new Date(this.clock()).toISOString(), error: null, failures: 0, retryAt: 0 })
    } catch (error) {
      if (this.key) await this.serial(async () => {
        const meta = await this.metadata(), failures = meta.failures + 1
        const message = error instanceof ProviderError ? error.message : error instanceof Error && /^(Remote sync files|The connected Google account|Drive returned|A batch ID|An event ID|Device sequence|Sync file failed|Reconnect Google)/.test(error.message) ? error.message : 'Sync could not complete. Local data and pending edits are preserved.'
        await this.store.commit(meta, { ...meta, failures, error: message, cursor: error instanceof ProviderError && error.kind === 'invalid_cursor' ? null : meta.cursor,
          retryAt: this.clock() + Math.max(Math.min(2 ** Math.min(failures, 10), 900), error instanceof ProviderError ? error.retryAfter : 0) * 1000 + Math.floor(Math.random() * 3000) }, [])
      }).catch(() => {})
      throw error
    } finally { this.running = false }
  }
}
