import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Lock, ShieldCheck, ShieldOff, Unlock } from 'lucide-react'
import {
  ADMIN_PIN_MAX_LENGTH,
  ADMIN_PIN_MIN_LENGTH,
  ADMIN_UNLOCK_DURATION_MS,
  getAdminUnlockExpiry,
  isAdminPinConfigured,
  isAdminUnlocked,
  isPinFormatValid,
  lockAdmin,
  setAdminPin,
  unlockAdmin,
} from '../../lib/adminAuth'

const TICK_INTERVAL_MS = 30 * 1000

function formatRemaining(ms) {
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

/**
 * Gates `children` behind a numeric PIN held only on this device.
 * Use to wrap admin-only panels (e.g. project/site/route management) so
 * a lost APK cannot be used to delete field data.
 */
export default function AdminGate({ locale = 'zh', title, description, children }) {
  const isZh = locale === 'zh'
  const t = useMemo(() => ({
    title: title || (isZh ? '后台管理（受保护）' : 'Admin (protected)'),
    description: description || (isZh
      ? '项目、站点和路线的增删改受 PIN 保护，避免 APK 落入野外人员手中后误删数据。解锁后将保持 30 分钟有效。'
      : 'Project, site, and route changes require a PIN. This prevents accidental deletion when the APK is used by field staff. Unlock lasts 30 minutes.'),
    setupPrompt: isZh ? '尚未设定管理员 PIN，请先设定一个 4-12 位数字 PIN。' : 'No admin PIN configured. Set a 4-12 digit numeric PIN to continue.',
    pinPlaceholder: isZh ? '4-12 位数字 PIN' : '4-12 digit PIN',
    confirmPlaceholder: isZh ? '再输入一次确认' : 'Confirm PIN',
    setPin: isZh ? '设定 PIN' : 'Set PIN',
    unlock: isZh ? '解锁' : 'Unlock',
    locked: isZh ? '已锁定' : 'Locked',
    unlocked: isZh ? '已解锁' : 'Unlocked',
    lockNow: isZh ? '立即锁定' : 'Lock now',
    pinFormatError: isZh ? 'PIN 必须是 4-12 位数字。' : 'PIN must be 4-12 digits.',
    pinMismatch: isZh ? '两次输入不一致。' : 'PIN entries do not match.',
    unlockMismatch: isZh ? 'PIN 错误，请重试。' : 'Incorrect PIN, please try again.',
    storageError: isZh ? '无法保存 PIN（localStorage 异常）。' : 'Failed to persist PIN (localStorage error).',
    expiresIn: isZh ? '剩余 ' : 'Expires in ',
    minute: isZh ? ' 分钟' : '',
  }), [isZh, title, description])

  const [hasPin, setHasPin] = useState(() => isAdminPinConfigured())
  const [unlocked, setUnlocked] = useState(() => isAdminUnlocked())
  const [expiresAt, setExpiresAt] = useState(() => getAdminUnlockExpiry())
  const [pin, setPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const tickRef = useRef(null)

  const refreshState = useCallback(() => {
    setHasPin(isAdminPinConfigured())
    const stillUnlocked = isAdminUnlocked()
    setUnlocked(stillUnlocked)
    setExpiresAt(stillUnlocked ? getAdminUnlockExpiry() : null)
  }, [])

  useEffect(() => {
    if (!unlocked) return undefined
    tickRef.current = setInterval(refreshState, TICK_INTERVAL_MS)
    return () => {
      if (tickRef.current) clearInterval(tickRef.current)
    }
  }, [unlocked, refreshState])

  useEffect(() => {
    function onVisibility() { refreshState() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [refreshState])

  async function handleSetPin() {
    setError('')
    if (!isPinFormatValid(pin)) { setError(t.pinFormatError); return }
    if (pin !== confirmPin) { setError(t.pinMismatch); return }
    setBusy(true)
    try {
      await setAdminPin(pin)
      setPin(''); setConfirmPin('')
      refreshState()
    } catch (err) {
      setError(err.code === 'pin-format' ? t.pinFormatError : t.storageError)
    } finally {
      setBusy(false)
    }
  }

  async function handleUnlock() {
    setError('')
    if (!isPinFormatValid(pin)) { setError(t.pinFormatError); return }
    setBusy(true)
    try {
      await unlockAdmin(pin)
      setPin('')
      refreshState()
    } catch (err) {
      setError(err.code === 'mismatch' ? t.unlockMismatch
        : err.code === 'pin-format' ? t.pinFormatError
        : t.storageError)
    } finally {
      setBusy(false)
    }
  }

  function handleLockNow() {
    lockAdmin()
    refreshState()
  }

  if (unlocked) {
    const remainingMs = (expiresAt || 0) - Date.now()
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 rounded-2xl border border-[#30D158]/25 bg-[#30D158]/10 px-3 py-2 text-[12px] text-[#30D158]">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span className="font-medium">{t.unlocked}</span>
          <span className="text-[#30D158]/70">·</span>
          <span className="text-[#30D158]/70">{t.expiresIn}{formatRemaining(remainingMs)}{t.minute}</span>
          <button
            type="button"
            onClick={handleLockNow}
            className="ml-auto inline-flex items-center gap-1 rounded-md bg-[#30D158]/20 px-2 py-0.5 text-[11px] font-medium text-[#30D158] active:bg-[#30D158]/30"
          >
            <Lock className="h-3 w-3" /> {t.lockNow}
          </button>
        </div>
        {children}
      </div>
    )
  }

  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#FF9F0A]/15">
          <ShieldOff className="h-4 w-4 text-[#FF9F0A]" />
        </div>
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-white">{t.title}</h3>
          <p className="text-[12px] text-white/40">{t.description}</p>
        </div>
      </div>

      {!hasPin && (
        <div className="rounded-[12px] bg-[#FF9F0A]/10 px-3 py-2 text-[12px] text-[#FF9F0A]">{t.setupPrompt}</div>
      )}

      <div className="space-y-2">
        <input
          type="password"
          inputMode="numeric"
          autoComplete="off"
          maxLength={ADMIN_PIN_MAX_LENGTH}
          minLength={ADMIN_PIN_MIN_LENGTH}
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
          placeholder={t.pinPlaceholder}
          className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[10px] text-[14px] tracking-[0.4em] text-white placeholder:text-white/20 placeholder:tracking-normal"
        />
        {!hasPin && (
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={ADMIN_PIN_MAX_LENGTH}
            minLength={ADMIN_PIN_MIN_LENGTH}
            value={confirmPin}
            onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ''))}
            placeholder={t.confirmPlaceholder}
            className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[10px] text-[14px] tracking-[0.4em] text-white placeholder:text-white/20 placeholder:tracking-normal"
          />
        )}
        {error && (
          <div className="rounded-[10px] bg-[#FF453A]/10 px-3 py-2 text-[12px] text-[#FF453A]">{error}</div>
        )}
        <button
          type="button"
          onClick={hasPin ? handleUnlock : handleSetPin}
          disabled={busy || !pin || (!hasPin && pin !== confirmPin)}
          className="inline-flex items-center gap-2 rounded-[10px] bg-[#0A84FF] px-4 py-[10px] text-[14px] font-medium text-white active:bg-[#0A84FF]/85 disabled:opacity-40"
        >
          {hasPin ? <Unlock className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
          {hasPin ? t.unlock : t.setPin}
        </button>
      </div>
    </div>
  )
}

export const ADMIN_UNLOCK_DURATION = ADMIN_UNLOCK_DURATION_MS
