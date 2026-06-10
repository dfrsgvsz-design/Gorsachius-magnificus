import React from 'react'
import { Download, Loader2, Save } from 'lucide-react'
import MetricCard from './MetricCard'
import { EXPORT_JURISDICTIONS } from './constants'
import {
  toArray,
  buildPreviewEntries,
  formatPreviewKey,
  formatPreviewValue,
  getSpeciesDisplayName,
} from './helpers'

export default function VertebrateReviewPanel({
  protocolDefinition,
  exportJurisdiction,
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
  const eventEntries = buildPreviewEntries(eventPayloadDraft)
  const recordEntries = buildPreviewEntries(currentRecordPayloadDraft)
  const exportState = vertebrateExportResult?.exportJob || latestProtocolExportJob || null
  const exportSummary = vertebrateExportResult?.summary || exportState?.summary || {}
  const exportFiles = toArray(exportState?.bundle?.files)
  const primarySpeciesName = getSpeciesDisplayName(currentMatchedSpecies || {})
  const selectedTaxonomyGateBlocked = Boolean(taxonomyGateByJurisdiction?.[exportJurisdiction]?.isBlocked)

  return (
    <div className="section-shell space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">Terrestrial vertebrate review</h3>
          <p className="mt-1 text-xs text-gray-400">
            Save one protocol event preview, check masking, then export a jurisdiction-specific bundle.
          </p>
        </div>
        <label className="space-y-1 text-xs text-gray-400">
          <span className="block">Export jurisdiction</span>
          <select
            value={exportJurisdiction}
            onChange={(event) => onChangeJurisdiction(event.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
          >
            {EXPORT_JURISDICTIONS.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard
          title="Event status"
          value={eventValidationMissing.length === 0 ? 'Ready' : 'Needs fields'}
          note={eventValidationMissing.length === 0 ? protocolDefinition.label : eventValidationMissing.join(', ')}
        />
        <MetricCard
          title="Record status"
          value={recordValidationMissing.length === 0 ? 'Ready' : 'Needs fields'}
          note={recordValidationMissing.length === 0 ? (primarySpeciesName || 'Current draft') : recordValidationMissing.join(', ')}
        />
        <MetricCard
          title="Mask preview"
          value={currentRecordMaskPreview.label}
          note={`${maskedPreviewCount}/${recentVertebrateRecordPreviews.length} recent records masked`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Event payload</p>
              <p className="mt-1 text-sm text-white">{protocolDefinition.label}</p>
            </div>
            {latestProtocolEvent && (
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-100">
                Saved {latestProtocolEvent.started_at ? new Date(latestProtocolEvent.started_at).toLocaleString() : 'draft'}
              </span>
            )}
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {eventEntries.length === 0 ? (
              <p className="text-sm text-gray-400">No protocol event fields entered yet.</p>
            ) : (
              eventEntries.map(([key, value]) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-gray-500">{formatPreviewKey(key)}</p>
                  <p className="mt-1 text-sm text-white">{formatPreviewValue(value)}</p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Record payload</p>
              <p className="mt-1 text-sm text-white">{primarySpeciesName || 'Current observation draft'}</p>
            </div>
            <span className={`rounded-full border px-3 py-1 text-xs ${currentRecordMaskPreview.masked ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-cyan-500/20 bg-cyan-500/10 text-cyan-100'}`}>
              {currentRecordMaskPreview.label}
            </span>
          </div>
          <p className="mt-2 text-xs text-gray-400">{currentRecordMaskPreview.note}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {recordEntries.length === 0 ? (
              <p className="text-sm text-gray-400">No protocol record fields entered yet.</p>
            ) : (
              recordEntries.map(([key, value]) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-gray-500">{formatPreviewKey(key)}</p>
                  <p className="mt-1 text-sm text-white">{formatPreviewValue(value)}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-sm font-semibold text-white">Recent masking preview</h4>
            <span className="text-xs text-gray-400">{recentVertebrateRecordPreviews.length} records</span>
          </div>
          <div className="mt-3 max-h-56 space-y-2 overflow-y-auto">
            {recentVertebrateRecordPreviews.length === 0 ? (
              <p className="text-sm text-gray-400">Save vertebrate records to preview export masking here.</p>
            ) : (
              recentVertebrateRecordPreviews.map((item) => (
                <div key={item.record.observation_id || item.record.observed_at || item.record.scientific_name} className="rounded-lg border border-white/10 bg-black/20 px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-white">{getSpeciesDisplayName(item.record)}</p>
                      <p className="truncate text-xs text-gray-500">{item.record.scientific_name || item.matched?.scientific_name || item.matched?.scientific || 'Unmatched taxon'}</p>
                    </div>
                    <span className={`rounded-full border px-2 py-1 text-[11px] ${item.maskPreview.masked ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                      {item.maskPreview.label}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-gray-400">{item.maskPreview.note}</p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h4 className="text-sm font-semibold text-white">Export bundle</h4>
              <p className="mt-1 text-xs text-gray-400">
                Save the event first, then export jurisdiction-specific summaries from the shared backend.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => onSaveReview({ quiet: false })}
                disabled={savingReviewEvent}
                className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50"
              >
                {savingReviewEvent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Save review event
              </button>
              {EXPORT_JURISDICTIONS.map((option) => (
                <button
                  key={option.id}
                  onClick={() => onExport(option.id)}
                  disabled={!isOnline || exportingVertebrateJurisdiction !== '' || taxonomyGateByJurisdiction?.[option.id]?.isBlocked}
                  className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-50 ${
                    exportJurisdiction === option.id ? 'bg-cyan-500' : 'bg-emerald-500'
                  }`}
                >
                  {exportingVertebrateJurisdiction === option.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {selectedTaxonomyGateBlocked && (
            <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
              Resolve the taxonomy release and checksum gate before exporting this review bundle.
            </p>
          )}

          {!isOnline && (
            <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
              Reconnect to generate the export bundle. Event drafts and observations can still be queued offline.
            </p>
          )}

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <MetricCard
              title="Bundle status"
              value={exportState?.status || 'Not exported'}
              note={exportState?.created_at || exportState?.updated_at || 'No export job yet'}
            />
            <MetricCard
              title="Bundle files"
              value={exportFiles.length}
              note={exportState?.jurisdiction || exportJurisdiction}
            />
          </div>

          <div className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Latest export summary</p>
            {Object.keys(exportSummary || {}).length === 0 ? (
              <p className="mt-2 text-sm text-gray-400">No terrestrial vertebrate export bundle has been generated for this selection yet.</p>
            ) : (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {Object.entries(exportSummary).map(([key, value]) => (
                  <div key={key} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-gray-500">{formatPreviewKey(key)}</p>
                    <p className="mt-1 text-sm text-white">{formatPreviewValue(value)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {exportFiles.length > 0 && (
            <div className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3">
              <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Bundle files</p>
              <div className="mt-3 space-y-2">
                {exportFiles.map((file) => (
                  <div key={file.filename || file.output_id} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-200">
                    <span className="truncate text-white">{file.filename || file.output_id || 'export-file'}</span>
                    <span className="shrink-0 text-xs text-gray-500">{file.media_type || 'text/csv'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
