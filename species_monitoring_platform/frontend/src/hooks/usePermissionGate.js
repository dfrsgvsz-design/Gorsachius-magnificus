import { useCallback, useState } from 'react'

/**
 * Pure state machine for a single permission gate sequence.
 *
 *   pristine  → user has not yet been asked
 *   prompting → rationale modal is visible, waiting for accept/skip
 *   pending   → OS-level permission dialog is in flight (between accept and
 *               native callback)
 *   granted   → native side returned a granted state
 *   denied    → user skipped the rationale OR the OS denied
 *   blocked   → "Don't ask again" path — the only way out is system settings
 *
 * Exported so a unit test can drive every transition without React.
 *
 * @param {'pristine'|'prompting'|'pending'|'granted'|'denied'|'blocked'} current
 * @param {string} event
 * @returns {string} next state
 */
export function reducePermissionGateState(current, event) {
  switch (event) {
    case 'request':
      return current === 'granted' ? 'granted' : 'prompting'
    case 'accept':
      return current === 'prompting' ? 'pending' : current
    case 'skip':
      return current === 'prompting' ? 'denied' : current
    case 'native_granted':
      return 'granted'
    case 'native_denied':
      return 'denied'
    case 'native_blocked':
      return 'blocked'
    case 'reset':
      return 'pristine'
    default:
      return current
  }
}

/**
 * React hook for gating an OS permission behind a context-rich rationale.
 *
 * Usage:
 *
 *   const { status, requestPermission, accept, skip } = usePermissionGate({
 *     permissionId: 'camera',
 *     check: () => Camera.checkPermissions().then((r) => r.camera),
 *     request: () => Camera.requestPermissions({ permissions: ['camera'] })
 *       .then((r) => r.camera),
 *   })
 *
 * Wrap `<PermissionRationaleModal>` around `status === 'prompting'` and call
 * `accept()` from its CTA. The hook keeps the OS prompt off until after the
 * user has acknowledged the rationale.
 *
 * `check` and `request` should each resolve to one of:
 *   - 'granted'
 *   - 'denied'
 *   - 'prompt' / 'prompt-with-rationale' (treated as not-yet-granted)
 *   - 'blocked' / 'permanently-denied' (denied with "Don't ask again")
 */
export default function usePermissionGate({ permissionId, check, request }) {
  const [status, setStatus] = useState('pristine')

  const requestPermission = useCallback(async () => {
    setStatus('prompting')
    try {
      const current = await check?.()
      if (current === 'granted') {
        setStatus('granted')
        return 'granted'
      }
    } catch {
      // Treat check failures as "needs rationale".
    }
    return 'prompting'
  }, [check])

  const accept = useCallback(async () => {
    setStatus('pending')
    try {
      const result = await request?.()
      if (result === 'granted') {
        setStatus('granted')
        return 'granted'
      }
      if (result === 'blocked' || result === 'permanently-denied') {
        setStatus('blocked')
        return 'blocked'
      }
      setStatus('denied')
      return 'denied'
    } catch {
      setStatus('denied')
      return 'denied'
    }
  }, [request])

  const skip = useCallback(() => {
    setStatus('denied')
  }, [])

  const reset = useCallback(() => {
    setStatus('pristine')
  }, [])

  return {
    permissionId,
    status,
    requestPermission,
    accept,
    skip,
    reset,
  }
}
