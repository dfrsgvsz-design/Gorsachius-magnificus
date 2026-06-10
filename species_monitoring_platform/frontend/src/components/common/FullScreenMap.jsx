import React, { useCallback, useEffect, useState } from 'react'
import { Layers, Maximize2, Minimize2, X } from 'lucide-react'

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
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="absolute top-3 left-3 z-[1000] flex items-center justify-center w-9 h-9 rounded-lg bg-[#161b22]/90 border border-white/[0.08] text-white/60 hover:text-white backdrop-blur-sm transition"
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
        <button onClick={() => setIsFullscreen(false)} title="Exit fullscreen">
          <Minimize2 className="h-4 w-4" />
        </button>
        {onClose && (
          <button onClick={() => { setIsFullscreen(false); onClose() }} title="Close map">
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
