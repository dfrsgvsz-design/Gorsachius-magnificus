/**
 * Offline tile caching using Cache API.
 *
 * Stores map tiles in a browser Cache for offline use.
 * Works with both Service Workers and direct Cache API access.
 */

const TILE_CACHE_NAME = 'biodiversity-survey-tiles-v1'

function tileUrl(template, x, y, z) {
  return template
    .replace('{x}', x)
    .replace('{y}', y)
    .replace('{z}', z)
    .replace('{s}', ['a', 'b', 'c'][Math.abs(x + y) % 3])
}

function lon2tile(lon, zoom) {
  return Math.floor(((lon + 180) / 360) * Math.pow(2, zoom))
}

function lat2tile(lat, zoom) {
  return Math.floor(
    ((1 - Math.log(Math.tan((lat * Math.PI) / 180) + 1 / Math.cos((lat * Math.PI) / 180)) / Math.PI) / 2) *
    Math.pow(2, zoom)
  )
}

/**
 * Calculate tile count and storage estimate for a bounding box.
 */
export function estimateTileDownload(bounds, minZoom = 8, maxZoom = 15) {
  const { minLat, maxLat, minLon, maxLon } = bounds
  let totalTiles = 0

  for (let z = minZoom; z <= maxZoom; z++) {
    const xMin = lon2tile(minLon, z)
    const xMax = lon2tile(maxLon, z)
    const yMin = lat2tile(maxLat, z)
    const yMax = lat2tile(minLat, z)
    totalTiles += (xMax - xMin + 1) * (yMax - yMin + 1)
  }

  const avgTileKB = 25
  const estimatedMB = (totalTiles * avgTileKB) / 1024

  return {
    tileCount: totalTiles,
    estimatedMB: Math.round(estimatedMB * 10) / 10,
    minZoom,
    maxZoom,
    bounds,
  }
}

/**
 * Download and cache tiles for offline use.
 *
 * @param {Object} options
 * @param {string} options.tileTemplate - Tile URL template with {x},{y},{z},{s}
 * @param {Object} options.bounds - { minLat, maxLat, minLon, maxLon }
 * @param {number} options.minZoom
 * @param {number} options.maxZoom
 * @param {Function} options.onProgress - (downloaded, total) => void
 * @param {AbortSignal} options.signal - AbortController signal
 * @returns {Promise<{ downloaded: number, failed: number, cached: number }>}
 */
export async function downloadTiles({
  tileTemplate,
  bounds,
  minZoom = 10,
  maxZoom = 14,
  onProgress,
  signal,
}) {
  if (!('caches' in window)) {
    throw new Error('Cache API not available. Use HTTPS or localhost.')
  }

  const cache = await caches.open(TILE_CACHE_NAME)
  const { minLat, maxLat, minLon, maxLon } = bounds

  const tiles = []
  for (let z = minZoom; z <= maxZoom; z++) {
    const xMin = lon2tile(minLon, z)
    const xMax = lon2tile(maxLon, z)
    const yMin = lat2tile(maxLat, z)
    const yMax = lat2tile(minLat, z)
    for (let x = xMin; x <= xMax; x++) {
      for (let y = yMin; y <= yMax; y++) {
        tiles.push({ x, y, z })
      }
    }
  }

  let downloaded = 0
  let failed = 0
  let cached = 0
  const batchSize = 6

  for (let i = 0; i < tiles.length; i += batchSize) {
    if (signal?.aborted) break

    const batch = tiles.slice(i, i + batchSize)
    const results = await Promise.allSettled(
      batch.map(async ({ x, y, z }) => {
        const url = tileUrl(tileTemplate, x, y, z)

        const existing = await cache.match(url)
        if (existing) {
          cached++
          return
        }

        const response = await fetch(url, { signal })
        if (response.ok) {
          await cache.put(url, response)
          downloaded++
        } else {
          failed++
        }
      })
    )

    for (const r of results) {
      if (r.status === 'rejected' && r.reason?.name !== 'AbortError') {
        failed++
      }
    }

    onProgress?.(downloaded + cached, tiles.length)
  }

  return { downloaded, failed, cached, total: tiles.length }
}

/**
 * Get a cached tile or fetch from network.
 */
export async function getCachedTile(url) {
  if (!('caches' in window)) return null
  try {
    const cache = await caches.open(TILE_CACHE_NAME)
    return await cache.match(url)
  } catch {
    return null
  }
}

/**
 * Get cache statistics.
 */
export async function getTileCacheStats() {
  if (!('caches' in window)) return { available: false, count: 0 }
  try {
    const cache = await caches.open(TILE_CACHE_NAME)
    const keys = await cache.keys()
    return {
      available: true,
      count: keys.length,
      estimatedMB: Math.round((keys.length * 25) / 1024 * 10) / 10,
    }
  } catch {
    return { available: false, count: 0 }
  }
}

/**
 * Clear all cached tiles.
 */
export async function clearTileCache() {
  if (!('caches' in window)) return false
  return caches.delete(TILE_CACHE_NAME)
}

/**
 * Build bounds from a center point and radius in km.
 */
export function boundsFromCenter(lat, lon, radiusKm = 10) {
  const latDelta = radiusKm / 111
  const lonDelta = radiusKm / (111 * Math.cos((lat * Math.PI) / 180))
  return {
    minLat: lat - latDelta,
    maxLat: lat + latDelta,
    minLon: lon - lonDelta,
    maxLon: lon + lonDelta,
  }
}
