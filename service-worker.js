/* ════════════════════════════════════════════════════════════════════
 *  service-worker.js  ·  DeepNova v6.0 PWA
 *  Cache-first para estáticos · Network-first para /api/* y /chat
 * ════════════════════════════════════════════════════════════════════ */
const CACHE_NAME = 'deepnova-v6';
const PRECACHE = [
  '/',
  '/index.html',
  '/favicon.svg',
  '/site.webmanifest'
];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(PRECACHE).catch(() => {}))
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Network-first para API y chat (datos frescos)
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/chat') ||
      url.pathname.startsWith('/sessions') ||
      url.pathname.startsWith('/oauth')) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // Cache-first para estáticos
  e.respondWith(
    caches.match(e.request).then((cached) => {
      return cached || fetch(e.request).then((res) => {
        if (res && res.status === 200 && e.request.method === 'GET') {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(e.request, copy));
        }
        return res;
      }).catch(() => cached);
    })
  );
});
