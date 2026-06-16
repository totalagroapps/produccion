const STATIC_CACHE = "registro-web-v2";
const STATIC_ASSETS = [
  "/static/logo.png",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/manifest.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key !== STATIC_CACHE).map(key => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  const url = new URL(req.url);

  if (url.origin === location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then(cached => cached || fetch(req))
    );
  } else if (req.mode === 'navigate' || url.pathname.startsWith("/registro_web")) {
    event.respondWith(
      fetch(req).then(res => {
        const resClone = res.clone();
        caches.open(STATIC_CACHE).then(cache => cache.put(req, resClone));
        return res;
      }).catch(() => caches.match(req))
    );
  }
});
