// Cache public offline guidance and icons only. Application data stays on the server.
const CACHE = 'tracker-public-shell-v1'
const PUBLIC = ['/offline.html', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png']
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)).then(() => self.skipWaiting()))
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
