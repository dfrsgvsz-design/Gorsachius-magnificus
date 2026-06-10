import React, { useEffect, useState } from 'react'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'

const TOAST_ICONS = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
}

const TOAST_CLASSES = {
  success: 'toast-success',
  error: 'toast-error',
  info: 'toast-info',
}

export function useToast(duration = 3000) {
  const [toast, setToast] = useState(null)

  const show = (message, type = 'success') => {
    setToast({ message, type, key: Date.now() })
  }

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(null), duration)
    return () => clearTimeout(timer)
  }, [toast, duration])

  const ToastComponent = toast ? (
    <Toast message={toast.message} type={toast.type} key={toast.key} onClose={() => setToast(null)} />
  ) : null

  return { show, ToastComponent }
}

export default function Toast({ message, type = 'success', onClose }) {
  const Icon = TOAST_ICONS[type] || Info

  return (
    <div className={`toast ${TOAST_CLASSES[type] || TOAST_CLASSES.info}`}>
      <span className="inline-flex items-center gap-2">
        <Icon className="h-4 w-4" />
        {message}
      </span>
    </div>
  )
}
