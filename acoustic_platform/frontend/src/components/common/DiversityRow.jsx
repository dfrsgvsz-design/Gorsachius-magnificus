export default function DiversityRow({ label, value, desc }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-3 md:gap-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface-secondary)' }}>
      <div className="min-w-0">
        <p className="text-xs font-medium md:text-sm" style={{ color: 'var(--text-primary)' }}>{label}</p>
        <p className="truncate text-[11px] md:text-xs" style={{ color: 'var(--text-tertiary)' }}>{desc}</p>
      </div>
      <span className="shrink-0 text-base font-bold md:ml-4 md:text-lg" style={{ color: 'var(--cornell-teal)' }}>{value ?? '--'}</span>
    </div>
  )
}
