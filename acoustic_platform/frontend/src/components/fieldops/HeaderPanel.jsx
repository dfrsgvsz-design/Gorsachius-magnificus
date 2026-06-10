import React from 'react'
import { Loader2, MapPinned, RefreshCw, Save } from 'lucide-react'

export default function HeaderPanel({
  copy,
  isOnline,
  loadingSync,
  syncQueueLength,
  onPull,
  onPush,
}) {
  return (
    <section className="glass-card p-5">
      <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-300">
        <MapPinned className="h-3.5 w-3.5" />
        {copy.badge}
      </div>
      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-4xl">
          <h2 className="text-2xl font-bold text-white">{copy.title}</h2>
          <p className="mt-2 text-sm text-gray-300">{copy.body}</p>
          <p className="mt-2 text-xs text-gray-500">{copy.noProject}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded-full border px-3 py-1 ${isOnline ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-300'}`}>
            {isOnline ? copy.online : copy.offline}
          </span>
          <button onClick={onPull} disabled={!isOnline || loadingSync} className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white disabled:opacity-50">
            {loadingSync ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {copy.pull}
          </button>
          <button onClick={onPush} disabled={!isOnline || loadingSync || syncQueueLength === 0} className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-white disabled:opacity-50">
            <Save className="h-4 w-4" />
            {copy.push}
          </button>
        </div>
      </div>
    </section>
  )
}
