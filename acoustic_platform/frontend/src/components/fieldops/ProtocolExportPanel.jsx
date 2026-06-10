import React from 'react'
import { Download, Loader2, Save } from 'lucide-react'
import MetricCard from './MetricCard'
import { EXPORT_JURISDICTIONS } from './constants'
import { toArray, formatPreviewKey, formatPreviewValue } from './helpers'

export default function ProtocolExportPanel({
  protocolDefinition,
  exportJurisdiction,
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
  const exportFiles = toArray(latestProtocolExportJob?.bundle?.files)
  const exportSummary = latestProtocolExportJob?.summary || {}
  const selectedTaxonomyGateBlocked = Boolean(taxonomyGateByJurisdiction?.[exportJurisdiction]?.isBlocked)

  return (
    <div className="section-shell space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">Protocol export bundle</h3>
          <p className="mt-1 text-xs text-gray-400">
            Save the active event context, then export jurisdiction-specific CSV and JSON bundle files for this protocol.
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
        <MetricCard title="Observations" value={observationCount} note={protocolDefinition.label} />
        <MetricCard
          title="Tracks"
          value={trackCount}
          note={protocolDefinition.supportsTrack ? 'Route-based effort' : 'No live track required'}
        />
        <MetricCard
          title="Taxonomy package"
          value={taxonomyPackage?.label || 'Pending sync'}
          note={taxonomyPackageNote}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onSaveEvent({ quiet: false })}
          disabled={savingEvent}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          {savingEvent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save event
        </button>
        {EXPORT_JURISDICTIONS.map((option) => (
          <button
            key={option.id}
            onClick={() => onExport(option.id)}
            disabled={!isOnline || exportingJurisdiction !== '' || taxonomyGateByJurisdiction?.[option.id]?.isBlocked}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-50 ${
              exportJurisdiction === option.id ? 'bg-cyan-500' : 'bg-emerald-500'
            }`}
          >
            {exportingJurisdiction === option.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {option.label}
          </button>
        ))}
      </div>

      {selectedTaxonomyGateBlocked && (
        <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
          Resolve the taxonomy release and checksum gate before exporting this protocol bundle.
        </p>
      )}

      {!isOnline && (
        <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
          Reconnect to generate the export bundle. Event drafts and observations can still be queued offline.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard
          title="Event"
          value={latestProtocolEvent ? 'Saved' : 'Draft only'}
          note={latestProtocolEvent?.started_at || 'Save once before export to pin the event context'}
        />
        <MetricCard
          title="Bundle status"
          value={latestProtocolExportJob?.status || 'Not exported'}
          note={latestProtocolExportJob?.updated_at || latestProtocolExportJob?.created_at || 'No export job yet'}
        />
        <MetricCard
          title="Bundle files"
          value={exportFiles.length}
          note={latestProtocolExportJob?.jurisdiction || exportJurisdiction}
        />
      </div>

      <div className="rounded-lg border border-white/10 bg-black/20 p-3">
        <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Latest export summary</p>
        {Object.keys(exportSummary).length === 0 ? (
          <p className="mt-2 text-sm text-gray-400">No export bundle has been generated for this protocol and jurisdiction yet.</p>
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
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
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
  )
}
