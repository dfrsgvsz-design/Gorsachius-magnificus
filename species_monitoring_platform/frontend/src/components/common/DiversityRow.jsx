export default function DiversityRow({ label, value, desc }) {
  return (
    <div className="surface-card-muted flex items-center justify-between gap-3 py-2.5 md:gap-4 md:py-3">
      <div className="min-w-0">
        <p className="text-xs font-medium text-white md:text-sm">{label}</p>
        <p className="truncate text-[11px] text-white/25 md:text-xs">{desc}</p>
      </div>
      <span className="shrink-0 text-base font-bold text-[#30D158] md:ml-4 md:text-lg">{value ?? '--'}</span>
    </div>
  )
}
