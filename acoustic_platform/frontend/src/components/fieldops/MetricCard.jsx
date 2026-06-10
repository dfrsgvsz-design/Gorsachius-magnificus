import React from 'react'

export default function MetricCard({ title, value, note }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3">
      <p className="text-xs text-gray-400">{title}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
      <p className="mt-1 text-[11px] text-gray-500">{note}</p>
    </div>
  )
}
