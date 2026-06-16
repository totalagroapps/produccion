import os

# 1. MAIN.PY
with open('main.py', 'r', encoding='utf-8') as f:
    text = f.read()

if 'from fastapi.middleware.gzip import GZipMiddleware' not in text:
    text = text.replace('from starlette.middleware.sessions import SessionMiddleware',
                        'from starlette.middleware.sessions import SessionMiddleware\nfrom fastapi.middleware.gzip import GZipMiddleware')

if 'from zoneinfo import ZoneInfo' not in text:
    text = text.replace('from datetime import datetime', 'from datetime import datetime\nfrom zoneinfo import ZoneInfo')

if 'app.add_middleware(GZipMiddleware' not in text:
    text = text.replace('app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)',
                        'app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)\napp.add_middleware(GZipMiddleware, minimum_size=500)')

text = text.replace('datetime.now()', 'datetime.now(ZoneInfo("America/Bogota"))')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(text)

# 2. ANDROID.PY
with open('routers/android.py', 'r', encoding='utf-8') as f:
    text2 = f.read()

if 'from zoneinfo import ZoneInfo' not in text2:
    text2 = text2.replace('from datetime import datetime', 'from datetime import datetime\nfrom zoneinfo import ZoneInfo')

text2 = text2.replace('datetime.now()', 'datetime.now(ZoneInfo("America/Bogota"))')

with open('routers/android.py', 'w', encoding='utf-8') as f:
    f.write(text2)

# 3. SW.JS
sw_content = """const STATIC_CACHE = "registro-web-v2";
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
"""

with open('static/sw.js', 'w', encoding='utf-8') as f:
    f.write(sw_content)
