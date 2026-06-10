import { Loader2 } from 'lucide-react'

export default function LoadingState({ text }) {
  return (
    <div className="flex items-center justify-center py-20" role="status" aria-busy="true" aria-live="polite">
      <Loader2 className="w-6 h-6 animate-spin text-[#0A84FF] mr-3" aria-hidden="true" />
      <span className="text-white/40">{text}</span>
    </div>
  )
}
