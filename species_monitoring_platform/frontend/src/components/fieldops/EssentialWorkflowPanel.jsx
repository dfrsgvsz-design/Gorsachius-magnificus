import React from 'react'
import { Activity, Save, Square } from 'lucide-react'
import MetricCard from './MetricCard'
import FieldSurveyMap from './FieldSurveyMap'
import { getSpeciesDisplayName } from './fieldOpsUtils'

/**
 * Essential field workflow: quick-access map, track controls, metrics, and latest records.
 * Extracted from FieldOpsTab.jsx lines 2927-2992.
 */
export default function EssentialWorkflowPanel({
  copy,
  trackStatus,
  trackInfo,
  protocolDefinition,
  locale = 'zh',
  selectedRoute,
  currentProjectId,
  hasActiveTrackDraft,
  mapCenter,
  tileUrl,
  tileAttribution,
  projectSites,
  siteRoutes,
  routeObservations,
  routeTracks,
  liveTrack,
  userPosition = null,
  onStartTrack,
  onStopTrack,
  onSaveObservation,
}) {
  const isZh = locale === 'zh'
  return (
    <section className="space-y-4">
      {/* iOS 操作按钮栏 */}
      <div className="flex gap-2">
        <button
          onClick={onStartTrack}
          disabled={trackStatus === 'recording' || !protocolDefinition.supportsTrack}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-[#0A84FF] px-3 py-[11px] text-[15px] font-medium text-white transition-colors active:bg-[#0A84FF]/80 disabled:opacity-40"
        >
          <Activity className="h-4 w-4" />
          {trackStatus === 'paused' ? (copy.resumeTrack || 'Resume track') : copy.startTrack}
        </button>
        <button
          onClick={onStopTrack}
          disabled={!hasActiveTrackDraft}
          className="inline-flex items-center justify-center gap-2 rounded-[12px] bg-[#FF453A]/15 px-4 py-[11px] text-[15px] font-medium text-[#FF453A] transition-colors active:bg-[#FF453A]/25 disabled:opacity-40"
        >
          <Square className="h-4 w-4" />
          {copy.stopTrack}
        </button>
        <button
          onClick={onSaveObservation}
          disabled={!currentProjectId || (protocolDefinition.requiresAsset && !selectedRoute)}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-[#30D158] px-3 py-[11px] text-[15px] font-medium text-white transition-colors active:bg-[#30D158]/80 disabled:opacity-40"
        >
          <Save className="h-4 w-4" />
          {copy.saveObservation}
        </button>
      </div>

      {/* 地图 */}
      <div className="overflow-hidden rounded-2xl border border-white/[0.06]">
        <FieldSurveyMap
          center={mapCenter}
          tileUrl={tileUrl}
          attribution={tileAttribution}
          sites={projectSites}
          routes={selectedRoute ? [selectedRoute] : siteRoutes}
          observations={routeObservations}
          tracks={routeTracks}
          liveTrack={liveTrack}
          userPosition={userPosition}
        />
      </div>

      {/* iOS Grouped Inset 指标卡 */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard title={isZh ? '轨迹点' : 'Track points'} value={trackInfo.points} note={trackStatus} />
        <MetricCard title={isZh ? '行走距离' : 'Walked'} value={`${Math.round(trackInfo.distance_m || 0)} m`} note={selectedRoute?.name || (isZh ? '实时' : 'live')} />
        <MetricCard title={isZh ? '记录' : 'Records'} value={routeObservations.length} note={protocolDefinition.label_zh || protocolDefinition.label} />
      </div>

      {/* 最近记录 — iOS Grouped Inset List */}
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        <div className="px-4 pb-1 pt-3">
          <p className="text-[13px] font-medium text-white/40">{isZh ? '最近记录' : 'Latest records'}</p>
        </div>
        {routeObservations.length === 0 ? (
          <p className="px-4 pb-4 pt-2 text-[15px] text-white/30">{isZh ? '暂无记录。保存观测即可开始。' : 'No records yet. Save an observation to start.'}</p>
        ) : (
          <div>
            {routeObservations.slice(0, 5).map((record, idx) => (
              <div
                key={record.observation_id || record.local_id}
                className={`flex items-center justify-between gap-3 px-4 py-[12px] ${idx < Math.min(routeObservations.length, 5) - 1 ? 'border-b border-white/[0.04]' : ''}`}
              >
                <span className="truncate text-[15px] text-white">{getSpeciesDisplayName(record) || (isZh ? '未知类群' : 'Unknown taxon')}</span>
                <span className="shrink-0 text-[13px] text-white/30">{record.observed_at || '--'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
