import React from 'react'
import { Download, Loader2, Save } from 'lucide-react'
import MetricCard from './MetricCard'
import {
  EXPORT_JURISDICTIONS,
  buildPreviewEntries,
  formatPreviewKey,
  formatPreviewValue,
  getSpeciesDisplayName,
  toArray,
} from './fieldOpsUtils'

/**
 * Terrestrial vertebrate review panel with masking preview and export.
 * Extracted from FieldOpsTab.jsx lines 4057-4300.
 */
export default function VertebrateReviewPanel({
  protocolDefinition,
  exportJurisdiction,
  locale = 'zh',
  onChangeJurisdiction,
  eventValidationMissing,
  recordValidationMissing,
  eventPayloadDraft,
  currentRecordPayloadDraft,
  currentMatchedSpecies,
  currentRecordMaskPreview,
  recentVertebrateRecordPreviews,
  maskedPreviewCount,
  latestProtocolEvent,
  latestProtocolExportJob,
  vertebrateExportResult,
  taxonomyGateByJurisdiction,
  savingReviewEvent,
  exportingVertebrateJurisdiction,
  isOnline,
  onSaveReview,
  onExport,
}) {
  const isZh = locale === 'zh'
  const eventEntries = buildPreviewEntries(eventPayloadDraft)
  const recordEntries = buildPreviewEntries(currentRecordPayloadDraft)
  const exportState = vertebrateExportResult?.exportJob || latestProtocolExportJob || null
  const exportSummary = vertebrateExportResult?.summary || exportState?.summary || {}
  const exportFiles = toArray(exportState?.bundle?.files)
  const primarySpeciesName = getSpeciesDisplayName(currentMatchedSpecies || {})
  const selectedTaxonomyGateBlocked = Boolean(taxonomyGateByJurisdiction?.[exportJurisdiction]?.isBlocked)

  return (
    <div className="space-y-4 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-[15px] font-semibold text-white">{isZh ? '陆生脊椎动物审核' : 'Terrestrial vertebrate review'}</h3>
          <p className="mt-1 text-[12px] text-white/30">
            {isZh ? '保存协议事件预览，检查掩码，然后导出特定管辖区的数据包。' : 'Save one protocol event preview, check masking, then export a jurisdiction-specific bundle.'}
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

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard
          title={isZh ? '事件状态' : 'Event status'}
          value={eventValidationMissing.length === 0 ? (isZh ? '就绪' : 'Ready') : (isZh ? '缺少字段' : 'Needs fields')}
          note={eventValidationMissing.length === 0 ? (protocolDefinition.label_zh || protocolDefinition.label) : eventValidationMissing.join(', ')}
        />
        <MetricCard
          title={isZh ? '记录状态' : 'Record status'}
          value={recordValidationMissing.length === 0 ? (isZh ? '就绪' : 'Ready') : (isZh ? '缺少字段' : 'Needs fields')}
          note={recordValidationMissing.length === 0 ? (primarySpeciesName || (isZh ? '当前草稿' : 'Current draft')) : recordValidationMissing.join(', ')}
        />
        <MetricCard
          title={isZh ? '掩码预览' : 'Mask preview'}
          value={currentRecordMaskPreview.label}
          note={isZh ? `${maskedPreviewCount}/${recentVertebrateRecordPreviews.length} 条记录已掩码` : `${maskedPreviewCount}/${recentVertebrateRecordPreviews.length} recent records masked`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{isZh ? '事件载荷' : 'Event payload'}</p>
              <p className="mt-1 text-[15px] text-white">{protocolDefinition.label_zh || protocolDefinition.label}</p>
            </div>
            {latestProtocolEvent && (
              <span className="rounded-full bg-[#30D158]/15 px-3 py-1 text-[11px] font-medium text-[#30D158]">
                {isZh ? '已保存' : 'Saved'} {latestProtocolEvent.started_at ? new Date(latestProtocolEvent.started_at).toLocaleString() : (isZh ? '草稿' : 'draft')}
              </span>
            )}
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {eventEntries.length === 0 ? (
              <p className="text-[13px] text-white/25">{isZh ? '尚未填写协议事件字段。' : 'No protocol event fields entered yet.'}</p>
            ) : (
              eventEntries.map(([key, value]) => (
                <div key={key} className="rounded-[12px] border border-white/[0.06] bg-white/[0.03] px-3 py-2">
                  <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/25">{formatPreviewKey(key)}</p>
                  <p className="mt-1 text-[14px] text-white">{formatPreviewValue(value)}</p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{isZh ? '记录载荷' : 'Record payload'}</p>
              <p className="mt-1 text-[15px] text-white">{primarySpeciesName || (isZh ? '当前观测草稿' : 'Current observation draft')}</p>
            </div>
            <span className={`rounded-full px-3 py-1 text-[11px] font-medium ${currentRecordMaskPreview.masked ? 'bg-[#FF9F0A]/15 text-[#FF9F0A]' : 'bg-[#0A84FF]/15 text-[#0A84FF]'}`}>
              {currentRecordMaskPreview.label}
            </span>
          </div>
          <p className="mt-2 text-[12px] text-white/30">{currentRecordMaskPreview.note}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {recordEntries.length === 0 ? (
              <p className="text-[13px] text-white/25">{isZh ? '尚未填写协议记录字段。' : 'No protocol record fields entered yet.'}</p>
            ) : (
              recordEntries.map(([key, value]) => (
                <div key={key} className="rounded-[12px] border border-white/[0.06] bg-white/[0.03] px-3 py-2">
                  <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/25">{formatPreviewKey(key)}</p>
                  <p className="mt-1 text-[14px] text-white">{formatPreviewValue(value)}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-[15px] font-semibold text-white">{isZh ? '近期掩码预览' : 'Recent masking preview'}</h4>
            <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">{recentVertebrateRecordPreviews.length} {isZh ? '条记录' : 'records'}</span>
          </div>
          <div className="mt-3 max-h-56 overflow-y-auto rounded-2xl border border-white/[0.06]">
            {recentVertebrateRecordPreviews.length === 0 ? (
              <p className="px-4 py-4 text-[13px] text-white/25">{isZh ? '保存脊椎动物记录后可在此预览导出掩码。' : 'Save vertebrate records to preview export masking here.'}</p>
            ) : (
              recentVertebrateRecordPreviews.map((item, idx) => (
                <div key={item.record.observation_id || item.record.observed_at || item.record.scientific_name} className={`px-4 py-3 ${idx < recentVertebrateRecordPreviews.length - 1 ? 'border-b border-white/[0.04]' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[14px] font-medium text-white">{getSpeciesDisplayName(item.record)}</p>
                      <p className="truncate text-[12px] text-white/25">{item.record.scientific_name || item.matched?.scientific_name || item.matched?.scientific || (isZh ? '未匹配类群' : 'Unmatched taxon')}</p>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${item.maskPreview.masked ? 'bg-[#FF9F0A]/15 text-[#FF9F0A]' : 'bg-[#30D158]/15 text-[#30D158]'}`}>
                      {item.maskPreview.label}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] text-white/30">{item.maskPreview.note}</p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h4 className="text-[15px] font-semibold text-white">{isZh ? '导出数据包' : 'Export bundle'}</h4>
              <p className="mt-1 text-[12px] text-white/30">
                {isZh ? '先保存事件，然后从后端导出特定管辖区的汇总数据。' : 'Save the event first, then export jurisdiction-specific summaries from the shared backend.'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => onSaveReview({ quiet: false })}
                disabled={savingReviewEvent}
                className="inline-flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 transition-colors active:bg-white/[0.08] disabled:opacity-40"
              >
                {savingReviewEvent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {isZh ? '保存审核事件' : 'Save review event'}
              </button>
              {EXPORT_JURISDICTIONS.map((option) => (
                <button
                  key={option.id}
                  onClick={() => onExport(option.id)}
                  disabled={!isOnline || exportingVertebrateJurisdiction !== '' || taxonomyGateByJurisdiction?.[option.id]?.isBlocked}
                  className={`inline-flex items-center gap-2 rounded-[12px] px-4 py-[11px] text-[14px] font-medium text-white transition-colors disabled:opacity-40 ${
                    exportJurisdiction === option.id ? 'bg-[#0A84FF] active:bg-[#0A84FF]/80' : 'bg-[#30D158] active:bg-[#30D158]/80'
                  }`}
                >
                  {exportingVertebrateJurisdiction === option.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  {isZh ? (option.label_zh || option.label) : option.label}
                </button>
              ))}
            </div>
          </div>

          {selectedTaxonomyGateBlocked && (
            <p className="mt-3 rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
              {isZh ? '请先解决分类版本和校验问题，然后再导出审核数据包。' : 'Resolve the taxonomy release and checksum gate before exporting this review bundle.'}
            </p>
          )}

          {!isOnline && (
            <p className="mt-3 rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
              {isZh ? '请重新连接网络以生成导出数据包。事件草稿和观测仍可离线排队。' : 'Reconnect to generate the export bundle. Event drafts and observations can still be queued offline.'}
            </p>
          )}

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <MetricCard
              title={isZh ? '数据包状态' : 'Bundle status'}
              value={exportState?.status || (isZh ? '未导出' : 'Not exported')}
              note={exportState?.created_at || exportState?.updated_at || (isZh ? '暂无导出任务' : 'No export job yet')}
            />
            <MetricCard
              title={isZh ? '数据包文件' : 'Bundle files'}
              value={exportFiles.length}
              note={exportState?.jurisdiction || exportJurisdiction}
            />
          </div>

          <div className="mt-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/25">{isZh ? '最新导出摘要' : 'Latest export summary'}</p>
            {Object.keys(exportSummary || {}).length === 0 ? (
              <p className="mt-2 text-[13px] text-white/25">{isZh ? '此选择尚未生成脊椎动物导出数据包。' : 'No terrestrial vertebrate export bundle has been generated for this selection yet.'}</p>
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
            <div className="mt-3 rounded-2xl border border-white/[0.06]">
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
      </div>
    </div>
  )
}
