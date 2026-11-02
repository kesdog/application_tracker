import { t } from './i18n'
import { browserSession } from './auth'
import type { ProbeChallenge } from './phone/core/compatibility'

export interface SyncStatus {
  initialized: boolean
  workspace_id?: string
  device_id?: string
  label?: string
  last_success?: string | null
  error?: string | null
  retry_at?: string | null
  recovery_required?: boolean
  running?: boolean
  pending_uploads: number
  pending_downloads: number
  conflicts: number
  remote_bytes?: number
  remote_objects?: number
  warnings?: string[]
  devices?: { device_id: string; last_seen: string; acknowledgments: Record<string, number> }[]
}
export type CompactState = Record<string, string | number | boolean | null>
export interface SyncConflict {
  id: string
  record_key: string
  heads: string[]
  reason: string
  base: CompactState
  variants: { head: string; device_id: string; actor: string; state: CompactState }[]
}

/** Inject session headers and HTTP to reuse this client in another Vue host. */
export class SyncClient {
  constructor(private readonly request: typeof fetch = (url, options) => fetch(url, options),
    private readonly authorize: (options: RequestInit) => RequestInit = options => browserSession.withHeaders(options),
    private readonly base = '/api/sync') {}

  private async call<T>(path: string, data?: unknown): Promise<T> {
    const response = await this.request(this.base + path, this.authorize({
      method: data === undefined ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin',
      ...(data === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
    }))
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(typeof body?.detail === 'string' ? body.detail : t("Sync request failed ({p0})", { p0: response.status }))
    }
    return response.json()
  }
  status() { return this.call<SyncStatus>('/status') }
  preparePhone() { return this.call<{ recovery_export: string; status: SyncStatus }>('/pair-phone', { confirm_encrypted_google_storage: true }) }
  startProbe(clientId: string) { return this.call<ProbeChallenge>('/probe/start', { phone_client_id: clientId }) }
  verifyProbe(probe: string, file: string, batch: string) { return this.call<{ verified: boolean }>('/probe/verify', { probe_id: probe, phone_file_id: file, phone_batch_id: batch }) }
  cleanupProbe(probe: string) { return this.call('/probe/cleanup', { probe_id: probe }) }
  initialize(label: string, recovery: string | null) {
    return this.call<{ workspace_id: string; recovery_export: string }>('/initialize', {
      label, recovery_export: recovery, confirm_encrypted_google_storage: true,
    })
  }
  run() { return this.call<SyncStatus>('/run', {}) }
  conflicts() { return this.call<SyncConflict[]>('/conflicts') }
  resolve(conflict: SyncConflict, state: CompactState) {
    return this.call<SyncStatus>(`/conflicts/${encodeURIComponent(conflict.id)}/resolve`, { state, expected_heads: conflict.heads })
  }
}

export const syncClient = new SyncClient()
