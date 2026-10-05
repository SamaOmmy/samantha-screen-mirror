// Caches the app shell so the app opens instantly. Never touches /api or /stream.
const CACHE = "samantha-mirror-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/stream") return;
  // The page itself: ask the PC first, because it is what signs a phone in from the QR link (/?token=...).
  // Only when the PC cannot be reached do we show the cached copy, which then explains what is wrong.
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          if (r.ok && !url.search) caches.open(CACHE).then((c) => c.put("/", r.clone()));
          return r;
        })
        .catch(async () => (await caches.match("/")) || Response.error())
    );
    return;
  }
  // Stale-while-revalidate for hashed assets.
  e.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(e.request, { ignoreSearch: true });
      const fresh = fetch(e.request)
        .then((r) => { if (r.ok) cache.put(e.request, r.clone()); return r; })
        .catch(() => cached);
      return cached || fresh;
    })
  );
});
