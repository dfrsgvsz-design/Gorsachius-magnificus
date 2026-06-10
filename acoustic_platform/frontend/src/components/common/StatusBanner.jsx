import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

const TONE_CONFIG = {
  error: {
    Icon: XCircle,
    style: { borderColor: 'rgba(179,27,27,0.2)', background: 'rgba(179,27,27,0.04)', color: 'var(--cornell-carnelian)' },
  },
  warning: {
    Icon: AlertTriangle,
    style: { borderColor: 'rgba(245,158,11,0.3)', background: '#FFFBEB', color: '#92400E' },
  },
  success: {
    Icon: CheckCircle2,
    style: { borderColor: 'rgba(45,106,79,0.2)', background: 'rgba(45,106,79,0.04)', color: 'var(--cornell-forest)' },
  },
  info: {
    Icon: Info,
    style: { borderColor: 'rgba(0,102,153,0.2)', background: 'rgba(0,102,153,0.04)', color: 'var(--cornell-blue)' },
  },
}

export function StatusBanner({ tone = 'error', message }) {
  if (!message) return null
  const config = TONE_CONFIG[tone] || TONE_CONFIG.error
  const { Icon } = config

  return (
    <div className="flex items-start gap-3 rounded-xl border p-4" style={config.style}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0" />
      <p className="text-sm leading-6">{message}</p>
    </div>
  )
}
