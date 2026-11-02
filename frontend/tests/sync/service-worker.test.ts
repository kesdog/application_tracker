import { expect, it, vi } from 'vitest'
import { runInNewContext } from 'node:vm'
import source from '../../public/phone/sw.js?raw'
import manifest from '../../public/phone/manifest.webmanifest?raw'

function worker() {
  const handlers = new Map<string, (event: any) => void>()
  const match = vi.fn().mockResolvedValue('cached independent phone shell'), addAll = vi.fn(), remove = vi.fn()
  const caches = { match, open: vi.fn().mockResolvedValue({ addAll }), keys: vi.fn().mockResolvedValue(['tracker-public-shell-v2', 'tracker-independent-phone-old', 'unrelated-cache']), delete: remove }
  const fetch = vi.fn().mockRejectedValue(new Error('offline'))
  runInNewContext(source.replace('/*PHONE_ASSETS*/ []', JSON.stringify(['/assets/phone-fixture.js', '/assets/phone-fixture.css'])), { self: { addEventListener: (name: string, handler: (event: any) => void) => handlers.set(name, handler), location: { origin: 'https://tracker.test' }, skipWaiting: vi.fn(), clients: { claim: vi.fn() } }, caches, fetch, URL })
  return { handlers, caches, fetch, addAll, match, remove }
}

it('installs a complete public app shell and keeps the desktop service-worker cache separate', async () => {
  const { handlers, addAll, remove } = worker()
  let work!: Promise<unknown>
  handlers.get('install')!({ waitUntil: (promise: Promise<unknown>) => { work = promise } }); await work
  expect(addAll).toHaveBeenCalledWith(expect.arrayContaining(['/phone/', '/phone/manifest.webmanifest', '/assets/phone-fixture.js', '/assets/phone-fixture.css']))
  handlers.get('activate')!({ waitUntil: (promise: Promise<unknown>) => { work = promise } }); await work
  expect(remove).toHaveBeenCalledExactlyOnceWith('tracker-independent-phone-old')
  expect(JSON.parse(manifest)).toMatchObject({ scope: '/phone/', start_url: '/phone/', display: 'standalone' })
})

it('reopens the phone shell without a server and never intercepts API, writes, Google or desktop pages', async () => {
  const { handlers, match } = worker(); let response!: Promise<unknown>
  handlers.get('fetch')!({ request: { method: 'GET', mode: 'navigate', url: 'https://tracker.test/phone/' }, respondWith: (promise: Promise<unknown>) => { response = promise } })
  expect(await response).toBe('cached independent phone shell'); expect(match).toHaveBeenCalledWith('/phone/')
  for (const request of [
    { method: 'GET', mode: 'cors', url: 'https://tracker.test/api/applications' },
    { method: 'POST', mode: 'cors', url: 'https://tracker.test/phone/' },
    { method: 'GET', mode: 'cors', url: 'https://www.googleapis.com/drive/v3/files' },
    { method: 'GET', mode: 'navigate', url: 'https://tracker.test/' },
  ]) {
    const respondWith = vi.fn(); handlers.get('fetch')!({ request, respondWith }); expect(respondWith).not.toHaveBeenCalled()
  }
})
