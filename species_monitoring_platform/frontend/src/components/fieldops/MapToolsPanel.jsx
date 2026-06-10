import React from 'react'
import { CloudDownload, Download, Loader2, Upload } from 'lucide-react'
import { formatBytes } from '../../lib/surveyOffline'

/**
 * Map tile preloading, route import/export, and offline map packages.
 * Extracted from FieldOpsTab.jsx lines 3208-3251.
 */
export default function MapToolsPanel({
  copy,
  activeMapPackages,
  selectedRoute,
  currentProjectId,
  downloadingTiles,
  importingRoute,
  onPreloadTiles,
  onImportRoute,
  onExportRoute,
}) {
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-white">{copy.map}</h3>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">{activeMapPackages.length}</span>
      </div>
      <p className="text-[12px] text-white/30">{copy.mapNote}</p>
      <div className="flex flex-wrap gap-2">
        {/* Preloading should be available even before a project exists — the
            preload step writes into the shared service-worker tile cache so
            offline crews on a fresh device can stage map data first. */}
        <button onClick={onPreloadTiles} disabled={downloadingTiles} className="inline-flex items-center gap-2 rounded-[12px] bg-[#30D158] px-4 py-[11px] text-[14px] font-medium text-white transition-colors active:bg-[#30D158]/80 disabled:opacity-40">
          {downloadingTiles ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
          {copy.preloadMap}
        </button>
        <label className={`inline-flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 active:bg-white/[0.08] ${currentProjectId ? 'cursor-pointer' : 'cursor-not-allowed opacity-40'}`}>
          {importingRoute ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {copy.importRoute}
          <input
            type="file"
            accept=".gpx,.geojson,.json"
            className="hidden"
            onChange={onImportRoute}
            disabled={!currentProjectId || importingRoute}
          />
        </label>
      </div>
      {selectedRoute && (
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => onExportRoute(selectedRoute, 'geojson')} className="inline-flex items-center justify-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-[11px] text-[14px] text-white/60 active:bg-white/[0.08]">
            <Download className="h-4 w-4" />
            {copy.exportGeoJSON}
          </button>
          <button onClick={() => onExportRoute(selectedRoute, 'gpx')} className="inline-flex items-center justify-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-[11px] text-[14px] text-white/60 active:bg-white/[0.08]">
            <Download className="h-4 w-4" />
            {copy.exportGpx}
          </button>
        </div>
      )}
      {activeMapPackages.length > 0 && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02]">
          {activeMapPackages.slice(0, 3).map((item, idx) => (
            <div key={item.package_id} className={`px-4 py-[10px] ${idx < Math.min(activeMapPackages.length, 3) - 1 ? 'border-b border-white/[0.04]' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[14px] font-medium text-white">{item.name}</span>
                <span className="text-[12px] text-white/30">{item.status}</span>
              </div>
              <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-white/20">
                <span>zoom {item.min_zoom}-{item.max_zoom}</span>
                <span>{formatBytes(item.storage_bytes_estimate || 0)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
