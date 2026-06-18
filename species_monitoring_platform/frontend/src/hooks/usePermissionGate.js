import { useCallback, useRef, useState } from 'react'

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
  // Holds the pending promise resolver while the rationale modal is open
  // so `gateCheck()` can return a single boolean to the calling hook
  // (camera / audio / geolocation) after the user clicks Accept or Skip.
  const pendingResolverRef = useRef(null)

  const settleGateCheck = useCallback((result) => {
    const resolver = pendingResolverRef.current
    pendingResolverRef.current = null
    if (resolver) resolver(result)
  }, [])

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
        settleGateCheck(true)
        return 'granted'
      }
      if (result === 'blocked' || result === 'permanently-denied') {
        setStatus('blocked')
        settleGateCheck(false)
        return 'blocked'
      }
      setStatus('denied')
      settleGateCheck(false)
      return 'denied'
    } catch {
      setStatus('denied')
      settleGateCheck(false)
      return 'denied'
    }
  }, [request, settleGateCheck])

  const skip = useCallback(() => {
    setStatus('denied')
    settleGateCheck(false)
  }, [settleGateCheck])

  const reset = useCallback(() => {
    setStatus('pristine')
    settleGateCheck(false)
  }, [settleGateCheck])

  /**
   * Returns an `async () => boolean` that the capture hooks (camera /
   * audio / geolocation) can `await` before invoking native APIs.
   *
   * Behaviour:
   *   - already granted   → resolves `true` immediately, no UI shown
   *   - already blocked / denied (user previously refused) → resolves `false`
   *     immediately, no UI shown again (consumers should render
   *     PermissionDeniedFallback in that branch)
   *   - pristine / prompting / pending → shows the rationale modal by
   *     flipping `status` to 'prompting'; the returned promise resolves
   *     when the user clicks Accept / Skip in `<PermissionRationaleModal>`,
   *     which call `gate.accept()` / `gate.skip()` respectively.
   *
   * Only one pending gate check is allowed at a time. Calling
   * `createGateCheck()` while another is in flight settles the earlier
   * promise with `false` (treat as cancel) to avoid leaked resolvers.
   */
  const createGateCheck = useCallback(() => {
    return async function gateCheck() {
      if (status === 'granted') return true
      if (status === 'blocked' || status === 'denied') return false
      // Cancel any in-flight gate check before starting a new one.
      settleGateCheck(false)
      const pending = new Promise((resolve) => {
        pendingResolverRef.current = resolve
      })
      setStatus('prompting')
      return pending
    }
  }, [status, settleGateCheck])

  return {
    permissionId,
    status,
    requestPermission,
    accept,
    skip,
    reset,
    createGateCheck,
  }
}
