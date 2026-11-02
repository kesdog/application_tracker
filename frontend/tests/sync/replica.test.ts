import { afterEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBObjectStore } from 'fake-indexeddb'
import { PhoneSyncEngine } from '../../src/phone/core/engine'
import { IndexedReplicaStore } from '../../src/phone/core/storage'
import { keyFromBytes, openEnvelope } from '../../src/phone/core/crypto'
import type { RecordState } from '../../src/phone/core/storage'
import { bytesKey, fixture, paired, passphrase, publish, rootId, seeded } from './support'
const close: IndexedReplicaStore[] = []

it('waits for cross-client Drive visibility without replaying a write', async () => {
  const objects = await seeded(), remote = objects.remote(), original = remote.list
  let lists = 0
  remote.list = async () => ++lists < 3 ? [] : original()
  const store = new IndexedReplicaStore(crypto.randomUUID(), new IDBFactory()); close.push(store)
  const sleep = vi.fn(async (_ms: number) => {})
  const engine = new PhoneSyncEngine(store, remote, Date.now, { sleep, retryDelays: [1, 2] })
  await engine.pair(fixture.crypto.recovery, passphrase, { subject: fixture.crypto.subject, email: 'synthetic@example.invalid' }, 'phone.apps.googleusercontent.com')
  expect(sleep.mock.calls).toEqual([[1], [2]])
  expect((await engine.status()).paired).toBe(true)
  expect(objects.calls).not.toContain('upload')
})

it('cancels enrollment during visibility polling without persisting a vault', async () => {
  const objects = await seeded(), remote = objects.remote(); remote.list = async () => []
  const store = new IndexedReplicaStore(crypto.randomUUID(), new IDBFactory()); close.push(store)
  const engine: PhoneSyncEngine = new PhoneSyncEngine(store, remote, Date.now, { sleep: async (): Promise<void> => engine.lock(), retryDelays: [1] })
  await expect(engine.pair(fixture.crypto.recovery, passphrase, { subject: fixture.crypto.subject, email: 'synthetic@example.invalid' }, 'phone.apps.googleusercontent.com')).rejects.toThrow('cancelled')
  expect(await store.metadata()).toBeUndefined()
})
afterEach(() => { close.splice(0).forEach(store => store.close()); vi.restoreAllMocks() })

it('persists offline edits, encrypted records and outbox atomically across a new process-like instance', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  const root = (await replica.engine.records()).find(row => row.entityId === rootId)!
  objects.offline = true
  await replica.engine.edit('application', rootId, { ...root.state, company: 'Phone offline employer' }, root.heads)
  await expect(replica.engine.sync(true)).rejects.toThrow('unavailable')
  expect((await replica.engine.status()).pending).toBe(1)
  replica.store.close()
  const reopened = new IndexedReplicaStore(replica.name, replica.factory); close.push(reopened)
  const restarted = new PhoneSyncEngine(reopened, objects.remote())
  expect((await restarted.status()).unlocked).toBe(false)
  await expect(restarted.unlock('wrong synthetic passphrase')).rejects.toThrow('Unable to unlock')
  await restarted.unlock(passphrase)
  expect((await restarted.records()).find(row => row.entityId === rootId)!.state.company).toBe('Phone offline employer')
  expect((await restarted.status()).pending).toBe(1)
  objects.offline = false; await restarted.sync(true)
  expect((await restarted.status()).pending).toBe(0)
  const key = await keyFromBytes(bytesKey())
  const batches = await Promise.all([...objects.files.values()].map(file => openEnvelope(file.bytes, key, fixture.crypto.workspace)))
  expect(batches.flatMap(batch => batch.mutations).some(event => event.changes.company === 'Phone offline employer')).toBe(true)
  // Inspect actual IndexedDB bytes through the storage API's underlying factory.
  const raw = await new Promise<any[]>((resolve, reject) => { const request = replica.factory.open(replica.name); request.onsuccess = () => { const db = request.result, tx = db.transaction('records'), read = tx.objectStore('records').getAll(); read.onsuccess = () => { resolve(read.result); db.close() }; read.onerror = () => reject(read.error) } })
  expect(JSON.stringify(raw)).not.toContain('Phone offline employer')
  expect(JSON.stringify(await reopened.metadata())).not.toContain(passphrase)
})

it('converges disjoint edits between independent IndexedDB replicas and preserves competing edits for review', async () => {
  const objects = await seeded(), left = await paired(objects), right = await paired(objects); close.push(left.store, right.store)
  const a = (await left.engine.records()).find(row => row.entityId === rootId)!, b = (await right.engine.records()).find(row => row.entityId === rootId)!
  await left.engine.edit('application', rootId, { ...a.state, company: 'Left employer' }, a.heads)
  await right.engine.edit('application', rootId, { ...b.state, job_title: 'Right title' }, b.heads)
  for (let i = 0; i < 2; i++) { await left.engine.sync(true); await right.engine.sync(true) }
  let first = (await left.engine.records()).find(row => row.entityId === rootId)!, second = (await right.engine.records()).find(row => row.entityId === rootId)!
  expect(first.state).toEqual(second.state); expect(first.state.company).toBe('Left employer'); expect(first.state.job_title).toBe('Right title')
  await left.engine.edit('application', rootId, { ...first.state, company: 'Conflict left' }, first.heads)
  await right.engine.edit('application', rootId, { ...second.state, company: 'Conflict right' }, second.heads)
  for (let i = 0; i < 2; i++) { await left.engine.sync(true); await right.engine.sync(true) }
  first = (await left.engine.records()).find(row => row.entityId === rootId)!
  expect(first.reason).toBe('competing_values')
  await expect(left.engine.edit('application', rootId, { ...first.state, company: 'Stale overwrite' }, a.heads, true)).rejects.toThrow('record changed')
  await left.engine.edit('application', rootId, { ...first.variants[0]!.state, company: 'Human reviewed employer' }, first.heads, true)
  for (let i = 0; i < 2; i++) { await left.engine.sync(true); await right.engine.sync(true) }
  second = (await right.engine.records()).find(row => row.entityId === rootId)!
  expect(second.state.company).toBe('Human reviewed employer'); expect(second.reason).toBeNull()
})

it('reconciles a persisted upload intent after the response is lost without uploading twice', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  const root = (await replica.engine.records()).find(row => row.entityId === rootId)!
  await replica.engine.edit('application', rootId, { ...root.state, company: 'Uncertain write' }, root.heads)
  objects.loseResponse = true
  await expect(replica.engine.sync(true)).rejects.toThrow()
  const uploads = objects.calls.filter(call => call === 'upload').length
  expect((await replica.engine.status()).pending).toBe(1)
  await replica.engine.sync(true)
  expect(objects.calls.filter(call => call === 'upload').length).toBe(uploads)
  expect((await replica.engine.status()).pending).toBe(0)
})

it.each(['event_id', 'device_sequence'])('rejects different content for existing %s without advancing the cursor', async collision => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  const before = await replica.store.metadata(), key = await keyFromBytes(bytesKey())
  const root = fixture.crypto.batch.mutations[0]
  await publish(objects, [{ ...root, ...(collision === 'device_sequence' ? { event_id: crypto.randomUUID() } : {}), changes: { ...root.changes, company: 'Tampered duplicate' } }], key)
  await expect(replica.engine.sync(true)).rejects.toThrow(collision === 'event_id' ? 'reused' : 'sequence collision')
  expect((await replica.store.metadata())!.cursor).toBe(before!.cursor)
  expect((await replica.engine.records()).find(row => row.entityId === rootId)!.state.company).toBe(root.changes.company)
})

it('rejects an altered envelope and safely rediscovers an expired cursor', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  objects.expired = true; await expect(replica.engine.sync(true)).rejects.toThrow('expired')
  expect((await replica.store.metadata())!.cursor).toBeNull()
  await replica.engine.sync(true)
  const cursor = (await replica.store.metadata())!.cursor
  objects.put(crypto.randomUUID(), new TextEncoder().encode(JSON.stringify(fixture.crypto.envelope))); objects.corrupt = true
  await expect(replica.engine.sync(true)).rejects.toThrow('failed authentication')
  expect((await replica.store.metadata())!.cursor).toBe(cursor)
})

it('ignores unrelated removals but blocks loss of an authenticated workspace file', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  objects.feed.push({ id: 'other-workspace-probe', removed: true }); await replica.engine.sync(true)
  objects.feed.push({ id: [...objects.files.keys()][0]!, removed: true }); await expect(replica.engine.sync(true)).rejects.toThrow('Remote sync files')
})

it('prevents two stale tabs from allocating the same sequence or overwriting data', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  const second = new IndexedReplicaStore(replica.name, replica.factory); close.push(second); second.setKey(await keyFromBytes(bytesKey()), fixture.crypto.workspace)
  const a = await replica.store.metadata(), b = await second.metadata()
  await replica.store.commit(a, { ...a!, nextSequence: a!.nextSequence + 1 }, [])
  await expect(second.commit(b, { ...b!, nextSequence: 100 }, [{ store: 'outbox', id: 'should-rollback', value: true }])).rejects.toThrow('another tab')
  expect(await second.read('outbox', 'should-rollback')).toBeUndefined()
  expect((await second.metadata())!.nextSequence).toBe(a!.nextSequence + 1)
})

it('recovers a local resolution after interruption between its atomic journal commit and merge', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  const root = (await replica.engine.records()).find(row => row.entityId === rootId)!
  const commit = replica.store.commit.bind(replica.store); let writes = 0
  vi.spyOn(replica.store, 'commit').mockImplementation(async (...args) => { if (++writes === 2) throw new Error('simulated interruption'); return commit(...args) })
  await expect(replica.engine.edit('application', rootId, { ...root.state, company: 'Durable interrupted edit' }, root.heads)).rejects.toThrow('interruption')
  vi.restoreAllMocks(); replica.engine.lock()
  const restarted = new PhoneSyncEngine(replica.store, objects.remote()); await restarted.unlock(passphrase)
  expect((await restarted.records()).find(row => row.entityId === rootId)!.state.company).toBe('Durable interrupted edit')
  expect((await replica.store.metadata())!.dirty).toEqual([]); expect((await restarted.status()).pending).toBe(1)
})

it('does not create enrollment on an account mismatch or wrong recovery key', async () => {
  const objects = await seeded(), store = new IndexedReplicaStore(crypto.randomUUID(), new IDBFactory()); close.push(store)
  const engine = new PhoneSyncEngine(store, objects.remote())
  await expect(engine.pair(fixture.crypto.recovery, passphrase, { subject: 'another-account', email: 'other@example.invalid' }, 'phone.apps.googleusercontent.com')).rejects.toThrow()
  expect(await store.metadata()).toBeUndefined()
})

it('rolls back journal, sequence and projected state together if outbox storage fills', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  const root = (await replica.engine.records()).find(row => row.entityId === rootId)!, before = await replica.store.metadata()
  const put = IDBObjectStore.prototype.put
  vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementation(function(this: IDBObjectStore, value: any, key?: IDBValidKey) {
    if (this.name === 'outbox') throw new DOMException('synthetic quota failure', 'QuotaExceededError')
    return key === undefined ? put.call(this, value) : put.call(this, value, key)
  })
  await expect(replica.engine.edit('application', rootId, { ...root.state, company: 'Must roll back' }, root.heads)).rejects.toThrow('not saved')
  vi.restoreAllMocks()
  expect((await replica.store.metadata())!.nextSequence).toBe(before!.nextSequence)
  expect((await replica.engine.records()).find(row => row.entityId === rootId)!.state).toEqual(root.state)
  expect((await replica.engine.status()).pending).toBe(0)
})

it('cancels an in-flight offline unlock when the device is locked', async () => {
  const objects = await seeded(), replica = await paired(objects); close.push(replica.store)
  replica.engine.lock()
  const pending = replica.engine.unlock(passphrase); replica.engine.lock()
  await expect(pending).rejects.toThrow('cancelled'); expect(replica.engine.unlocked).toBe(false)
})

it('unblocks a previously visited sibling after a reviewed sequence resolution arrives', async () => {
  const objects = await seeded(), left = await paired(objects), right = await paired(objects); close.push(left.store, right.store)
  const state = { application_id: rootId, sequence_number: 2, due_at: '2026-11-02T10:00:00Z', status: 'PREPARED' }
  const leftId = 'ffffffff-ffff-4fff-8fff-ffffffffffff', rightId = '00000000-0000-4000-8000-000000000000'
  await left.engine.edit('followup', leftId, state)
  await right.engine.edit('followup', rightId, state)
  for (let i = 0; i < 2; i++) { await left.engine.sync(true); await right.engine.sync(true) }
  const conflict = (await right.engine.records()).find(row => row.entityId === leftId)!
  expect(conflict.reason).toBe('followup_sequence_collision')
  await right.engine.edit('followup', leftId, { ...conflict.variants[0]!.state, sequence_number: 3 }, conflict.heads, true)
  for (let i = 0; i < 2; i++) { await right.engine.sync(true); await left.engine.sync(true) }
  for (const peer of [left, right]) {
    const rows = (await peer.engine.records()).filter(row => row.entity === 'followup')
    expect(rows.map(row => row.state.sequence_number).sort()).toEqual([1, 2, 3]); expect(rows.every(row => !row.reason)).toBe(true)
  }
})
