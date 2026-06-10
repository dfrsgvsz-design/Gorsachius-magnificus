import React from 'react'
import MetricCard from './MetricCard'

/**
 * Transect pilot flow overview with status cards and workflow steps.
 * Extracted from FieldOpsTab.jsx lines 2881-2922.
 */
export default function PilotFlowPanel({
  copy,
  selectedRoute,
  pilotStatusCards,
  workflowSteps,
}) {
  return (
    <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-[15px] font-semibold text-white">{copy.pilotTitle || 'Transect pilot flow'}</h3>
            <p className="mt-1 text-[13px] leading-5 text-white/50">{copy.pilotBody || 'Pick one route, walk it, capture route-linked species records, then sync and export a clean transect report.'}</p>
          </div>
          <span className="shrink-0 rounded-full bg-[#0A84FF]/15 px-3 py-1 text-[12px] font-medium text-[#0A84FF]">
            {selectedRoute?.name || (copy.routeMissing || 'Route needed')}
          </span>
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

      <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
        <div>
          <h3 className="text-[15px] font-semibold text-white">{copy.transect || 'Transect'}</h3>
          <p className="mt-1 text-[12px] text-white/30">
            {copy.selectTransectHint || 'Select a transect so species records, track logs, and exports stay tied to the same walk.'}
          </p>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02]">
          {workflowSteps.map((step, index) => (
            <div key={step} className={`flex items-start gap-3 px-4 py-[13px] ${index < workflowSteps.length - 1 ? 'border-b border-white/[0.04]' : ''}`}>
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#0A84FF]/15 text-[11px] font-bold text-[#0A84FF]">
                {index + 1}
              </div>
              <p className="text-[14px] leading-5 text-white/70">{step}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
