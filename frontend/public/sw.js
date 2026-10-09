// Cache public offline guidance and icons only. Application data stays on the server.
const CACHE = 'tracker-public-shell-v2'
const PUBLIC = ['/offline.html', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png']
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)).then(() => self.skipWaiting()))
})

function followupUrl(value) {
  return typeof value === 'string' && /^\/#\/followups(?:\/[a-zA-Z0-9-]+\/[a-zA-Z0-9-]+)?$/.test(value) ? value : '/#/followups'
}
self.addEventListener('push', event => {
  let payload = {}
  try { payload = event.data?.json() || {} } catch { /* Always show a visible fallback notification. */ }
  event.waitUntil(self.registration.showNotification('Application Tracker', {
    body: typeof payload.body === 'string' && payload.body.length <= 240 ? payload.body : 'A follow-up needs review. Open your queue to continue.',
    icon: '/icons/icon-192.png', badge: '/icons/apple-touch-icon.png',
    tag: typeof payload.tag === 'string' ? payload.tag.slice(0, 96) : 'tracker-reminder',
    data: { url: followupUrl(payload.url) },
  }))
})
self.addEventListener('notificationclick', event => {
  event.notification.close()
  const url = new URL(followupUrl(event.notification.data?.url), self.location.origin).href
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async clients => {
    const existing = clients.find(client => new URL(client.url).origin === self.location.origin)
    if (existing) { await existing.navigate(url); return existing.focus() }
    return self.clients.openWindow(url)
  }))
})
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('tracker-public-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()))
})
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url)
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/') || event.request.method !== 'GET') return
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(response => response.status >= 500 ? caches.match('/offline.html') : response).catch(() => caches.match('/offline.html')))
  } else if (PUBLIC.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)))
  }
})
