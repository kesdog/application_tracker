/** Drive transport with injected credentials/HTTP. No UI, database or merge imports. */
import type { Authorization } from './auth'
import { requireValue } from './protocol'
export interface RemoteFile { id: string; name: string; size?: string }
export interface RemotePage { files: RemoteFile[]; removed: string[]; cursor: string; more: boolean }
export interface SyncTransport {
  identity(): string; startCursor(): Promise<string>; list(): Promise<RemoteFile[]>
  changes(cursor: string): Promise<RemotePage>; download(id: string): Promise<Uint8Array<ArrayBuffer>>
  upload(batchId: string, bytes: Uint8Array): Promise<string>
}
export class ProviderError extends Error {
  constructor(public readonly kind: 'authorization' | 'rate_limit' | 'storage_full' | 'setup_required' | 'invalid_cursor' | 'missing' | 'unavailable' | 'request', public readonly retryAfter = 0) {
    super({ authorization: 'Reconnect Google to sync. Offline edits are saved.', rate_limit: 'Google rate limit reached. Pending edits are saved.', storage_full: 'Google storage is full. Pending edits are saved.', setup_required: 'Enable Google Drive API in the Google Cloud project, then retry. Your account permission is preserved.', invalid_cursor: 'Drive cursor expired. Sync again to rediscover files.', missing: 'A remote sync file is missing. Preserve local data and review recovery.', unavailable: 'Google is unavailable. Pending edits are saved.', request: 'Google rejected this request. Pending edits are saved.' }[kind])
  }
}
export const FILE_PREFIX = 'tracker-sync-v1-'
export class GoogleDriveTransport implements SyncTransport {
  constructor(private readonly auth: Authorization, private readonly http: typeof fetch = (input, init) => fetch(input, init), private readonly timeoutMs = 20_000) {}
  identity() { const identity = this.auth.identity(); requireValue(identity, 'Connect Google first'); return identity.subject }
  private async call(path: string, options: RequestInit = {}, query: Record<string, string> = {}) {
    requireValue(/^(drive\/v3|upload\/drive\/v3)\//.test(path) && !path.includes('..'))
    const url = new URL(path, 'https://www.googleapis.com/'); Object.entries(query).forEach(([key, value]) => url.searchParams.set(key, value))
    let response: Response
    const token = this.auth.token()
    try { response = await this.http(url, { ...options, headers: { ...options.headers, Authorization: 'Bearer ' + token }, credentials: 'omit', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(this.timeoutMs) }) }
    catch { throw new ProviderError('unavailable') }
    if (response.ok) return response
    let reasons: string[] = []
    try { const body = await response.json(); reasons = ['errors', 'details'].flatMap(field => Array.isArray(body.error?.[field]) ? body.error[field].filter((item: any) => typeof item?.reason === 'string').map((item: any) => item.reason) : []) } catch { /* Never expose provider response bodies. */ }
    const status = response.status
    const retryHeader = response.headers.get('Retry-After'), retryAfter = Math.min(3600, Math.max(0, /^\d+$/.test(retryHeader ?? '') ? Number(retryHeader) : (Date.parse(retryHeader ?? '') - Date.now()) / 1000 || 0))
    if (status === 429 || reasons.some(reason => ['rateLimitExceeded', 'userRateLimitExceeded', 'dailyLimitExceeded'].includes(reason))) throw new ProviderError('rate_limit', retryAfter)
    if (reasons.some(reason => ['storageQuotaExceeded', 'teamDriveFileLimitExceeded'].includes(reason))) throw new ProviderError('storage_full')
    if (reasons.some(reason => ['accessNotConfigured', 'SERVICE_DISABLED'].includes(reason))) throw new ProviderError('setup_required')
    if (status === 401 || status === 403) { this.auth.invalidate(token); throw new ProviderError('authorization') }
    throw new ProviderError(status === 410 ? 'invalid_cursor' : status === 404 ? 'missing' : status >= 500 ? 'unavailable' : 'request')
  }
  async startCursor() { const page = await (await this.call('drive/v3/changes/startPageToken')).json(); requireValue(typeof page.startPageToken === 'string'); return page.startPageToken as string }
  async list(): Promise<RemoteFile[]> {
    const files: RemoteFile[] = [], seen = new Set<string>(); let token = ''
    do {
      const page = await (await this.call('drive/v3/files', {}, { spaces: 'appDataFolder', q: 'trashed=false', pageSize: '1000', fields: 'nextPageToken,files(id,name,size)', ...(token ? { pageToken: token } : {}) })).json()
      files.push(...(page.files ?? []).filter((file: RemoteFile) => file.name?.startsWith(FILE_PREFIX)))
      token = page.nextPageToken ?? ''; requireValue(!token || !seen.has(token), 'Drive returned a repeated page'); seen.add(token)
    } while (token)
    return files
  }
  async changes(cursor: string): Promise<RemotePage> {
    const page = await (await this.call('drive/v3/changes', {}, { pageToken: cursor, spaces: 'appDataFolder', pageSize: '1000', fields: 'nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,size))' })).json()
    const next = page.nextPageToken ?? page.newStartPageToken; requireValue(typeof next === 'string', 'Drive did not return a durable change cursor')
    return { files: (page.changes ?? []).filter((item: any) => !item.removed && item.file?.name?.startsWith(FILE_PREFIX)).map((item: any) => item.file), removed: (page.changes ?? []).filter((item: any) => item.removed).map((item: any) => item.fileId), cursor: next, more: Boolean(page.nextPageToken) }
  }
  async download(id: string) {
    const response = await this.call('drive/v3/files/' + encodeURIComponent(id), {}, { alt: 'media' })
    const reader = response.body!.getReader(), chunks: Uint8Array[] = []; let length = 0
    try { while (true) { const next = await reader.read(); if (next.done) break; length += next.value.length; requireValue(length <= 130 * 1024 * 1024, 'Sync file exceeds the encrypted size limit'); chunks.push(next.value) } }
    catch (error) { await reader.cancel().catch(() => {}); throw error }
    const bytes = new Uint8Array(length); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length } return bytes
  }
  async upload(batchId: string, bytes: Uint8Array) {
    const boundary = 'sync-' + crypto.randomUUID(), metadata = JSON.stringify({ name: FILE_PREFIX + batchId, parents: ['appDataFolder'], appProperties: { protocol: 'tracker-sync-v1' } })
    const body = new Blob([`--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${metadata}\r\n--${boundary}\r\nContent-Type: application/octet-stream\r\n\r\n`, bytes as BlobPart, `\r\n--${boundary}--\r\n`])
    return (await (await this.call('upload/drive/v3/files', { method: 'POST', body, headers: { 'Content-Type': 'multipart/related; boundary=' + boundary } }, { uploadType: 'multipart', fields: 'id' })).json()).id as string
  }
}
