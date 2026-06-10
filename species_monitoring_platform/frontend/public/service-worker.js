const CACHE_VERSION = 4;
const CACHE_NAME = `bird-platform-v${CACHE_VERSION}`;
const API_CACHE = `bird-api-cache-v${CACHE_VERSION}`;
const TILE_CACHE = `bird-tile-cache-v${CACHE_VERSION}`;
const API_CACHE_DURATION = 5 * 60 * 1000;
const PROXIED_TILE_PATH_PREFIXES = ['/api/map-tiles/', '/api/maps/tiles/'];

const STATIC_ASSETS = [
  '/manifest.webmanifest',
  '/app-icon.svg',
];

const CACHEABLE_API_PATHS = [
  '/api/species',
  '/api/health',
  '/api/config',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== API_CACHE && key !== TILE_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Let non-GET requests fall through to the app. The field client already
  // maintains its own durable sync queue and the service worker cannot safely
  // use window-only storage APIs for request replay.
  if (event.request.method !== 'GET') {
    return;
  }

  if (url.origin === self.location.origin && PROXIED_TILE_PATH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
    event.respondWith(staleWhileRevalidateTile(event.request));
    return;
  }

  if (CACHEABLE_API_PATHS.some((path) => url.pathname === path)) {
    event.respondWith(networkFirstWithCache(event.request));
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirstNavigation(event.request));
    return;
  }

  if (url.origin === self.location.origin && !url.pathname.startsWith('/api') && !url.pathname.startsWith('/ws')) {
    event.respondWith(staleWhileRevalidate(event.request));
  }
});

async function networkFirstWithCache(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      const clone = response.clone();
      const headers = new Headers(clone.headers);
      headers.set('x-sw-cached-at', Date.now().toString());
      const body = await clone.blob();
      await cache.put(request, new Response(body, { status: clone.status, statusText: clone.statusText, headers }));
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) {
      const cachedAt = parseInt(cached.headers.get('x-sw-cached-at') || '0', 10);
      if (Date.now() - cachedAt < API_CACHE_DURATION) {
        return cached;
      }
    }
    return new Response(
      JSON.stringify({ error: 'Offline', detail: 'Network unavailable and no cached data' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    );
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const isHtmlRequest = request.headers.get('accept')?.includes('text/html');

  const networkPromise = fetch(request)
    .then((response) => {
      if (response.ok && !isHtmlRequest) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    networkPromise.catch(() => {});
    return cached;
  }

  const networkResponse = await networkPromise;
  if (networkResponse) return networkResponse;

  if (request.headers.get('accept')?.includes('text/html')) {
    const fallback = await cache.match('/');
    if (fallback) return fallback;
  }

  return new Response('Offline', { status: 503 });
}

async function networkFirstNavigation(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response.ok) {
      await cache.put('/index.html', response.clone());
    }
    return response;
  } catch {
    const fallback = (await cache.match('/index.html')) || (await cache.match('/'));
    if (fallback) return fallback;
    return new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidateTile(request) {
  const cache = await caches.open(TILE_CACHE);
  const cached = await cache.match(request);

  const networkPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    networkPromise.catch(() => {});
    return cached;
  }

  const networkResponse = await networkPromise;
  if (networkResponse) return networkResponse;

  return new Response('Offline', { status: 503 });
}
