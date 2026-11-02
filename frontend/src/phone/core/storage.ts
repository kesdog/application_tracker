/** IndexedDB adapter. Crypto happens before a short atomic compare-and-swap transaction. */
import { decryptJson, encryptJson, type WrappedKey } from './crypto'
import { requireValue, type Entity, type MergeResult, type State } from './protocol'
export interface Workspace {
  version: number; workspace: string; device: string; nextSequence: number; subject: string; email: string; clientId: string
  vault: WrappedKey; cursor: string | null; lastSuccess: string | null; retryAt: number; failures: number; error: string | null; dirty?: string[]
}
export interface RecordState {
  id: string; entity: Entity; entityId: string; state: State; appliedHeads: string[]; heads: string[]
  reason: string | null; base: State; variants: MergeResult['variants']; candidate: State
}
export const STORES = ['events', 'records', 'outbox', 'batches', 'inbox', 'receipts', 'sequences'] as const
export type StoreName = typeof STORES[number]
export interface Change { store: StoreName; id: string; value?: any; record?: string; parent?: string; pending?: number }
export interface ReplicaStore {
  metadata(): Promise<Workspace | undefined>
  setKey(key: CryptoKey, workspace: string): void; lock(): void
  read<T>(store: StoreName, id: string): Promise<T | undefined>
  all<T>(store: StoreName, query?: { index: string; key: IDBValidKey }): Promise<T[]>
  commit(previous: Workspace | undefined, next: Workspace, changes: Change[]): Promise<void>
  close(): void
}
type Row = Omit<Change, 'store' | 'value'> & { encrypted: { nonce: string; ciphertext: string } }
export class IndexedReplicaStore implements ReplicaStore {
  private key?: CryptoKey
  private workspace = ''
  private generation = 0
  private connection?: Promise<IDBDatabase>
  constructor(private readonly name = 'tracker-independent-phone-v1', private readonly factory: IDBFactory = indexedDB) {}
  setKey(key: CryptoKey, workspace: string) { this.key = key; this.workspace = workspace; this.generation++ }
  lock() { this.key = undefined; this.generation++ }
  private db() {
    requireValue(this.factory, 'This browser cannot use persistent IndexedDB storage. Use a supported browser outside private mode.')
    return this.connection ??= new Promise<IDBDatabase>((resolve, reject) => {
      const request = this.factory.open(this.name, 1)
      request.onupgradeneeded = () => {
        request.result.createObjectStore('meta')
        for (const name of STORES) {
          const store = request.result.createObjectStore(name, { keyPath: 'id' })
          if (name === 'events') store.createIndex('record', 'record')
          if (name === 'records') { store.createIndex('parent', 'parent'); store.createIndex('pending', 'pending') }
        }
      }
      request.onsuccess = () => { const db = request.result; db.onversionchange = () => { db.close(); this.lock(); this.connection = undefined }; resolve(db) }
      request.onerror = () => { this.connection = undefined; reject(new Error('Phone storage is unavailable. Check browser storage permissions.')) }
      request.onblocked = () => reject(new Error('Close other phone-app tabs before upgrading local storage.'))
    })
  }
  async metadata(): Promise<Workspace | undefined> {
    const db = await this.db()
    return new Promise((resolve, reject) => { const request = db.transaction('meta').objectStore('meta').get('workspace'); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error) })
  }
  private async decode<T>(rows: Row[], store: StoreName): Promise<T[]> {
    const key = this.key, generation = this.generation; requireValue(key, 'Unlock this device first')
    const values: T[] = []
    // Sequential decoding bounds temporary allocations during larger bootstraps.
    for (const row of rows) values.push(await decryptJson(row.encrypted, key, this.workspace + ':' + store + ':' + row.id))
    requireValue(generation === this.generation, 'This device was locked during the operation')
    return values
  }
  async read<T>(store: StoreName, id: string): Promise<T | undefined> {
    const db = await this.db()
    const row = await new Promise<Row | undefined>((resolve, reject) => { const request = db.transaction(store).objectStore(store).get(id); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error) })
    return row ? (await this.decode<T>([row], store))[0] : undefined
  }
  async all<T>(store: StoreName, query?: { index: string; key: IDBValidKey }): Promise<T[]> {
    const db = await this.db()
    const rows = await new Promise<Row[]>((resolve, reject) => { const source = db.transaction(store).objectStore(store); const request = query ? source.index(query.index).getAll(query.key) : source.getAll(); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error) })
    return this.decode<T>(rows, store)
  }
  async commit(previous: Workspace | undefined, next: Workspace, changes: Change[]) {
    const key = this.key, generation = this.generation; requireValue(key && this.workspace === next.workspace, 'Unlock this device first')
    const rows: (Row | null)[] = []
    for (const change of changes) rows.push(change.value === undefined ? null : { id: change.id, record: change.record, parent: change.parent, pending: change.pending,
      encrypted: await encryptJson(change.value, key, this.workspace + ':' + change.store + ':' + change.id) })
    const db = await this.db(); requireValue(generation === this.generation, 'This device was locked during the operation')
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(['meta', ...new Set(changes.map(item => item.store))], 'readwrite')
      let failure = 'Phone storage could not commit. Pending work was preserved.'
      tx.oncomplete = () => resolve(); tx.onerror = () => {}; tx.onabort = () => reject(new Error(failure))
      const request = tx.objectStore('meta').get('workspace')
      request.onsuccess = () => {
        const current = request.result as Workspace | undefined
        if (generation !== this.generation || current?.version !== previous?.version || current?.device !== previous?.device) {
          failure = 'Local state changed in another tab or this device was locked. Refresh before retrying.'; tx.abort(); return
        }
        try {
          changes.forEach((change, index) => { const store = tx.objectStore(change.store); if (rows[index]) store.put(rows[index]); else store.delete(change.id) })
          tx.objectStore('meta').put({ ...next, version: (previous?.version ?? -1) + 1 }, 'workspace')
        } catch { failure = 'Phone storage is full or unavailable. This edit was not saved; existing data and pending work were preserved.'; tx.abort() }
      }
    })
  }
  close() { this.lock(); this.connection?.then(db => db.close()); this.connection = undefined }
}
