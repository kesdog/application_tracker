import { expect, it, vi } from 'vitest'
import { runInNewContext } from 'node:vm'
import source from '../public/sw.js?raw'
import manifest from '../public/manifest.webmanifest?raw'

function worker() {
  const handlers = new Map<string, (event: any) => void>()
  const fetch = vi.fn().mockResolvedValue({ status: 200 })
  const caches = { match: vi.fn().mockResolvedValue('offline guidance'), open: vi.fn().mockResolvedValue({ addAll: vi.fn() }), keys: vi.fn().mockResolvedValue(['tracker-public-shell-v1', 'unrelated-app', 'tracker-public-shell-v2']), delete: vi.fn() }
  const showNotification = vi.fn()
  const clients = { claim: vi.fn(), matchAll: vi.fn().mockResolvedValue([]), openWindow: vi.fn() }
  runInNewContext(source, { self: { addEventListener: (name: string, callback: (event: any) => void) => handlers.set(name, callback), location: { origin: 'https://tracker.test' }, registration: { showNotification }, clients, skipWaiting: vi.fn() }, caches, fetch, URL })
  return { handlers, fetch, caches, showNotification, clients }
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
  expect(caches.delete).toHaveBeenCalledExactlyOnceWith('tracker-public-shell-v1')
  const parsed = JSON.parse(manifest)
  expect(parsed.start_url).toBe('/#/followups')
  expect(parsed.icons.map((icon: { sizes: string }) => icon.sizes)).toEqual(['192x192', '512x512'])
})

it('displays a visible push and restricts its destination to follow-up links', async () => {
  const { handlers, showNotification } = worker()
  let pending!: Promise<unknown>
  handlers.get('push')!({ data: { json: () => ({body:'2 follow-ups need review.',url:'https://evil.test/',tag:'batch-1'}) }, waitUntil: (value: Promise<unknown>) => { pending = value } })
  await pending
  expect(showNotification).toHaveBeenCalledWith('Application Tracker', expect.objectContaining({ body:'2 follow-ups need review.', data:{url:'/#/followups'} }))
  handlers.get('push')!({ data: { json: () => { throw new Error('malformed') } }, waitUntil: (value: Promise<unknown>) => { pending = value } })
  await pending
  expect(showNotification).toHaveBeenLastCalledWith('Application Tracker', expect.objectContaining({ body:expect.stringContaining('needs review') }))
})

it('opens the exact message on notification click without updating or sending it', async () => {
  const { handlers, clients, fetch } = worker()
  let pending!: Promise<unknown>
  const close = vi.fn()
  handlers.get('notificationclick')!({ notification:{close,data:{url:'/#/followups/job-1/message-1'}},waitUntil:(value:Promise<unknown>)=>{pending=value} })
  await pending
  expect(close).toHaveBeenCalledOnce()
  expect(clients.openWindow).toHaveBeenCalledExactlyOnceWith('https://tracker.test/#/followups/job-1/message-1')
  expect(fetch).not.toHaveBeenCalled()
})
