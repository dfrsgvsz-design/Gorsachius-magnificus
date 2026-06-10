import React from 'react'
import { Download, Loader2 } from 'lucide-react'
import MetricCard from './MetricCard'
import {
  toArray,
  formatReportDescriptor,
  getSpeciesDisplayName,
  getSpeciesSecondaryName,
} from './fieldOpsUtils'

/**
 * Route/station report panel with species list and export buttons.
 * Extracted from FieldOpsTab.jsx lines 3881-4055.
 */
export default function RouteReportPanel({
  copy,
  locale = 'zh',
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
  const isZh = locale === 'zh'
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
  const observerSummary = formatReportDescriptor(routeReport?.observers, copy.noObservers || (isZh ? '未列出观察者' : 'No observers listed'))
  const weatherSummary = formatReportDescriptor(routeReport?.weather, copy.noWeather || (isZh ? '未填写天气摘要' : 'No weather summary'))

  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-[15px] font-semibold text-white">{copy.transectReport || (isZh ? '路线/站点报告' : 'Route or station report')}</h3>
          <p className="text-[12px] text-white/30">
            {selectedRoute?.name || copy.selectTransectHint || (isZh ? '请选择路线、站点或样方以加载汇总信息。' : 'Select a route, station, or plot asset to load its summary.')}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <button
            onClick={() => onExport('json')}
            disabled={!selectedRoute || !isOnline || exportingFormat !== '' || taxonomyGateBlocked}
            className="inline-flex items-center justify-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 transition-colors active:bg-white/[0.08] disabled:opacity-40"
          >
            {exportingFormat === 'json' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            JSON
          </button>
          <button
            onClick={() => onExport('csv')}
            disabled={!selectedRoute || !isOnline || exportingFormat !== '' || taxonomyGateBlocked}
            className="inline-flex items-center justify-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 transition-colors active:bg-white/[0.08] disabled:opacity-40"
          >
            {exportingFormat === 'csv' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            CSV
          </button>
        </div>
      </div>

      {!selectedRoute && (
        <div className="rounded-[12px] bg-white/[0.04] px-4 py-3 text-[14px] text-white/40">
          {copy.selectTransectHint || (isZh ? '请选择路线、站点或样方以加载汇总信息。' : 'Select a route, station, or plot asset to load its summary.')}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'offline' && (
        <div className="rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
          {copy.reportOfflineHint || (isZh ? '请重新连接网络以加载最新路线/站点汇总并启用报告导出。' : 'Reconnect to load the latest route or station summary and enable report exports.')}
        </div>
      )}

      {selectedRoute && taxonomyGateBlocked && (
        <div className="rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
          {taxonomyGateMessage || (isZh ? '请先解决分类版本和校验问题，然后再导出此报告。' : 'Resolve the taxonomy release and checksum gate before exporting this route or station report.')}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'loading' && (
        <div className="flex items-center gap-2 rounded-[12px] bg-[#0A84FF]/10 px-4 py-2.5 text-[13px] text-[#0A84FF]">
          <Loader2 className="h-4 w-4 animate-spin" />
          {copy.loadingReport || (isZh ? '正在加载路线/站点汇总……' : 'Loading route or station summary...')}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'error' && (
        <div className="rounded-[12px] bg-[#FF453A]/10 px-4 py-2.5 text-[13px] text-[#FF453A]">
          {routeReportError}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'ready' && !routeReport && (
        <div className="rounded-[12px] bg-white/[0.04] px-4 py-3 text-[14px] text-white/40">
          {copy.emptyReportSummary || (isZh ? '服务器尚未返回此选择的路线/站点汇总。' : 'The server did not return a route or station summary for this selection yet.')}
        </div>
      )}

      {selectedRoute && routeReportStatus === 'ready' && routeReport && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              title={copy.recordsOnTransect || (isZh ? '观测记录' : 'Observations')}
              value={observationCount}
              note={`${speciesCount} ${copy.speciesLabel || (isZh ? '种' : 'species')}`}
            />
            <MetricCard
              title={copy.track || (isZh ? '轨迹' : 'Tracks')}
              value={trackCount}
              note={`${observerCount} ${copy.observer || (isZh ? '观察者' : 'observers')}`}
            />
            <MetricCard
              title={copy.routeLength || (isZh ? '路线长度' : 'Route length')}
              value={`${routeLengthMeters} m`}
              note={routeReport?.route?.route_type || selectedRoute?.route_type || (isZh ? '路线' : 'route')}
            />
            <MetricCard
              title={copy.effort || (isZh ? '努力量' : 'Effort')}
              value={effortMinutes != null ? `${effortMinutes} min` : '--'}
              note={copy.serverSummary || (isZh ? '服务器汇总' : 'server summary')}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{copy.observer || (isZh ? '观察者' : 'Observer')}</p>
              <p className="mt-1 text-[15px] text-white">{observerSummary}</p>
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{copy.weather || (isZh ? '天气' : 'Weather')}</p>
              <p className="mt-1 text-[15px] text-white">{weatherSummary}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-white/[0.06]">
            <div className="flex items-center justify-between px-4 py-2.5 text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">
              <span>{copy.speciesList || (isZh ? '物种' : 'Species')}</span>
              <span>{copy.recordsOnTransect || (isZh ? '记录' : 'Records')}</span>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {speciesRows.length === 0 ? (
                <p className="px-4 py-4 text-[13px] text-white/25">{copy.noSpeciesRows || (isZh ? '报告中尚无物种数据。' : 'No species rows in this report yet.')}</p>
              ) : (
                speciesRows.slice(0, 8).map((item, index) => {
                  const primaryName = getSpeciesDisplayName(item)
                  const secondaryName = getSpeciesSecondaryName(item)
                  const recordCount = item.count ?? item.observation_count ?? item.observations ?? 0
                  const individualCount = item.individual_count ?? item.total_count ?? item.total_individuals

                  return (
                    <div key={`${primaryName}-${index}`} className={`grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 ${index < Math.min(speciesRows.length, 8) - 1 ? 'border-b border-white/[0.04]' : ''}`}>
                      <div className="min-w-0">
                        <p className="truncate text-[14px] font-medium text-white">{primaryName}</p>
                        <p className="truncate text-[12px] text-white/25">
                          {secondaryName || selectedRoute?.name || (copy.transect || (isZh ? '路线/站点' : 'route or station asset'))}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-[15px] font-semibold text-white">{recordCount}</p>
                        <p className="text-[11px] text-white/20">
                          {individualCount != null ? `${individualCount} ${copy.count || (isZh ? '只' : 'count')}` : copy.recordsOnTransect || (isZh ? '条记录' : 'records')}
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
