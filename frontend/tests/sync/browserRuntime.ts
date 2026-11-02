/** Test-build-only adapter. Never included by a normal production build. */
import { PhoneSyncEngine } from '../../src/phone/core/engine'
import { GoogleDriveTransport } from '../../src/phone/core/drive'
import type { Authorization } from '../../src/phone/core/auth'
import type { ReplicaStore } from '../../src/phone/core/storage'
import type { PhoneRuntime } from '../../src/phone/runtime'
export function createRuntime(store: ReplicaStore, _clientId: string): PhoneRuntime {
  let connected = false
  const auth: Authorization = {
    async connect() { connected = true; return { subject: 'synthetic-verified-subject', email: 'synthetic-phone@example.invalid' } },
    identity() { return connected ? { subject: 'synthetic-verified-subject', email: 'synthetic-phone@example.invalid' } : undefined },
    token() { if (!connected) throw new Error('Connect the simulated account first'); return 'test-right' },
    clear() { connected = false }, invalidate() { connected = false },
  }
  const http: typeof fetch = (input, options) => {
    const url = new URL(String(input))
    if (url.origin !== 'https://www.googleapis.com') throw new Error('Unexpected synthetic Google destination')
    return fetch('/fixture/google' + url.pathname + url.search, options)
  }
  return { auth, engine: new PhoneSyncEngine(store, new GoogleDriveTransport(auth, http)), preload: async () => {} }
}
