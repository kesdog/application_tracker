import { afterEach, expect, it, vi } from 'vitest'
import { getDashboard, listApplications } from './api'

afterEach(() => vi.unstubAllGlobals())

it('serializes active application filters and omits blank values', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('[]'))
  vi.stubGlobal('fetch', fetchMock)
  await listApplications({ q: 'python engineer', status: 'INTERVIEW', company: '', date_from: '2026-09-01' })
  expect(fetchMock).toHaveBeenCalledWith('/api/applications?q=python+engineer&status=INTERVIEW&date_from=2026-09-01', expect.objectContaining({ cache: 'no-store' }))
})

it('loads dashboard counts, upcoming work, and recent activity', async () => {
  const data = { counts: { active_applications: 0 }, upcoming: [], recent_activity: [] }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(data)))
  vi.stubGlobal('fetch', fetchMock)
  await expect(getDashboard()).resolves.toEqual(data)
  expect(fetchMock).toHaveBeenCalledWith('/api/dashboard', expect.objectContaining({ cache: 'no-store' }))
})
