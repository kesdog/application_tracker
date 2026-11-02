import { IDBFactory } from 'fake-indexeddb'
import { PhoneSyncEngine } from '../../src/phone/core/engine'
import { IndexedReplicaStore } from '../../src/phone/core/storage'
import { decode64, seal } from '../../src/phone/core/crypto'
import { ProviderError, FILE_PREFIX, type RemoteFile, type SyncTransport } from '../../src/phone/core/drive'
import type { Batch } from '../../src/phone/core/protocol'
import source from './fixtures/protocol.json?raw'
export const fixture = JSON.parse(source)
export const passphrase = 'only synthetic test passphrase'
export class Objects {
  files = new Map<string, { name: string; bytes: Uint8Array<ArrayBuffer> }>()
  feed: { id: string; removed?: boolean }[] = []
  offline = false; loseResponse = false; corrupt = false; expired = false
  calls: string[] = []
  account = fixture.crypto.subject
  put(batchId: string, bytes: Uint8Array) {
    const id = crypto.randomUUID(); this.files.set(id, { name: FILE_PREFIX + batchId, bytes: new Uint8Array(bytes) }); this.feed.push({ id }); return id
  }
  remote(): SyncTransport {
    const store = this
    function check() { if (store.offline) throw new ProviderError('unavailable') }
    function metadata(id: string): RemoteFile { return { id, name: store.files.get(id)!.name } }
    return {
      identity: () => store.account,
      async startCursor() { check(); store.calls.push('start'); return String(store.feed.length) },
      async list() { check(); store.calls.push('list'); return [...store.files.keys()].map(metadata) },
      async changes(cursor) {
        check(); store.calls.push('changes'); if (store.expired) { store.expired = false; throw new ProviderError('invalid_cursor') }
        const offset = Number(cursor), entries = store.feed.slice(offset, offset + 2)
        return { files: entries.filter(item => !item.removed).map(item => metadata(item.id)), removed: entries.filter(item => item.removed).map(item => item.id), cursor: String(offset + entries.length), more: offset + entries.length < store.feed.length }
      },
      async download(id) { check(); store.calls.push('download'); return store.corrupt ? new TextEncoder().encode('{"header":{"workspace_id":"' + fixture.crypto.workspace + '"}}') : new Uint8Array(store.files.get(id)!.bytes) },
      async upload(batchId, bytes) {
        check(); store.calls.push('upload'); const id = store.put(batchId, bytes)
        if (store.loseResponse) { store.loseResponse = false; throw new ProviderError('unavailable') } return id
      },
    }
  }
}
export async function seeded() {
  const objects = new Objects()
  objects.put(fixture.crypto.batch.batch_id, new TextEncoder().encode(JSON.stringify(fixture.crypto.envelope)))
  return objects
}
export async function paired(objects: Objects, name = crypto.randomUUID(), factory = new IDBFactory()) {
  const store = new IndexedReplicaStore(name, factory), engine = new PhoneSyncEngine(store, objects.remote())
  await engine.pair(fixture.crypto.recovery, passphrase, { subject: fixture.crypto.subject, email: 'synthetic@example.invalid' }, 'phone.apps.googleusercontent.com')
  await engine.sync(true)
  return { store, engine, name, factory }
}
export async function publish(objects: Objects, mutations: Batch['mutations'], key: CryptoKey, kind: Batch['kind'] = 'events') {
  const batch: Batch = { version: 1, workspace_id: fixture.crypto.workspace, device_id: mutations[0]?.device_id ?? crypto.randomUUID(), batch_id: crypto.randomUUID(), kind, mutations, acknowledgments: {} }
  const bytes = await seal(batch, key); return objects.put(batch.batch_id, bytes)
}
export const rootId = fixture.crypto.batch.mutations[0].entity_id as string
export const bytesKey = () => decode64(fixture.crypto.key)
