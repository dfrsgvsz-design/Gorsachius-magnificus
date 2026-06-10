import React from 'react'
import { Download, Loader2, Save } from 'lucide-react'
import MetricCard from './MetricCard'
import {
  EXPORT_JURISDICTIONS,
  formatPreviewKey,
  formatPreviewValue,
  toArray,
} from './fieldOpsUtils'

/**
 * Protocol export bundle panel.
 * Extracted from FieldOpsTab.jsx lines 4312-4455.
 */
export default function ProtocolExportPanel({
  protocolDefinition,
  exportJurisdiction,
  locale = 'zh',
  onChangeJurisdiction,
  taxonomyPackage,
  taxonomyPackageNote,
  taxonomyGateByJurisdiction,
  observationCount,
  trackCount,
  latestProtocolEvent,
  latestProtocolExportJob,
  savingEvent,
  exportingJurisdiction,
  isOnline,
  onSaveEvent,
  onExport,
}) {
  const isZh = locale === 'zh'
  const exportFiles = toArray(latestProtocolExportJob?.bundle?.files)
  const exportSummary = latestProtocolExportJob?.summary || {}
  const selectedTaxonomyGateBlocked = Boolean(taxonomyGateByJurisdiction?.[exportJurisdiction]?.isBlocked)

  return (
    <div className="space-y-4 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-[15px] font-semibold text-white">{isZh ? '协议导出数据包' : 'Protocol export bundle'}</h3>
          <p className="mt-1 text-[12px] text-white/30">
            {isZh ? '保存当前事件上下文，然后导出特定管辖区的 CSV 和 JSON 数据包。' : 'Save the active event context, then export jurisdiction-specific CSV and JSON bundle files for this protocol.'}
          </p>
        </div>
        <label className="space-y-1">
          <span className="block text-[12px] text-white/30">{isZh ? '导出管辖区' : 'Export jurisdiction'}</span>
          <select
            value={exportJurisdiction}
            onChange={(event) => onChangeJurisdiction(event.target.value)}
            className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white focus:border-[#0A84FF]/40 focus:outline-none"
          >
            {EXPORT_JURISDICTIONS.map((option) => (
              <option key={option.id} value={option.id}>{isZh ? (option.label_zh || option.label) : option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <MetricCard title={isZh ? '观测记录' : 'Observations'} value={observationCount} note={protocolDefinition.label_zh || protocolDefinition.label} />
        <MetricCard
          title={isZh ? '轨迹' : 'Tracks'}
          value={trackCount}
          note={protocolDefinition.supportsTrack ? (isZh ? '路线型努力量' : 'Route-based effort') : (isZh ? '无需实时轨迹' : 'No live track required')}
        />
        <MetricCard
          title={isZh ? '分类包' : 'Taxonomy package'}
          value={taxonomyPackage?.label || (isZh ? '等待同步' : 'Pending sync')}
          note={taxonomyPackageNote}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onSaveEvent({ quiet: false })}
          disabled={savingEvent}
          className="inline-flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 transition-colors active:bg-white/[0.08] disabled:opacity-40"
        >
          {savingEvent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {isZh ? '保存事件' : 'Save event'}
        </button>
        {EXPORT_JURISDICTIONS.map((option) => (
          <button
            key={option.id}
            onClick={() => onExport(option.id)}
            disabled={!isOnline || exportingJurisdiction !== '' || taxonomyGateByJurisdiction?.[option.id]?.isBlocked}
            className={`inline-flex items-center gap-2 rounded-[12px] px-4 py-[11px] text-[14px] font-medium text-white transition-colors disabled:opacity-40 ${
              exportJurisdiction === option.id ? 'bg-[#0A84FF] active:bg-[#0A84FF]/80' : 'bg-[#30D158] active:bg-[#30D158]/80'
            }`}
          >
            {exportingJurisdiction === option.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {isZh ? (option.label_zh || option.label) : option.label}
          </button>
        ))}
      </div>

      {selectedTaxonomyGateBlocked && (
        <p className="rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
          {isZh ? '请先解决分类版本和校验问题，然后再导出此协议数据包。' : 'Resolve the taxonomy release and checksum gate before exporting this protocol bundle.'}
        </p>
      )}

      {!isOnline && (
        <p className="rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
          {isZh ? '请重新连接网络以生成导出数据包。事件草稿和观测仍可离线排队。' : 'Reconnect to generate the export bundle. Event drafts and observations can still be queued offline.'}
        </p>
      )}

      <div className="grid grid-cols-3 gap-3">
        <MetricCard
          title={isZh ? '事件' : 'Event'}
          value={latestProtocolEvent ? (isZh ? '已保存' : 'Saved') : (isZh ? '仅草稿' : 'Draft only')}
          note={latestProtocolEvent?.started_at || (isZh ? '导出前请先保存一次事件上下文' : 'Save once before export to pin the event context')}
        />
        <MetricCard
          title={isZh ? '数据包状态' : 'Bundle status'}
          value={latestProtocolExportJob?.status || (isZh ? '未导出' : 'Not exported')}
          note={latestProtocolExportJob?.updated_at || latestProtocolExportJob?.created_at || (isZh ? '暂无导出任务' : 'No export job yet')}
        />
        <MetricCard
          title={isZh ? '数据包文件' : 'Bundle files'}
          value={exportFiles.length}
          note={latestProtocolExportJob?.jurisdiction || exportJurisdiction}
        />
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{isZh ? '最新导出摘要' : 'Latest export summary'}</p>
        {Object.keys(exportSummary).length === 0 ? (
          <p className="mt-2 text-[13px] text-white/25">{isZh ? '此协议和管辖区尚未生成导出数据包。' : 'No export bundle has been generated for this protocol and jurisdiction yet.'}</p>
        ) : (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.entries(exportSummary).map(([key, value]) => (
              <div key={key} className="rounded-[12px] border border-white/[0.06] bg-white/[0.03] px-3 py-2">
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/25">{formatPreviewKey(key)}</p>
                <p className="mt-1 text-[14px] text-white">{formatPreviewValue(value)}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {exportFiles.length > 0 && (
        <div className="rounded-2xl border border-white/[0.06]">
          <div className="px-4 pb-1 pt-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{isZh ? '数据包文件' : 'Bundle files'}</p>
          </div>
          {exportFiles.map((file, idx) => (
            <div key={file.filename || file.output_id} className={`flex items-center justify-between gap-3 px-4 py-[10px] ${idx < exportFiles.length - 1 ? 'border-b border-white/[0.04]' : ''}`}>
              <span className="truncate text-[14px] text-white">{file.filename || file.output_id || 'export-file'}</span>
              <span className="shrink-0 text-[12px] text-white/30">{file.media_type || 'text/csv'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
