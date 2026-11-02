/* Built assets are injected by Vite. Only the public phone shell is cached. */
const ASSETS = /*PHONE_ASSETS*/ []
const CACHE = 'tracker-independent-phone-' + /*PHONE_VERSION*/ 'development'
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['/phone/', '/phone/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', ...ASSETS])).then(() => self.skipWaiting()))
})
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('tracker-independent-phone-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()))
})
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  if (event.request.mode === 'navigate' && url.pathname.startsWith('/phone/')) {
    event.respondWith(fetch(event.request).then(response => response.ok ? response : caches.match('/phone/')).catch(() => caches.match('/phone/')))
  } else if (ASSETS.includes(url.pathname) || ['/phone/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'].includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)))
  }
})
