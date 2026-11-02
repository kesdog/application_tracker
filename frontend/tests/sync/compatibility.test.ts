import { expect, it, vi } from 'vitest'
import { verifyCrossClient, type ProbeAPI } from '../../src/phone/core/compatibility'
import type { Authorization } from '../../src/phone/core/auth'
import { keyFromBytes, openEnvelope, seal } from '../../src/phone/core/crypto'
import type { Batch } from '../../src/phone/core/protocol'
import { bytesKey, fixture, Objects } from './support'

it.each(['success', 'wrong_account', 'missing_feed', 'corrupt', 'delayed_feed', 'delayed_list', 'shared_budget'])('requires live evidence and cleans disposable probes: %s', async scenario => {
  const objects = new Objects(), key = await keyFromBytes(bytesKey()), workspace = crypto.randomUUID(), batchId = crypto.randomUUID(), phoneBatchId = crypto.randomUUID()
  const probeFiles: string[] = []
  const unrelated = objects.put(crypto.randomUUID(), new Uint8Array([1, 2]))
  const auth: Authorization = { connect: vi.fn(), identity: () => ({ subject: scenario === 'wrong_account' ? 'wrong-account' : fixture.crypto.subject, email: 'synthetic@example.invalid' }), token: () => 'synthetic', clear: vi.fn(), invalidate: vi.fn() }
  const api: ProbeAPI = {
    async startProbe() {
      const batch: Batch = { version: 1, workspace_id: workspace, batch_id: batchId, device_id: crypto.randomUUID(), kind: 'ack', mutations: [], acknowledgments: {} }
      const id = objects.put(batchId, await seal(batch, key)); probeFiles.push(id)
      if (scenario === 'corrupt') objects.files.get(id)!.bytes[10] ^= 1
      return { probe_id: 'synthetic-probe-reference-only', workspace_id: workspace, test_key: fixture.crypto.key, subject: fixture.crypto.subject,
        desktop_client_id: 'desktop.apps.googleusercontent.com', desktop_file_id: id, desktop_batch_id: batchId, phone_batch_id: phoneBatchId }
    },
    async verifyProbe(_reference, fileId, id) {
      const batch = await openEnvelope(objects.files.get(fileId)!.bytes, key, workspace)
      expect(batch.kind).toBe('ack'); expect(batch.mutations).toEqual([]); expect(id).toBe(phoneBatchId); return { verified: true }
    },
    cleanupProbe: vi.fn(async () => {
      for (const [id, file] of objects.files) if (probeFiles.includes(id) || file.name.endsWith(phoneBatchId)) objects.files.delete(id)
    }),
  }
  const drive = objects.remote()
  const list = drive.list.bind(drive), changes = drive.changes.bind(drive), cursors: string[] = []; let listCalls = 0
  if (['missing_feed', 'shared_budget'].includes(scenario)) drive.changes = async cursor => ({ files: [], removed: [], cursor, more: false })
  if (['delayed_list', 'shared_budget'].includes(scenario)) drive.list = async () => ++listCalls === 1 ? [] : list()
  if (scenario === 'delayed_feed') drive.changes = async cursor => { cursors.push(cursor); return cursors.length < 3 ? { files: [], removed: [], cursor: 'empty-new-cursor', more: false } : changes(cursor) }
  const sleep = vi.fn(async () => {}), upload = vi.spyOn(drive, 'upload'), polling = { sleep, retryDelays: [0, 0] }
  if (['success', 'delayed_feed', 'delayed_list'].includes(scenario)) {
    expect(await verifyCrossClient('phone.apps.googleusercontent.com', auth, drive, api, polling)).toEqual({ verified: true }); expect(upload).toHaveBeenCalledOnce()
  } else await expect(verifyCrossClient('phone.apps.googleusercontent.com', auth, drive, api, polling)).rejects.toThrow()
  if (['missing_feed', 'shared_budget', 'delayed_feed'].includes(scenario)) expect(sleep).toHaveBeenCalledTimes(2)
  if (scenario === 'delayed_feed') expect(cursors.every(cursor => cursor === cursors[0])).toBe(true)
  expect(api.cleanupProbe).toHaveBeenCalledOnce(); expect([...objects.files.keys()]).toEqual([unrelated]); expect(auth.connect).not.toHaveBeenCalled()
})
