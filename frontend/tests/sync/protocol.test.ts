import { describe, expect, it } from 'vitest'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { existsSync } from 'node:fs'
import source from './fixtures/protocol.json?raw'
import { canonical, mergeEvents, validateBatch, validateMutation } from '../../src/phone/core/protocol'
import { decode64, keyFromBytes, openEnvelope, recoveryKey, seal, unwrapKey, wrapKey } from '../../src/phone/core/crypto'
const fixture = JSON.parse(source), bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value))

describe('Python/browser interoperability', () => {
  for (const sample of fixture.cases) it('matches Python causal merge: ' + sample.name, () => {
    const result = mergeEvents(sample.events.map(validateMutation))
    expect({ ...result, ready: [...result.ready].sort() }).toEqual(sample.expected)
    const reversed = mergeEvents([...sample.events].reverse().map(validateMutation))
    expect({ ...reversed, ready: [...reversed.ready].sort() }).toEqual(sample.expected)
  })
  it('decrypts the Python AES-GCM/gzip envelope and emits a Python-readable envelope', async () => {
    const key = await keyFromBytes(decode64(fixture.crypto.key))
    expect(await openEnvelope(bytes(fixture.crypto.envelope), key, fixture.crypto.workspace)).toEqual(fixture.crypto.batch)
    expect(canonical(fixture.crypto.batch)).toBe(fixture.crypto.canonical)
    const encrypted = await seal(fixture.crypto.batch, key)
    const candidate = resolve('..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
    const python = existsSync(candidate) ? candidate : 'python'
    const result = spawnSync(python, ['-c', 'import sys; from app.sync.crypto import open_envelope,decode_key,canonical; b=open_envelope(sys.stdin.buffer.read(),decode_key(sys.argv[1]),sys.argv[2]); sys.stdout.buffer.write(canonical(b.model_dump(mode="json")))', fixture.crypto.key, fixture.crypto.workspace], { input: encrypted, cwd: resolve('..') })
    expect(result.status, result.stderr.toString()).toBe(0)
    expect(result.stdout.toString('utf8')).toBe(fixture.crypto.canonical)
  })
  it('binds recovery to the Google subject and wraps the key for offline unlock', async () => {
    const recovered = await recoveryKey(fixture.crypto.recovery, fixture.crypto.subject)
    await expect(recoveryKey(fixture.crypto.recovery, 'another-account')).rejects.toThrow('do not match')
    const wrapped = await wrapKey(recovered.raw, 'synthetic passphrase only', recovered.workspace)
    const key = await unwrapKey(wrapped, 'synthetic passphrase only', recovered.workspace)
    expect(await openEnvelope(bytes(fixture.crypto.envelope), key, recovered.workspace)).toEqual(fixture.crypto.batch)
    await expect(unwrapKey(wrapped, 'wrong synthetic passphrase', recovered.workspace)).rejects.toThrow('Unable to unlock')
    await expect(unwrapKey({ ...wrapped, iterations: 1 }, 'synthetic passphrase only', recovered.workspace)).rejects.toThrow('Unable to unlock')
  })
  it.each(['nonce', 'ciphertext', 'workspace', 'hash', 'extra'])('rejects tampering before applying data: %s', async field => {
    const envelope = structuredClone(fixture.crypto.envelope)
    if (field === 'workspace') envelope.header.workspace_id = crypto.randomUUID()
    else if (field === 'hash') envelope.header.sha256 = '0'.repeat(64)
    else if (field === 'extra') envelope.extra = true
    else envelope[field] = envelope[field].slice(0, -5) + 'AAAAA'
    await expect(openEnvelope(bytes(envelope), await keyFromBytes(decode64(fixture.crypto.key)), fixture.crypto.workspace)).rejects.toThrow('failed authentication')
  })
  it.each(['description', 'body', 'subject', 'contact_email', 'document_id', 'access_token'])('rejects private fields in events and checkpoints: %s', field => {
    const batch = structuredClone(fixture.crypto.batch); batch.mutations[0].changes[field] = 'excluded private content'
    expect(() => validateBatch(batch)).toThrow()
  })
  it('retains explicit conflicts across every four-event delivery permutation', () => {
    const root = fixture.cases[0].events[0], a = fixture.cases.find((item: any) => item.name === 'competing').events[1], b = fixture.cases.find((item: any) => item.name === 'competing').events[2]
    const c = { ...b, event_id: crypto.randomUUID(), device_id: crypto.randomUUID(), device_seq: 1, changes: { company: 'Third employer' } }
    function permutations<T>(items: T[]): T[][] { return items.length ? items.flatMap((item, index) => permutations(items.filter((_, other) => other !== index)).map(rest => [item, ...rest])) : [[]] }
    for (const order of permutations([root, a, b, c])) expect(mergeEvents(order).reason).toBe('competing_values')
  })
})
