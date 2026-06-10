import React from 'react'
import { Activity, Square } from 'lucide-react'
import MetricCard from './MetricCard'

/**
 * Track recording controls with status, metrics, and start/stop buttons.
 * Extracted from FieldOpsTab.jsx lines 3545-3592.
 */
export default function TrackPanel({
  copy,
  trackStatus,
  trackInfo,
  selectedRoute,
  protocolDefinition,
  hasActiveTrackDraft,
  latestTrack,
  onStart,
  onStop,
  locale = 'zh',
}) {
  const isZh = locale === 'zh'
  const statusColor = trackStatus === 'recording'
    ? 'bg-[#FF453A]/15 text-[#FF453A]'
    : trackStatus === 'paused'
      ? 'bg-[#FF9F0A]/15 text-[#FF9F0A]'
      : 'bg-white/[0.06] text-white/40'
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-white">{copy.track}</h3>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-medium ${statusColor}`}>
          {trackStatus === 'recording' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#FF453A]" />}
          {trackStatus === 'recording' ? (isZh ? '录制中' : 'REC') : trackStatus === 'paused' ? (isZh ? '暂停' : 'Paused') : (isZh ? '待机' : 'Idle')}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <MetricCard title={isZh ? '轨迹点' : 'Points'} value={trackInfo.points} note="GPS" />
        <MetricCard title={isZh ? '距离' : 'Distance'} value={`${Math.round(trackInfo.distance_m)} m`} note={selectedRoute?.name || (isZh ? '实时' : 'live')} />
      </div>
      {!protocolDefinition.supportsTrack && (
        <p className="rounded-[12px] bg-[#FF9F0A]/10 px-3 py-2.5 text-[13px] text-[#FF9F0A]">
          {isZh ? `${protocolDefinition.label_zh || protocolDefinition.label} 不需要实时行走轨迹。请继续使用站点/样方、媒体和记录工作流。` : `${protocolDefinition.label} does not require a live walk track. Keep using the shared station, plot, media, and record workflow.`}
        </p>
      )}
      <div className="flex gap-2">
        <button
          onClick={onStart}
          disabled={trackStatus === 'recording' || !protocolDefinition.supportsTrack}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-[#0A84FF] px-3 py-[11px] text-[15px] font-medium text-white transition-colors active:bg-[#0A84FF]/80 disabled:opacity-40"
        >
          <Activity className="h-4 w-4" />
          {trackStatus === 'paused' ? (copy.resumeTrack || 'Resume track') : copy.startTrack}
        </button>
        <button
          onClick={onStop}
          disabled={!hasActiveTrackDraft}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-[#FF453A]/15 px-3 py-[11px] text-[15px] font-medium text-[#FF453A] transition-colors active:bg-[#FF453A]/25 disabled:opacity-40"
        >
          <Square className="h-4 w-4" />
          {copy.stopTrack}
        </button>
      </div>
      {latestTrack && (
        <div className="rounded-[12px] border border-white/[0.06] bg-white/[0.03] px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[15px] font-medium text-white">{latestTrack.name}</span>
            <span className="text-[13px] text-white/40">{Math.round(latestTrack.distance_m || 0)} m</span>
          </div>
          <p className="mt-1 text-[12px] text-white/25">{latestTrack.started_at}</p>
        </div>
      )}
    </div>
  )
}
