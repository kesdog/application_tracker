import { expect, it } from 'vitest'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync } from 'node:fs'
import { resolve } from 'node:path'
import { fixture, paired, rootId, seeded, type Objects } from './support'

it('exchanges real encrypted edits with the production Python/SQLite peer and preserves private desktop text', async () => {
  const objects = await seeded(), phone = await paired(objects)
  mkdirSync(resolve('..', '.run'), { recursive: true })
  const directory = mkdtempSync(resolve('..', '.run', 'phone-sqlite-peer-'))
  const candidate = resolve('..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const python = existsSync(candidate) ? candidate : 'python'
  function desktop(edit?: Record<string, string>) {
    const files = [...objects.files].map(([id, file]) => ({ id, name: file.name, bytes: Buffer.from(file.bytes).toString('base64') }))
    const result = spawnSync(python, ['backend/tests/sync/phone_bridge.py', directory], { input: JSON.stringify({ files, edit }), cwd: resolve('..'), encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 })
    expect(result.status, result.stderr).toBe(0)
    const response = JSON.parse(result.stdout)
    for (const file of response.files) if (!objects.files.has(file.id)) {
      objects.files.set(file.id, { name: file.name, bytes: new Uint8Array(Buffer.from(file.bytes, 'base64')) }); objects.feed.push({ id: file.id })
    }
    return response
  }
  try {
    const root = (await phone.engine.records()).find(row => row.entityId === rootId)!
    await phone.engine.edit('application', rootId, { ...root.state, company: 'Edited on phone' }, root.heads)
    await phone.engine.sync(true)
    let response = desktop({ job_title: 'Edited on desktop', description: 'Desktop-only confidential description' })
    expect(response.application.company).toBe('Edited on phone')
    await phone.engine.sync(true)
    let updated = (await phone.engine.records()).find(row => row.entityId === rootId)!
    expect(updated.state.job_title).toBe('Edited on desktop'); expect(updated.state).not.toHaveProperty('description')
    await phone.engine.edit('application', rootId, { ...updated.state, company: 'Phone competing edit' }, updated.heads)
    desktop({ company: 'Desktop competing edit' })
    await phone.engine.sync(true); response = desktop(); await phone.engine.sync(true)
    updated = (await phone.engine.records()).find(row => row.entityId === rootId)!
    expect(updated.reason).toBe('competing_values')
    await phone.engine.edit('application', rootId, { ...updated.variants[0]!.state, company: 'Reviewed on phone' }, updated.heads, true)
    await phone.engine.sync(true); response = desktop()
    expect(response.application.company).toBe('Reviewed on phone')
    expect(response.application.description).toBe('Desktop-only confidential description')
    expect(response.status.conflicts).toBe(0)
  } finally { phone.store.close() }
}, 40_000)
