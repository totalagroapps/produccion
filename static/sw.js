const STATIC_CACHE = "registro-web-static-v1";
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
  const requestUrl = new URL(event.request.url);

  if (requestUrl.origin === location.origin && requestUrl.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
