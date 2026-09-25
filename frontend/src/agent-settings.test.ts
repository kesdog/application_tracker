import { afterEach, expect, it, vi } from 'vitest'
import { getAgentSettings, regenerateAgentToken, saveAgentPermissions } from './api'

afterEach(() => vi.unstubAllGlobals())

it('loads settings without expecting a plaintext token', async () => {
  const body = { configured: true, permissions: { read: true, create: false, edit: false, draft: false, tasks: false, interviews: false } }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body)))
  vi.stubGlobal('fetch', fetchMock)
  await expect(getAgentSettings()).resolves.toEqual(body)
  expect(fetchMock).toHaveBeenCalledWith('/api/settings/agent', expect.objectContaining({ cache: 'no-store' }))
})

it('rotates a token and saves permission toggles', async () => {
  const permissions = { read: true, create: true, edit: false, draft: false, tasks: false, interviews: false }
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ configured: true, permissions, token: 'new-token' })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ configured: true, permissions })))
  vi.stubGlobal('fetch', fetchMock)
  await expect(regenerateAgentToken()).resolves.toMatchObject({ token: 'new-token' })
  await expect(saveAgentPermissions(permissions)).resolves.toMatchObject({ permissions })
  expect(fetchMock.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ method: 'POST' }))
  expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({ method: 'PUT', body: JSON.stringify(permissions) }))
})
