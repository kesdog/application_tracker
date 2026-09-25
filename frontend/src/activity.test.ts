import { afterEach, expect, it, vi } from 'vitest'
import { deleteApplication, getTimeline, undoLastChange } from './api'

afterEach(() => vi.unstubAllGlobals())

it('loads an application timeline without caching', async () => {
  const payload = { events: [], undo_available: false }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)))
  vi.stubGlobal('fetch', fetchMock)
  await expect(getTimeline('app one')).resolves.toEqual(payload)
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/app%20one/timeline', expect.objectContaining({ cache: 'no-store' }))
})

it('requests one-step undo from the application endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"audit_id":"audit","entity_type":"APPLICATION","entity_id":"app","fields":["status"]}'))
  vi.stubGlobal('fetch', fetchMock)
  await undoLastChange('app')
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/app/undo', expect.objectContaining({ method: 'POST' }))
})

it('soft deletes through the application endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(deleteApplication('app')).resolves.toBeUndefined()
  expect(fetchMock).toHaveBeenCalledWith('/api/applications/app', expect.objectContaining({ method: 'DELETE' }))
})
