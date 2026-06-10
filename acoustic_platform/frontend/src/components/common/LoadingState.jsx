import { Loader2 } from 'lucide-react'

export function LoadingState({ message = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center py-12">
      <Loader2 className="mr-3 h-5 w-5 animate-spin" style={{ color: 'var(--cornell-carnelian)' }} />
      <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{message}</span>
    </div>
  )
}
