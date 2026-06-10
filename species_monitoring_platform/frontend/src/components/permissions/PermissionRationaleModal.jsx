import React from 'react'
import { Activity, Camera, MapPin, Mic, X } from 'lucide-react'
import { getPermissionCopy } from '../../lib/permissionCopy'

const ICON_MAP = {
  MapPin,
  Camera,
  Mic,
  Activity,
}

/**
 * Scenario card shown before the OS permission prompt. Renders four anchored
 * lines that audit reviewers expect to see:
 *
 *   1. WHAT — clear permission name
 *   2. SCENE — concrete in-app use case
 *   3. WHEN — when it activates (never silently in background)
 *   4. BENEFIT — what the user gains
 *
 * Action row offers a primary "Allow" (calls `onAccept`) and a secondary
 * "Skip" link (calls `onSkip`); both close the modal upstream. The component
 * is presentation-only and does not call any native API — it relies on the
 * caller (typically `usePermissionGate`) to map clicks to OS requests.
 */
export default function PermissionRationaleModal({
  open,
  permissionId,
  locale = 'zh',
  onAccept,
  onSkip,
  onClose,
}) {
  if (!open) return null
  const copy = getPermissionCopy(permissionId, locale)
  if (!copy) return null

  const Icon = ICON_MAP[copy.icon] || MapPin
  const isZh = locale === 'zh'

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={`perm-${permissionId}-title`}
      className="fixed inset-0 z-[9000] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-md rounded-3xl border border-white/[0.08] bg-[#161b22] p-6 shadow-2xl">
        <button
          onClick={onClose ?? onSkip}
          aria-label={isZh ? '关闭' : 'Close'}
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-white/40 transition hover:bg-white/[0.06] hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#0A84FF]/15 text-[#0A84FF]">
            <Icon className="h-6 w-6" />
          </span>
          <h2 id={`perm-${permissionId}-title`} className="text-[17px] font-semibold text-white">
            {copy.rationale.title}
          </h2>
        </div>

        <dl className="space-y-3 text-[14px]">
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wider text-white/40">
              {isZh ? '用途' : 'Used for'}
            </dt>
            <dd className="mt-1 text-white/80">{copy.rationale.scene}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wider text-white/40">
              {isZh ? '何时启用' : 'Activated when'}
            </dt>
            <dd className="mt-1 text-white/80">{copy.rationale.when}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wider text-white/40">
              {isZh ? '你能得到' : 'What you get'}
            </dt>
            <dd className="mt-1 text-white/80">{copy.rationale.benefit}</dd>
          </div>
        </dl>

        <div className="mt-6 flex flex-col gap-2">
          <button
            onClick={onAccept}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[14px] bg-[#0A84FF] px-4 py-[13px] text-[15px] font-semibold text-white transition-colors active:bg-[#0A84FF]/80"
          >
            {copy.rationale.action}
          </button>
          <button
            onClick={onSkip}
            className="inline-flex w-full items-center justify-center rounded-[12px] px-4 py-3 text-[14px] text-white/50 transition-colors hover:text-white/80"
          >
            {copy.rationale.skip}
          </button>
        </div>
      </div>
    </div>
  )
}
