import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react'

const TONES = {
  error: {
    wrap: 'border-red-500/20 bg-red-500/10 text-red-400',
    Icon: AlertCircle,
  },
  warning: {
    wrap: 'border-amber-500/20 bg-amber-500/10 text-amber-400',
    Icon: AlertTriangle,
  },
  success: {
    wrap: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400',
    Icon: CheckCircle2,
  },
  info: {
    wrap: 'border-cyan-500/20 bg-cyan-500/10 text-cyan-400',
    Icon: Info,
  },
}

export default function StatusBanner({ tone = 'info', message }) {
  if (!message) return null
  const config = TONES[tone] || TONES.info
  const Icon = config.Icon

  return (
    <section className={`flex items-start gap-3 rounded-lg border p-4 ${config.wrap}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="text-sm font-medium">{message}</p>
    </section>
  )
}
