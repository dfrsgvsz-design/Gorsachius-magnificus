import React, { useEffect } from 'react'
import {
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  useMap,
} from 'react-leaflet'

/**
 * Leaflet map for field surveys showing sites, routes, tracks, and observations.
 * Extracted from FieldOpsTab.jsx lines 4457-4505.
 *
 * Props:
 *   center       — [lat, lon] map center
 *   tileUrl      — tile layer URL template
 *   attribution  — tile attribution string
 *   sites        — array of { site_id, latitude, longitude }
 *   routes       — array of { route_id, geometry: { coordinates } }
 *   tracks       — array of { track_id, geometry: { coordinates } }
 *   liveTrack    — { geometry: { coordinates } } or null
 *   observations — array of { observation_id, latitude, longitude }
 */

function MapViewport({ center }) {
  const map = useMap()
  useEffect(() => {
    if (center?.length === 2) {
      map.setView(center, map.getZoom(), { animate: false })
    }
  }, [center, map])
  return null
}

export default function FieldSurveyMap({
  center,
  tileUrl,
  attribution,
  sites,
  routes,
  observations,
  tracks,
  liveTrack,
}) {
  return (
    <div className="h-[26rem] overflow-hidden rounded-2xl border border-white/[0.06]">
      <MapContainer center={center} zoom={11} className="h-full w-full">
        <MapViewport center={center} />
        <TileLayer attribution={attribution} url={tileUrl} />
        {(sites || []).map((site) => (
          site?.latitude != null && site?.longitude != null ? (
            <CircleMarker
              key={site.site_id}
              center={[site.latitude, site.longitude]}
              radius={6}
              pathOptions={{ color: '#10b981', fillOpacity: 0.8 }}
            />
          ) : null
        ))}
        {(routes || []).map((route) => (
          <Polyline
            key={route.route_id}
            positions={(route?.geometry?.coordinates || []).map((point) => [point[1], point[0]])}
            pathOptions={{ color: '#06b6d4', weight: 4 }}
          />
        ))}
        {(tracks || []).map((track) => (
          <Polyline
            key={track.track_id}
            positions={(track?.geometry?.coordinates || []).map((point) => [point[1], point[0]])}
            pathOptions={{ color: '#f59e0b', weight: 4, dashArray: '6 6' }}
          />
        ))}
        {liveTrack?.geometry?.coordinates?.length > 1 && (
          <Polyline
            positions={liveTrack.geometry.coordinates.map((point) => [point[1], point[0]])}
            pathOptions={{ color: '#ef4444', weight: 4 }}
          />
        )}
        {(observations || []).map((record) => (
          record?.latitude != null && record?.longitude != null ? (
            <CircleMarker
              key={record.observation_id}
              center={[record.latitude, record.longitude]}
              radius={5}
              pathOptions={{ color: '#8b5cf6', fillOpacity: 0.7 }}
            />
          ) : null
        ))}
      </MapContainer>
    </div>
  )
}
