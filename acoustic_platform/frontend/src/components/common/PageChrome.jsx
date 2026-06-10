export function PageHero({
  kicker,
  title,
  body,
  actions = null,
  metrics = null,
  aside = null,
  className = '',
}) {
  return (
    <section className={`section-shell space-y-5 ${className}`.trim()}>
      <div className="page-hero-grid">
        <div className="min-w-0">
          {kicker ? <div className="section-kicker">{kicker}</div> : null}
          <h2 className="section-title">{title}</h2>
          {body ? <p className="section-copy">{body}</p> : null}
          {actions ? <div className="page-hero-actions">{actions}</div> : null}
        </div>
        {aside ? <div className="page-hero-aside">{aside}</div> : null}
      </div>
      {metrics ? <div className="page-hero-metrics">{metrics}</div> : null}
    </section>
  )
}

export function SectionHeader({
  title,
  body,
  action = null,
  className = '',
}) {
  return (
    <div className={`flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between ${className}`.trim()}>
      <div className="min-w-0">
        <h3 className="subsection-title">{title}</h3>
        {body ? <p className="subsection-copy">{body}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}

export function EmptyPanel({ icon: Icon, title, body }) {
  return (
    <div className="empty-panel">
      {Icon ? <Icon className="mx-auto mb-3 h-10 w-10" style={{ color: 'var(--text-tertiary)', opacity: 0.4 }} /> : null}
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{title}</p>
      {body ? <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>{body}</p> : null}
    </div>
  )
}

export function InfoNote({ title, body, tone = 'default' }) {
  const toneStyles = {
    default: { borderColor: 'var(--border-default)', background: 'var(--surface-secondary)' },
    carnelian: { borderColor: 'rgba(179,27,27,0.2)', background: 'rgba(179,27,27,0.03)' },
    teal: { borderColor: 'rgba(13,115,119,0.2)', background: 'rgba(13,115,119,0.03)' },
    blue: { borderColor: 'rgba(0,102,153,0.2)', background: 'rgba(0,102,153,0.03)' },
    amber: { borderColor: 'rgba(245,158,11,0.2)', background: '#FFFBEB' },
  }

  const style = toneStyles[tone] || toneStyles.default

  return (
    <div className="rounded-xl border p-3 md:p-4" style={style}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] md:text-xs md:tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>{title}</p>
      <p className="mt-1.5 text-xs leading-5 md:mt-2 md:text-sm md:leading-6" style={{ color: 'var(--text-primary)' }}>{body}</p>
    </div>
  )
}
