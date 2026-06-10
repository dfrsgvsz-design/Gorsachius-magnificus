export function ConfidenceBadge({ value, thresholds = [0.8, 0.5] }) {
  const pct = typeof value === 'number' ? value : 0
  const display = `${(pct * 100).toFixed(1)}%`

  let style
  if (pct >= thresholds[0]) {
    style = { background: 'rgba(45,106,79,0.1)', color: 'var(--cornell-forest)' }
  } else if (pct >= thresholds[1]) {
    style = { background: 'rgba(245,158,11,0.1)', color: '#D97706' }
  } else {
    style = { background: 'rgba(179,27,27,0.08)', color: 'var(--cornell-carnelian)' }
  }

  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium" style={style}>
      {display}
    </span>
  )
}
