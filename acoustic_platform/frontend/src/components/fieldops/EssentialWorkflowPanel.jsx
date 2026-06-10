import React from 'react'
import { Activity, Save, Square } from 'lucide-react'
import MetricCard from './MetricCard'
import FieldSurveyMap from './FieldSurveyMap'
import { getSpeciesDisplayName } from './helpers'

export default function EssentialWorkflowPanel({
  copy,
  mapCenter,
  tileUrl,
  tileAttribution,
  projectSites,
  selectedRoute,
  siteRoutes,
  routeObservations,
  routeTracks,
  liveTrack,
  trackInfo,
  trackStatus,
  protocolDefinition,
  hasActiveTrackDraft,
  currentProjectId,
  onStartTrack,
  onStopTrack,
  onSaveObservation,
}) {
  return (
    <section className="section-shell space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">Essential field workflow</h3>
          <p className="mt-1 text-xs text-gray-400">
            Map, track, and records are available here directly for fast field use.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onStartTrack}
            disabled={trackStatus === 'recording' || !selectedRoute || !protocolDefinition.supportsTrack}
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            <Activity className="h-4 w-4" />
            {trackStatus === 'paused' ? (copy.resumeTrack || 'Resume track') : copy.startTrack}
          </button>
          <button
            onClick={onStopTrack}
            disabled={!hasActiveTrackDraft}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            <Square className="h-4 w-4" />
            {copy.stopTrack}
          </button>
          <button
            onClick={onSaveObservation}
            disabled={!currentProjectId || (protocolDefinition.requiresAsset && !selectedRoute)}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {copy.saveObservation}
          </button>
        </div>
      </div>
      <FieldSurveyMap
        center={mapCenter}
        tileUrl={tileUrl}
        attribution={tileAttribution}
        sites={projectSites}
        routes={selectedRoute ? [selectedRoute] : siteRoutes}
        observations={routeObservations}
        tracks={routeTracks}
        liveTrack={liveTrack}
      />
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard title="Track points" value={trackInfo.points} note={trackStatus} />
        <MetricCard title="Walked distance" value={`${Math.round(trackInfo.distance_m || 0)} m`} note={selectedRoute?.name || 'live'} />
        <MetricCard title="Saved records" value={routeObservations.length} note={protocolDefinition.label} />
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Latest records</p>
        {routeObservations.length === 0 ? (
          <p className="mt-2 text-sm text-gray-400">No records yet. Save one observation to start the list.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {routeObservations.slice(0, 5).map((record) => (
              <div key={record.observation_id || record.local_id} className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm">
                <span className="truncate text-white">{getSpeciesDisplayName(record) || 'Unknown taxon'}</span>
                <span className="text-xs text-gray-400">{record.observed_at || '--'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
