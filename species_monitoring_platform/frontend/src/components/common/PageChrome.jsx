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
    <section className={`card-padded space-y-5 ${className}`.trim()}>
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

export function EmptyPanel({
  icon: Icon,
  title,
  body,
}) {
  return (
    <div className="empty-panel">
      {Icon ? <Icon className="mx-auto mb-3 h-10 w-10 opacity-20" /> : null}
      <p className="text-sm text-white/50">{title}</p>
      {body ? <p className="mt-1.5 text-xs text-white/25">{body}</p> : null}
    </div>
  )
}

export function InfoNote({ title, body, tone = 'default' }) {
  const toneClass = {
    default: 'border-white/[0.06] bg-white/[0.03]',
    emerald: 'border-emerald-500/15 bg-emerald-500/5',
    cyan: 'border-cyan-500/15 bg-cyan-500/5',
    amber: 'border-amber-500/15 bg-amber-500/5',
  }

  return (
    <div className={`rounded-xl border p-3 md:p-4 ${toneClass[tone] || toneClass.default}`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/25 md:text-xs">{title}</p>
      <p className="mt-1.5 text-xs leading-5 text-white/50 md:mt-2 md:text-sm md:leading-6">{body}</p>
    </div>
  )
}
