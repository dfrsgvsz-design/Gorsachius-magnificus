export default function ConfidenceBadge({ value }) {
  const pct = (value * 100).toFixed(1)
  const color = value >= 0.7 ? 'text-[#30D158] bg-[#30D158]/15' :
                value >= 0.4 ? 'text-[#FF9F0A] bg-[#FF9F0A]/15' :
                'text-white/30 bg-white/[0.06]'
  return <span className={`species-badge text-xs ${color}`}>{pct}%</span>
}
