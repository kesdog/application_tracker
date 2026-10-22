import { expect, it, vi } from 'vitest'
import { SyncClient, type SyncConflict } from '../../src/syncClient'

it('uses an injected session/HTTP boundary and carries conflict preconditions', async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ initialized: true })))
  const client = new SyncClient(request, options => ({ ...options, headers: { ...options.headers, 'X-CSRF-Token': 'host-session' } }), '/other-host/sync')
  const conflict = { id: 'safe/id', heads: ['left', 'right'] } as SyncConflict
  await client.resolve(conflict, { company: 'Reviewed' })
  expect(request).toHaveBeenCalledWith('/other-host/sync/conflicts/safe%2Fid/resolve', expect.objectContaining({
    method: 'POST', cache: 'no-store', headers: expect.objectContaining({ 'X-CSRF-Token': 'host-session' }),
  }))
  expect(JSON.parse(request.mock.calls[0]![1].body)).toEqual({ state: { company: 'Reviewed' }, expected_heads: ['left', 'right'] })
})

it('surfaces server validation without interpreting a failed resolution as success', async () => {
  const client = new SyncClient(vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Conflict changed' }), { status: 409 })))
  await expect(client.run()).rejects.toThrow('Conflict changed')
})
