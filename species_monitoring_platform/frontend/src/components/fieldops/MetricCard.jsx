import React from 'react'

/**
 * Reusable metric display card.
 * Extracted from FieldOpsTab.jsx lines 4302-4310.
 */
export default function MetricCard({ title, value, note }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] px-3 py-3">
      <p className="text-[12px] text-white/30">{title}</p>
      <p className="mt-1 text-[20px] font-bold tracking-tight text-white">{value}</p>
      {note && <p className="mt-0.5 text-[11px] text-white/20">{note}</p>}
    </div>
  )
}
