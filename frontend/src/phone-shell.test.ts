import { expect, it, vi } from 'vitest'
import { runInNewContext } from 'node:vm'
import source from '../public/sw.js?raw'
import manifest from '../public/manifest.webmanifest?raw'

function worker() {
  const handlers = new Map<string, (event: any) => void>()
  const fetch = vi.fn().mockResolvedValue({ status: 200 })
  const caches = { match: vi.fn().mockResolvedValue('offline guidance'), open: vi.fn().mockResolvedValue({ addAll: vi.fn() }), keys: vi.fn().mockResolvedValue(['tracker-public-shell-old', 'unrelated-app', 'tracker-public-shell-v1']), delete: vi.fn() }
  runInNewContext(source, { self: { addEventListener: (name: string, callback: (event: any) => void) => handlers.set(name, callback), location: { origin: 'https://tracker.test' }, clients: { claim: vi.fn() }, skipWaiting: vi.fn() }, caches, fetch, URL })
  return { handlers, fetch, caches }
}

it('never intercepts private API requests, writes, or other sites', () => {
  const { handlers, caches, fetch } = worker()
  for (const request of [{ url: 'https://tracker.test/api/applications', method: 'GET', mode: 'navigate' }, { url: 'https://tracker.test/api/settings/general', method: 'POST', mode: 'cors' }, { url: 'https://elsewhere.test/', method: 'GET', mode: 'navigate' }]) {
    const respondWith = vi.fn()
    handlers.get('fetch')!({ request, respondWith })
    expect(respondWith).not.toHaveBeenCalled()
  }
  expect(caches.match).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalled()
})

it('shows public offline guidance without caching the requested document', async () => {
  const { handlers, fetch, caches } = worker()
  fetch.mockRejectedValue(new Error('offline'))
  let response!: Promise<unknown>
  handlers.get('fetch')!({ request: { url: 'https://tracker.test/', method: 'GET', mode: 'navigate' }, respondWith: (value: Promise<unknown>) => { response = value } })
  expect(await response).toBe('offline guidance')
  expect(caches.match).toHaveBeenCalledWith('/offline.html')
  expect(caches.open).not.toHaveBeenCalled()
})

it('removes only this app’s old public cache and starts the installed app in follow-ups', async () => {
  const { handlers, caches } = worker()
  let pending!: Promise<unknown>
  handlers.get('activate')!({ waitUntil: (value: Promise<unknown>) => { pending = value } })
  await pending
  expect(caches.delete).toHaveBeenCalledExactlyOnceWith('tracker-public-shell-old')
  const parsed = JSON.parse(manifest)
  expect(parsed.start_url).toBe('/#/followups')
  expect(parsed.icons.map((icon: { sizes: string }) => icon.sizes)).toEqual(['192x192', '512x512'])
})
