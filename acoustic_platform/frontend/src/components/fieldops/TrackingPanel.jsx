import React from 'react'
import { Activity, Square } from 'lucide-react'
import MetricCard from './MetricCard'

export default function TrackingPanel({
  copy,
  trackStatus,
  trackInfo,
  selectedRoute,
  latestTrack,
  protocolDefinition,
  hasActiveTrackDraft,
  onStartTrack,
  onStopTrack,
}) {
  return (
    <div className="section-shell space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{copy.track}</h3>
        <span className={`rounded-full border px-3 py-1 text-xs ${
          trackStatus === 'recording'
            ? 'border-red-500/30 bg-red-500/10 text-red-300'
            : trackStatus === 'paused'
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
              : 'border-white/10 bg-white/5 text-gray-300'
        }`}>
          {trackStatus}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <MetricCard title="Points" value={trackInfo.points} note="GPS" />
        <MetricCard title="Distance" value={`${Math.round(trackInfo.distance_m)} m`} note={selectedRoute?.name || 'live'} />
      </div>
      {!protocolDefinition.supportsTrack && (
        <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
          {protocolDefinition.label} does not require a live walk track. Keep using the shared station, plot, media, and record workflow.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onStartTrack}
          disabled={trackStatus === 'recording' || !selectedRoute || !protocolDefinition.supportsTrack}
          className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          <Activity className="h-4 w-4" />
          {trackStatus === 'paused' ? (copy.resumeTrack || 'Resume track') : copy.startTrack}
        </button>
        <button onClick={onStopTrack} disabled={!hasActiveTrackDraft} className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50">
          <Square className="h-4 w-4" />
          {copy.stopTrack}
        </button>
      </div>
      {latestTrack && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-gray-300">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-white">{latestTrack.name}</span>
            <span>{Math.round(latestTrack.distance_m || 0)} m</span>
          </div>
          <p className="mt-1 text-xs text-gray-500">{latestTrack.started_at}</p>
          <p className="mt-1 text-xs text-gray-500">{latestTrack.route_id || selectedRoute?.route_id || ''}</p>
        </div>
      )}
    </div>
  )
}
