import React from 'react'
import { Download, Loader2 } from 'lucide-react'
import MetricCard from './MetricCard'
import {
  toArray,
  formatReportDescriptor,
  getSpeciesDisplayName,
  getSpeciesSecondaryName,
} from './helpers'

export default function RouteReportPanel({
  copy,
  selectedRoute,
  routeReport,
  routeReportError,
  routeReportStatus,
  isOnline,
  exportingFormat,
  taxonomyGateBlocked,
  taxonomyGateMessage,
  onExport,
}) {
  const totals = routeReport?.totals || {}
  const speciesRows = [...toArray(routeReport?.species)].sort((left, right) => {
    const leftScore = Number(left?.count ?? left?.observation_count ?? left?.observations ?? 0)
    const rightScore = Number(right?.count ?? right?.observation_count ?? right?.observations ?? 0)
    return rightScore - leftScore
  })
  const observationCount = totals.observation_count ?? totals.observations ?? toArray(routeReport?.observations).length
  const speciesCount = totals.species_count ?? totals.species ?? speciesRows.length
  const trackCount = totals.track_count ?? totals.tracks ?? toArray(routeReport?.tracks).length
  const observerCount = totals.observer_count ?? totals.observers ?? toArray(routeReport?.observers).length
  const routeLengthMeters = Math.round(Number(
    totals.distance_m
      ?? totals.route_length_m
      ?? routeReport?.route?.length_m
      ?? selectedRoute?.length_m
      ?? 0,
  ))
  const effortMinutes = totals.effort_minutes ?? totals.duration_minutes ?? totals.duration_min ?? null
  const observerSummary = formatReportDescriptor(routeReport?.observers, copy.noObservers || 'No observers listed')
  const weatherSummary = formatReportDescriptor(routeReport?.weather, copy.noWeather || 'No weather summary')

  return (
    <div className="section-shell space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">{copy.transectReport || 'Route or station report'}</h3>
          <p className="text-xs text-gray-500">
            {selectedRoute?.name || copy.selectTransectHint || 'Select a route, station, or plot asset to load its summary.'}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <button
            onClick={() => onExport('json')}
            disabled={!selectedRoute || !isOnline || exportingFormat !== '' || taxonomyGateBlocked}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            {exportingFormat === 'json' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            JSON
          </button>
          <button
            onClick={() => onExport('csv')}
            disabled={!selectedRoute || !isOnline || exportingFormat !== '' || taxonomyGateBlocked}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            {exportingFormat === 'csv' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            CSV
          </button>
        </div>
      </div>

      {!selectedRoute && (
        <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-sm text-gray-300">
          {copy.selectTransectHint || 'Select a route, station, or plot asset to load its summary.'}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'offline' && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-3 text-sm text-amber-100">
          {copy.reportOfflineHint || 'Reconnect to load the latest route or station summary and enable report exports.'}
        </div>
      )}

      {selectedRoute && taxonomyGateBlocked && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-3 text-sm text-amber-100">
          {taxonomyGateMessage || 'Resolve the taxonomy release and checksum gate before exporting this route or station report.'}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'loading' && (
        <div className="flex items-center gap-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-3 text-sm text-cyan-100">
          <Loader2 className="h-4 w-4 animate-spin" />
          {copy.loadingReport || 'Loading route or station summary...'}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'error' && (
        <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 px-3 py-3 text-sm text-rose-100">
          {routeReportError}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'ready' && !routeReport && (
        <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-sm text-gray-300">
          {copy.emptyReportSummary || 'The server did not return a route or station summary for this selection yet.'}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'ready' && routeReport && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              title={copy.recordsOnTransect || 'Observations'}
              value={observationCount}
              note={`${speciesCount} ${copy.speciesLabel || 'species'}`}
            />
            <MetricCard
              title={copy.track || 'Tracks'}
              value={trackCount}
              note={`${observerCount} ${copy.observer || 'observers'}`}
            />
            <MetricCard
              title={copy.routeLength || 'Route length'}
              value={`${routeLengthMeters} m`}
              note={routeReport?.route?.route_type || selectedRoute?.route_type || 'route'}
            />
            <MetricCard
              title={copy.effort || 'Effort'}
              value={effortMinutes != null ? `${effortMinutes} min` : '--'}
              note={copy.serverSummary || 'server summary'}
            />
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-sm text-gray-300">
              <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{copy.observer || 'Observer'}</p>
              <p className="mt-1 text-white">{observerSummary}</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-sm text-gray-300">
              <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{copy.weather || 'Weather'}</p>
              <p className="mt-1 text-white">{weatherSummary}</p>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/5">
            <div className="flex items-center justify-between border-b border-white/10 px-3 py-2 text-xs uppercase tracking-[0.2em] text-gray-500">
              <span>{copy.speciesList || 'Species'}</span>
              <span>{copy.recordsOnTransect || 'Records'}</span>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {speciesRows.length === 0 ? (
                <p className="px-3 py-3 text-sm text-gray-400">{copy.noSpeciesRows || 'No species rows in this report yet.'}</p>
              ) : (
                speciesRows.slice(0, 8).map((item, index) => {
                  const primaryName = getSpeciesDisplayName(item)
                  const secondaryName = getSpeciesSecondaryName(item)
                  const recordCount = item.count ?? item.observation_count ?? item.observations ?? 0
                  const individualCount = item.individual_count ?? item.total_count ?? item.total_individuals

                  return (
                    <div key={`${primaryName}-${index}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-white/5 px-3 py-3 last:border-b-0">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{primaryName}</p>
                        <p className="truncate text-xs text-gray-500">
                          {secondaryName || selectedRoute?.name || (copy.transect || 'route or station asset')}
                        </p>
                      </div>
                      <div className="text-right text-sm text-gray-200">
                        <p>{recordCount}</p>
                        <p className="text-xs text-gray-500">
                          {individualCount != null ? `${individualCount} ${copy.count || 'count'}` : copy.recordsOnTransect || 'records'}
                        </p>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
