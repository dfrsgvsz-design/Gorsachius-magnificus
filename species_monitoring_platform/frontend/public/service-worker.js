const CACHE_VERSION = 4;
const CACHE_NAME = `bird-platform-v${CACHE_VERSION}`;
const API_CACHE = `bird-api-cache-v${CACHE_VERSION}`;
const TILE_CACHE = `bird-tile-cache-v${CACHE_VERSION}`;
const API_CACHE_DURATION = 5 * 60 * 1000;
// Field crews routinely revisit the same survey area for ~30 days during a
// season. We keep tiles cached for that window so an airplane-mode trek up
// the mountain still shows the basemap users browsed before. After 30 days
// we prefer a fresh fetch (the underlying OSM data may have changed) but
// still fall back to the stale copy if the network is unreachable rather
// than degrade to a blank 503 — Batch 6 / W3 release.
const TILE_CACHE_DURATION = 30 * 24 * 60 * 60 * 1000;
const PROXIED_TILE_PATH_PREFIXES = ['/api/map-tiles/', '/api/maps/tiles/'];

/**
 * Pure freshness check for a cached tile. Exported via `self.__swInternals`
 * so the renderer-side unit tests can drive it without standing up a service
 * worker. Returns `true` when the timestamp is positive and the elapsed time
 * is at most `ttlMs`. A missing timestamp (`0` / `NaN`) is treated as stale
 * so legacy un-stamped tiles re-fetch on next contact with the network.
 */
function isTileCacheFresh(cachedAtMs, now, ttlMs) {
  if (!Number.isFinite(cachedAtMs) || cachedAtMs <= 0) return false;
  if (!Number.isFinite(now) || !Number.isFinite(ttlMs) || ttlMs <= 0) return false;
  return now - cachedAtMs <= ttlMs;
}

self.__swInternals = self.__swInternals || {};
self.__swInternals.isTileCacheFresh = isTileCacheFresh;
self.__swInternals.TILE_CACHE_DURATION = TILE_CACHE_DURATION;

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

// Wraps a network response in a new Response that carries an
// `x-sw-cached-at` header so the freshness check on the next request can
// reject tiles older than `TILE_CACHE_DURATION`. Same envelope shape as the
// API cache writer above; reused by `prefetchMapTiles` via the
// `__swInternals` namespace.
async function buildTimestampedTileResponse(response) {
  const headers = new Headers(response.headers);
  headers.set('x-sw-cached-at', Date.now().toString());
  const body = await response.clone().blob();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

self.__swInternals.buildTimestampedTileResponse = buildTimestampedTileResponse;

async function staleWhileRevalidateTile(request) {
  const cache = await caches.open(TILE_CACHE);
  const cached = await cache.match(request);

  const networkPromise = fetch(request)
    .then(async (response) => {
      if (response.ok || response.status === 0) {
        try {
          const stamped = await buildTimestampedTileResponse(response);
          await cache.put(request, stamped);
        } catch {
          // Opaque or otherwise un-clonable responses still get cached
          // unstamped via the legacy path; the freshness check treats them
          // as stale on next read, so they will be re-fetched promptly.
          try {
            await cache.put(request, response.clone());
          } catch {
            // Ignore — we still return the live response below.
          }
        }
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    const cachedAtMs = parseInt(cached.headers.get('x-sw-cached-at') || '0', 10);
    if (isTileCacheFresh(cachedAtMs, Date.now(), TILE_CACHE_DURATION)) {
      // Fresh: classic stale-while-revalidate — serve cache, refresh async.
      networkPromise.catch(() => {});
      return cached;
    }
    // Stale (> 30 days OR un-stamped legacy entry). Prefer a fresh fetch,
    // but fall back to the stale copy when the device is offline rather
    // than serve a blank 503 (we'd rather show day-31 tiles than nothing).
    const fresh = await networkPromise;
    return fresh || cached;
  }

  const networkResponse = await networkPromise;
  if (networkResponse) return networkResponse;

  return new Response('Offline', { status: 503 });
}
