import React from 'react'
import { ArrowRight, Activity, Camera, MapPin, Mic } from 'lucide-react'
import { getPermissionCopy } from '../../lib/permissionCopy'

const ICON_MAP = {
  MapPin,
  Camera,
  Mic,
  Activity,
}

/**
 * Shown in-place where the feature would have appeared after the user denies
 * (or "Don't ask again"-blocks) a permission. The contract is:
 *
 *   - Never crash. The surrounding feature is gone but the rest of the
 *     screen keeps working.
 *   - Always explain WHY the feature is dimmed and WHAT the user can still
 *     do (the "degraded mode" copy).
 *   - When the OS allows it, offer a one-tap "Open Settings" deep link via
 *     `onOpenSettings`. Otherwise show the manual recovery hint.
 */
export default function PermissionDeniedFallback({
  permissionId,
  locale = 'zh',
  onRetry,
  onOpenSettings,
  blocked = false,
}) {
  const copy = getPermissionCopy(permissionId, locale)
  if (!copy) return null

  const Icon = ICON_MAP[copy.icon] || MapPin
  const isZh = locale === 'zh'

  return (
    <section
      role="status"
      aria-live="polite"
      className="space-y-3 rounded-2xl border border-amber-500/15 bg-amber-500/5 p-4"
    >
      <header className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-white">{copy.denied.headline}</h3>
          <p className="mt-1 text-[13px] leading-5 text-white/60">{copy.denied.body}</p>
        </div>
      </header>

      <div className="rounded-xl bg-white/[0.04] px-3 py-2 text-[12px] text-white/50">
        <span className="font-medium text-white/70">
          {isZh ? '当前模式:' : 'Current mode:'}
        </span>{' '}
        {copy.denied.degradedMode}
      </div>

      <div className="flex flex-wrap gap-2">
        {!blocked && onRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-[10px] bg-[#0A84FF]/15 px-3 py-[9px] text-[13px] font-medium text-[#0A84FF] transition-colors active:bg-[#0A84FF]/25"
          >
            {isZh ? '再试一次' : 'Try again'}
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        )}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="inline-flex items-center gap-1.5 rounded-[10px] border border-white/[0.08] bg-white/[0.04] px-3 py-[9px] text-[13px] text-white/60 transition-colors active:bg-white/[0.08]"
          >
            {isZh ? '打开系统设置' : 'Open settings'}
          </button>
        )}
      </div>

      <p className="text-[11px] text-white/30">{copy.recoverHint}</p>
    </section>
  )
}
