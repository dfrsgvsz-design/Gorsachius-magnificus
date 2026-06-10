import React from 'react'
import { CloudDownload, Download, Loader2, Upload } from 'lucide-react'
import { formatBytes } from '../../lib/surveyOffline'

export default function OfflineMapPanel({
  copy,
  selectedRoute,
  activeMapPackages,
  currentProjectId,
  downloadingTiles,
  importingRoute,
  onPreloadTiles,
  onImportRoute,
  onExportRoute,
}) {
  return (
    <div className="section-shell space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{copy.map}</h3>
        <span className="text-xs text-gray-400">{activeMapPackages.length}</span>
      </div>
      <p className="text-xs text-gray-500">{copy.mapNote}</p>
      <div className="flex flex-wrap gap-2">
        <button onClick={onPreloadTiles} disabled={downloadingTiles || !currentProjectId} className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
          {downloadingTiles ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
          {copy.preloadMap}
        </button>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
          {importingRoute ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {copy.importRoute}
          <input type="file" accept=".gpx,.geojson,.json" className="hidden" onChange={onImportRoute} />
        </label>
      </div>
      {selectedRoute && (
        <div className="grid gap-2 sm:grid-cols-2">
          <button onClick={() => onExportRoute(selectedRoute, 'geojson')} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
            <Download className="h-4 w-4" />
            {copy.exportGeoJSON}
          </button>
          <button onClick={() => onExportRoute(selectedRoute, 'gpx')} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
            <Download className="h-4 w-4" />
            {copy.exportGpx}
          </button>
        </div>
      )}
      <div className="space-y-2">
        {activeMapPackages.slice(0, 3).map((item) => (
          <div key={item.package_id} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-300">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-white">{item.name}</span>
              <span>{item.status}</span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2 text-gray-400">
              <span>{item.min_zoom}-{item.max_zoom}</span>
              <span>{formatBytes(item.storage_bytes_estimate || 0)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
