import React, { useEffect, useMemo } from 'react'
import L from 'leaflet'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  TileLayer,
  useMap,
} from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

/**
 * Leaflet map for field surveys showing sites, routes, tracks, observations,
 * and the surveyor's live position. Sites and observations are clustered to
 * stay legible at low zoom; the live position is rendered as a blue dot with
 * an accuracy ring to mirror the iOS / Google Maps "current location" idiom.
 *
 * Props:
 *   center        — [lat, lon] map center
 *   tileUrl       — tile layer URL template
 *   attribution   — tile attribution string
 *   sites         — array of { site_id, latitude, longitude }
 *   routes        — array of { route_id, geometry: { coordinates } }
 *   tracks        — array of { track_id, geometry: { coordinates } }
 *   liveTrack     — { geometry: { coordinates } } or null
 *   observations  — array of { observation_id, latitude, longitude }
 *   userPosition  — { lat, lon, accuracy? } or null
 *   onLocateUser  — optional callback when the user clicks the blue dot
 */

function createDotIcon(fill, diameter, ring = 'rgba(0,0,0,0.35)') {
  const radius = diameter / 2
  return L.divIcon({
    className: 'field-map-dot',
    html: `<span style="display:block;width:${diameter}px;height:${diameter}px;border-radius:50%;background:${fill};box-shadow:0 0 0 2px ${ring};"></span>`,
    iconSize: [diameter, diameter],
    iconAnchor: [radius, radius],
  })
}

const SITE_ICON = createDotIcon('#10b981', 14)
const OBSERVATION_ICON = createDotIcon('#8b5cf6', 12)

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
  userPosition = null,
  onLocateUser,
}) {
  const siteMarkers = useMemo(
    () =>
      (sites || [])
        .filter((site) => site?.latitude != null && site?.longitude != null)
        .map((site) => (
          <Marker
            key={`site-${site.site_id}`}
            position={[site.latitude, site.longitude]}
            icon={SITE_ICON}
          />
        )),
    [sites],
  )

  const observationMarkers = useMemo(
    () =>
      (observations || [])
        .filter((record) => record?.latitude != null && record?.longitude != null)
        .map((record) => (
          <Marker
            key={`obs-${record.observation_id}`}
            position={[record.latitude, record.longitude]}
            icon={OBSERVATION_ICON}
          />
        )),
    [observations],
  )

  return (
    <div className="h-[26rem] overflow-hidden rounded-2xl border border-white/[0.06]">
      <MapContainer center={center} zoom={11} className="h-full w-full">
        <MapViewport center={center} />
        <TileLayer attribution={attribution} url={tileUrl} />

        {(siteMarkers.length > 0 || observationMarkers.length > 0) && (
          <MarkerClusterGroup
            chunkedLoading
            showCoverageOnHover={false}
            spiderfyOnMaxZoom
            removeOutsideVisibleBounds
            maxClusterRadius={48}
          >
            {siteMarkers}
            {observationMarkers}
          </MarkerClusterGroup>
        )}

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

        {userPosition?.lat != null && userPosition?.lon != null && (
          <>
            {Number.isFinite(userPosition.accuracy) && userPosition.accuracy > 0 && (
              <Circle
                center={[userPosition.lat, userPosition.lon]}
                radius={userPosition.accuracy}
                pathOptions={{
                  color: '#0A84FF',
                  fillColor: '#0A84FF',
                  fillOpacity: 0.1,
                  weight: 1,
                  opacity: 0.45,
                }}
                interactive={false}
              />
            )}
            <CircleMarker
              center={[userPosition.lat, userPosition.lon]}
              radius={7}
              pathOptions={{
                color: '#FFFFFF',
                fillColor: '#0A84FF',
                fillOpacity: 1,
                weight: 2,
              }}
              eventHandlers={onLocateUser ? { click: () => onLocateUser(userPosition) } : undefined}
            />
          </>
        )}
      </MapContainer>
    </div>
  )
}
