import React, { useCallback, useEffect, useState } from 'react'
import { Layers, Maximize2, Minimize2, X } from 'lucide-react'

// Best-effort landscape lock. The Screen Orientation API requires a
// user-gesture context and is only available when the page (or PWA) is
// actually fullscreen, which is exactly when this component is mounted in
// fullscreen mode. Errors are swallowed because:
//  - Safari < 16.4 omits `screen.orientation.lock` entirely.
//  - Desktop Chrome rejects with `NotSupportedError` (no rotation hardware).
//  - In a Capacitor WebView the orientation is controlled by the activity
//    manifest, so the JS call is harmless but a no-op.
async function tryLockLandscape() {
  try {
    if (typeof screen !== 'undefined' && screen.orientation && typeof screen.orientation.lock === 'function') {
      await screen.orientation.lock('landscape')
    }
  } catch {
    // Ignore: orientation lock is a UX nicety, not a correctness requirement.
  }
}

function tryUnlockOrientation() {
  try {
    if (typeof screen !== 'undefined' && screen.orientation && typeof screen.orientation.unlock === 'function') {
      screen.orientation.unlock()
    }
  } catch {
    // Ignore: see comment on tryLockLandscape.
  }
}

export default function FullScreenMap({ children, onClose, layers = [], activeLayer, onLayerChange }) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      if (isFullscreen) setIsFullscreen(false)
      else onClose?.()
    }
  }, [isFullscreen, onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  useEffect(() => {
    if (!isFullscreen) return undefined
    void tryLockLandscape()
    return () => {
      tryUnlockOrientation()
    }
  }, [isFullscreen])

  if (!isFullscreen) {
    return (
      <div className="relative rounded-xl overflow-hidden border border-white/[0.06]" style={{ height: 480 }}>
        {children}
        <div className="absolute top-3 right-3 z-[1000] flex gap-2">
          {layers.length > 0 && (
            <MapLayerControl layers={layers} active={activeLayer} onChange={onLayerChange} />
          )}
          <button
            onClick={() => setIsFullscreen(true)}
            className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#161b22]/90 border border-white/[0.08] text-white/60 hover:text-white backdrop-blur-sm transition"
            title="Fullscreen"
            aria-label="Enter fullscreen map"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="absolute top-3 left-3 z-[1000] flex items-center justify-center w-9 h-9 rounded-lg bg-[#161b22]/90 border border-white/[0.08] text-white/60 hover:text-white backdrop-blur-sm transition"
            aria-label="Close map"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="fullscreen-map-container">
      {children}
      <div className="fullscreen-map-toolbar">
        {layers.length > 0 && (
          <MapLayerControl layers={layers} active={activeLayer} onChange={onLayerChange} />
        )}
        <button
          onClick={() => setIsFullscreen(false)}
          title="Exit fullscreen"
          aria-label="Exit fullscreen map"
        >
          <Minimize2 className="h-4 w-4" />
        </button>
        {onClose && (
          <button
            onClick={() => { setIsFullscreen(false); onClose() }}
            title="Close map"
            aria-label="Close map"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  )
}

function MapLayerControl({ layers, active, onChange }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#161b22]/90 border border-white/[0.08] text-white/60 hover:text-white backdrop-blur-sm transition"
        title="Map layers"
        aria-label="Toggle map layers"
      >
        <Layers className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-white/[0.08] bg-[#161b22]/95 backdrop-blur-xl p-2 animate-scale-in">
          {layers.map((layer) => (
            <button
              key={layer.id}
              onClick={() => { onChange?.(layer.id); setOpen(false) }}
              className={`flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs transition ${
                active === layer.id
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'text-white/50 hover:bg-white/[0.06] hover:text-white'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${active === layer.id ? 'bg-emerald-400' : 'bg-white/20'}`} />
              {layer.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
