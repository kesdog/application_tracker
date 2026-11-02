/** Browser Web Crypto implementation of the Python Compact Sync v1 envelope. */
import { canonical, exact, object, requireValue, uuid, validateBatch, type Batch } from './protocol'
const encoder = new TextEncoder(), decoder = new TextDecoder('utf-8', { fatal: true })
export const MAX_PLAINTEXT = 64 * 1024 * 1024
export function encode64(value: Uint8Array): string {
  let result = ''; for (let offset = 0; offset < value.length; offset += 32768) result += String.fromCharCode(...value.subarray(offset, offset + 32768))
  return btoa(result).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '')
}
export function decode64(value: string): Uint8Array<ArrayBuffer> {
  requireValue(typeof value === 'string' && /^[A-Za-z0-9_-]+$/.test(value))
  return Uint8Array.from(atob(value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - value.length % 4) % 4)), c => c.charCodeAt(0))
}
export async function keyFromBytes(raw: Uint8Array): Promise<CryptoKey> {
  requireValue(raw.byteLength === 32, 'A 256-bit recovery key is required')
  return crypto.subtle.importKey('raw', raw as BufferSource, 'AES-GCM', false, ['encrypt', 'decrypt'])
}
export async function encryptJson(value: unknown, key: CryptoKey, aad: string) {
  const nonce = crypto.getRandomValues(new Uint8Array(12))
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: encoder.encode(aad) }, key, encoder.encode(canonical(value)))
  return { nonce: encode64(nonce), ciphertext: encode64(new Uint8Array(encrypted)) }
}
export async function decryptJson(value: { nonce: string; ciphertext: string }, key: CryptoKey, aad: string): Promise<any> {
  return JSON.parse(decoder.decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: decode64(value.nonce), additionalData: encoder.encode(aad) }, key, decode64(value.ciphertext))))
}
async function digest(raw: Uint8Array) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', raw as BufferSource)), byte => byte.toString(16).padStart(2, '0')).join('') }
export async function hashJson(value: unknown) { return digest(encoder.encode(canonical(value))) }
async function transform(raw: Uint8Array, decompress = false): Promise<Uint8Array<ArrayBuffer>> {
  const stream = new Blob([raw as BlobPart]).stream().pipeThrough(decompress ? new DecompressionStream('gzip') : new CompressionStream('gzip'))
  const reader = stream.getReader(), parts: Uint8Array[] = []; let size = 0
  try {
    while (true) { const item = await reader.read(); if (item.done) break; size += item.value.length; requireValue(size <= MAX_PLAINTEXT, 'Decoded sync file exceeds the size limit'); parts.push(item.value) }
  } catch (error) { await reader.cancel().catch(() => {}); throw error }
  const result = new Uint8Array(size); let offset = 0; for (const part of parts) { result.set(part, offset); offset += part.length } return result
}
export async function seal(batch: Batch, key: CryptoKey): Promise<Uint8Array<ArrayBuffer>> {
  validateBatch(batch); const raw = encoder.encode(canonical(batch)); requireValue(raw.length <= MAX_PLAINTEXT)
  const header = { version: 1, workspace_id: batch.workspace_id, batch_id: batch.batch_id, sha256: await digest(raw) }
  const nonce = crypto.getRandomValues(new Uint8Array(12)), compressed = await transform(raw)
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: encoder.encode(canonical(header)) }, key, compressed)
  return encoder.encode(canonical({ header, nonce: encode64(nonce), ciphertext: encode64(new Uint8Array(encrypted)) }))
}
export async function openEnvelope(raw: Uint8Array, key: CryptoKey, workspace: string): Promise<Batch> {
  try {
    requireValue(raw.length <= (MAX_PLAINTEXT + 1024 * 1024) * 2)
    const envelope = object(JSON.parse(decoder.decode(raw))); exact(envelope, ['header', 'nonce', 'ciphertext']); const header = object(envelope.header)
    exact(header, ['version', 'workspace_id', 'batch_id', 'sha256']); requireValue(header.version === 1 && header.workspace_id === workspace); uuid(header.batch_id)
    const compressed = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: decode64(envelope.nonce), additionalData: encoder.encode(canonical(header)) }, key, decode64(envelope.ciphertext))
    const decoded = await transform(new Uint8Array(compressed), true); requireValue(await digest(decoded) === header.sha256)
    const batch = validateBatch(JSON.parse(decoder.decode(decoded))); requireValue(batch.batch_id === header.batch_id && batch.workspace_id === workspace)
    return batch
  } catch { throw new Error('Sync file failed authentication, schema or size validation; no data was applied') }
}
export async function recoveryKey(recovery: string, subject: string) {
  const [version, workspace, encoded, binding, extra] = recovery.trim().split('.')
  requireValue(version === 'ats1' && !extra && workspace && encoded && binding, 'Invalid recovery export'); uuid(workspace)
  const raw = decode64(encoded); requireValue(raw.length === 32)
  const hmac = await crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['verify'])
  requireValue(await crypto.subtle.verify('HMAC', hmac, decode64(binding), encoder.encode('tracker-sync-account-v1:' + workspace + ':' + subject)), 'Recovery export and Google account do not match')
  return { workspace, raw, key: await keyFromBytes(raw) }
}
export interface WrappedKey { salt: string; iterations: number; nonce: string; ciphertext: string }
async function passphraseKey(passphrase: string, salt: Uint8Array, iterations: number) {
  requireValue(passphrase.length >= 12 && passphrase.length <= 1024, 'Use an unlock passphrase of at least 12 characters')
  const material = await crypto.subtle.importKey('raw', encoder.encode(passphrase), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: salt as BufferSource, iterations }, material, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
}
export async function wrapKey(raw: Uint8Array, passphrase: string, workspace: string): Promise<WrappedKey> {
  const salt = crypto.getRandomValues(new Uint8Array(16)), iterations = 600_000
  return { salt: encode64(salt), iterations, ...await encryptJson({ key: encode64(raw) }, await passphraseKey(passphrase, salt, iterations), 'tracker-phone-vault-v1:' + workspace) }
}
export async function unwrapKey(wrapped: WrappedKey, passphrase: string, workspace: string): Promise<CryptoKey> {
  try {
    requireValue(wrapped.iterations >= 600_000 && wrapped.iterations <= 2_000_000)
    const value = await decryptJson(wrapped, await passphraseKey(passphrase, decode64(wrapped.salt), wrapped.iterations), 'tracker-phone-vault-v1:' + workspace)
    return keyFromBytes(decode64(value.key))
  } catch { throw new Error('Unable to unlock. Check your passphrase; local data was not changed.') }
}
