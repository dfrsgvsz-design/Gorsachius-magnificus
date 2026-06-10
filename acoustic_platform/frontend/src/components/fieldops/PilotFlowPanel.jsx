import React from 'react'
import MetricCard from './MetricCard'

export default function PilotFlowPanel({
  copy,
  selectedRoute,
  pilotStatusCards,
  workflowSteps,
  protocolDefinition,
}) {
  return (
    <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="section-shell space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">{copy.pilotTitle || 'Transect pilot flow'}</h3>
            <p className="mt-1 text-sm text-gray-300">{copy.pilotBody || 'Pick one route, walk it, capture route-linked species records, then sync and export a clean transect report.'}</p>
          </div>
          <div className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-100">
            {selectedRoute?.name || (copy.routeMissing || 'Route needed')}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {pilotStatusCards.map((card) => (
            <MetricCard
              key={card.title}
              title={card.title}
              value={card.value}
              note={card.note}
            />
          ))}
        </div>
      </div>

      <div className="section-shell space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-white">{copy.transect || 'Transect'}</h3>
          <p className="mt-1 text-xs text-gray-400">
            {copy.selectTransectHint || 'Select a transect so species records, track logs, and exports stay tied to the same walk.'}
          </p>
        </div>
        <div className="space-y-2">
          {workflowSteps.map((step, index) => (
            <div key={step} className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-gray-200">
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-500/15 text-xs font-semibold text-cyan-200">
                {index + 1}
              </div>
              <p>{step}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
