import { isValidElement } from 'react'

const COLOR_MAP = {
  emerald: 'border-emerald-500/20 bg-emerald-500/8 text-emerald-400',
  cyan: 'border-cyan-500/20 bg-cyan-500/8 text-cyan-400',
  violet: 'border-violet-500/20 bg-violet-500/8 text-violet-400',
  amber: 'border-amber-500/20 bg-amber-500/8 text-amber-400',
  red: 'border-red-500/20 bg-red-500/8 text-red-400',
}

export default function StatCard({ label, value, icon: Icon, color }) {
  const cls = COLOR_MAP[color] || COLOR_MAP.emerald

  return (
    <div className="card-padded">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-white/35">{label}</span>
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${cls}`}>
          {isValidElement(Icon) ? Icon : Icon ? <Icon className="h-4 w-4" /> : null}
        </span>
      </div>
      <p className="text-2xl font-bold text-white">{value ?? '--'}</p>
    </div>
  )
}
