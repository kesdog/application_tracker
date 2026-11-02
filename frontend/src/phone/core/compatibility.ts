/** Live acceptance check, independent of both replica storage implementations. */
import type { Authorization } from './auth'
import type { SyncTransport } from './drive'
import { decode64, keyFromBytes, openEnvelope, seal } from './crypto'
import { requireValue, type Batch } from './protocol'
export interface ProbeChallenge {
  probe_id: string; workspace_id: string; test_key: string; subject: string; desktop_client_id: string
  desktop_file_id: string; desktop_batch_id: string; phone_batch_id: string
}
export interface ProbeAPI {
  startProbe(clientId: string): Promise<ProbeChallenge>
  verifyProbe(probe: string, file: string, batch: string): Promise<{ verified: boolean }>
  cleanupProbe(probe: string): Promise<unknown>
}
export interface ProbePolling {
  sleep?: (milliseconds: number) => Promise<void>
  retryDelays?: readonly number[]
}
export async function verifyCrossClient(clientId: string, auth: Authorization, drive: SyncTransport, desktop: ProbeAPI, polling: ProbePolling = {}) {
  requireValue(auth.identity(), 'Connect the phone Web OAuth client first')
  const cursor = await drive.startCursor(), challenge = await desktop.startProbe(clientId)
  try {
    requireValue(challenge.desktop_client_id !== clientId && challenge.subject === auth.identity()!.subject, 'Use separate OAuth clients and the same Google account')
    const delays = [...(polling.retryDelays ?? [250, 500, 1000, 2000, 4000, 8000])]
    const sleep = polling.sleep ?? ((milliseconds: number) => new Promise<void>(resolve => setTimeout(resolve, milliseconds)))
    async function waitUntil(check: () => Promise<boolean>, message: string) {
      while (!await check()) {
        const delay = delays.shift(); requireValue(delay !== undefined, message)
        await sleep(delay!)
      }
    }
    const key = await keyFromBytes(decode64(challenge.test_key))
    await waitUntil(async () => (await drive.list()).some(file => file.id === challenge.desktop_file_id), 'The phone client cannot discover the desktop probe')
    const batch = await openEnvelope(await drive.download(challenge.desktop_file_id), key, challenge.workspace_id)
    requireValue(batch.batch_id === challenge.desktop_batch_id && batch.kind === 'ack' && !batch.mutations.length, 'The desktop probe did not authenticate')
    await waitUntil(async () => {
      // Re-read from the pre-upload cursor until Google publishes this file.
      // Poll only reads; never replay uploads or advance a replica cursor here.
      let next = cursor, observed = false; const seen = new Set<string>()
      while (true) {
        const page = await drive.changes(next); observed ||= page.files.some(file => file.id === challenge.desktop_file_id)
        if (!page.more) break
        requireValue(page.cursor !== next && !seen.has(page.cursor), 'Drive returned a repeated page'); seen.add(page.cursor); next = page.cursor
      }
      return observed
    }, 'The phone change feed did not observe the desktop probe')
    const answer: Batch = { version: 1, workspace_id: challenge.workspace_id, batch_id: challenge.phone_batch_id, device_id: crypto.randomUUID(), kind: 'ack', mutations: [], acknowledgments: {} }
    const file = await drive.upload(answer.batch_id, await seal(answer, key))
    const result = await desktop.verifyProbe(challenge.probe_id, file, answer.batch_id)
    requireValue(result.verified, 'Desktop verification did not complete')
    return result
  } finally {
    // The desktop reconciles uncertain phone uploads using the preallocated
    // random probe batch ID, then authenticates each empty file before removal.
    await desktop.cleanupProbe(challenge.probe_id)
  }
}
