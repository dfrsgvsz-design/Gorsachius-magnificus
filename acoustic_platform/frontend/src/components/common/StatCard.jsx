export function StatCard({ label, value, icon: Icon, color = 'default', subtitle }) {
  const colorMap = {
    default: { icon: 'var(--text-tertiary)', accent: 'var(--border-default)' },
    carnelian: { icon: 'var(--cornell-carnelian)', accent: 'rgba(179,27,27,0.15)' },
    blue: { icon: 'var(--cornell-blue)', accent: 'rgba(0,102,153,0.15)' },
    teal: { icon: 'var(--cornell-teal)', accent: 'rgba(13,115,119,0.15)' },
    forest: { icon: 'var(--cornell-forest)', accent: 'rgba(45,106,79,0.15)' },
    amber: { icon: '#D97706', accent: 'rgba(245,158,11,0.15)' },
  }

  const palette = colorMap[color] || colorMap.default

  return (
    <div className="stat-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="stat-label">{label}</p>
          <p className="stat-value mt-1">{value}</p>
          {subtitle && <p className="mt-0.5 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{subtitle}</p>}
        </div>
        {Icon && (
          <div className="shrink-0 rounded-lg p-2.5" style={{ background: palette.accent }}>
            <Icon className="h-5 w-5" style={{ color: palette.icon }} />
          </div>
        )}
      </div>
    </div>
  )
}
