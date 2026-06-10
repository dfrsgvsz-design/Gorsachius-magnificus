import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getSurveyDesignAssets,
  getSurveyProtocols,
  getSurveyTaxonomyPackages,
  getApiErrorMessage,
  pullSurveySync,
  pushSurveySync,
} from '../lib/api'
import {
  applySyncResult,
  collectAppliedSyncKeys,
  collectConflictSyncKeys,
  dedupeSyncOperations,
  mergeOutboxIntoState,
  mergeSyncPull,
} from '../lib/surveyOffline'
import { buildLocalPullSnapshot } from '../lib/localSurveyService'
import {
  OUTBOX_CHANGED_EVENT,
  clearOutboxByEntityKeys,
  ensureSchema,
  listOutbox,
  markOutboxConflicts,
} from '../lib/localStore'
import { toArray } from '../components/fieldops/fieldOpsUtils'

/**
 * Sync engine hook: network state, pull/push sync, bootstrap hydration,
 * and remote protocol fetch.
 *
 * Extracted from FieldOpsTab.jsx (handlePullSync, handlePushSync,
 * bootstrap useEffect, network useEffect, protocol fetch useEffect).
 */
export default function useSyncEngine({
  surveyState,
  setSurveyState,
  protocolDefinition,
  activeVertebrateSubmoduleId,
  exportJurisdiction,
  currentProjectId,
  currentSiteId,
  setError,
}) {
  const [networkOnline, setNetworkOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine,
  )
  const [loadingSync, setLoadingSync] = useState(false)
  const [bootstrapReady, setBootstrapReady] = useState(false)
  const hydratedRef = useRef(false)
  const isOnline = networkOnline

  // ── Network online/offline listeners ──

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleOnline = () => setNetworkOnline(true)
    const handleOffline = () => setNetworkOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // ── Durable outbox → in-memory queue mirror (B24) ──
  //
  // Mutations made outside the FieldOps state tree (ProjectManagementPanel,
  // ObservationListPanel, trash restore) land in the SQLite outbox. Mirror
  // them into surveyState.syncQueue so badges/push buttons stay accurate.

  const refreshQueueFromOutbox = useCallback(async () => {
    try {
      const outboxOps = await listOutbox()
      if (outboxOps.length === 0) return
      setSurveyState((current) => mergeOutboxIntoState(current, outboxOps))
    } catch (err) {
      console.warn('[useSyncEngine] outbox mirror failed', err)
    }
  }, [setSurveyState])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleOutboxChanged = () => {
      refreshQueueFromOutbox()
    }
    window.addEventListener(OUTBOX_CHANGED_EVENT, handleOutboxChanged)
    return () => {
      window.removeEventListener(OUTBOX_CHANGED_EVENT, handleOutboxChanged)
    }
  }, [refreshQueueFromOutbox])

  // ── Remote protocol fetch ──

  useEffect(() => {
    if (!networkOnline) return
    let cancelled = false

    getSurveyProtocols()
      .then((data) => {
        if (cancelled || !Array.isArray(data?.protocols) || data.protocols.length === 0) return
        setSurveyState((current) => ({ ...current, protocols: data.protocols }))
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [networkOnline, setSurveyState])

  // ── Pull sync ──

  const handlePullSync = useCallback(async () => {
    if (!isOnline) return
    setLoadingSync(true)
    setError(null)
    try {
      // Promise.allSettled instead of Promise.all so a transient failure on
      // one endpoint (e.g. team A's taxonomy service hiccups) does not wipe
      // out the survey rows that pulled successfully. Each fulfilled response
      // is applied independently; failures are aggregated into one error
      // banner that names the endpoints that actually went wrong.
      const designAssetPromise = currentProjectId
        ? getSurveyDesignAssets({
          project_id: currentProjectId,
          site_id: currentSiteId,
          program: protocolDefinition.program,
          submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '',
          protocol: protocolDefinition.id,
        })
        : Promise.resolve({ design_assets: [] })
      const settled = await Promise.allSettled([
        pullSurveySync(surveyState.syncMeta?.lastPulledAt || ''),
        getSurveyProtocols({ program: protocolDefinition.program }),
        getSurveyTaxonomyPackages({
          jurisdiction: exportJurisdiction,
          program: protocolDefinition.program,
          protocol: protocolDefinition.id,
        }),
        designAssetPromise,
      ])
      const labels = ['survey', 'protocols', 'taxonomy', 'design_assets']
      const fulfilled = settled.map((entry) => (entry.status === 'fulfilled' ? entry.value : null))
      const failures = settled
        .map((entry, index) => (entry.status === 'rejected' ? { label: labels[index], reason: entry.reason } : null))
        .filter(Boolean)
      const [pulled, protocolResponse, taxonomyResponse, designAssetResponse] = fulfilled
      if (pulled || protocolResponse || taxonomyResponse || designAssetResponse) {
        const mergedPull = {
          ...(pulled || {}),
          protocols: toArray(protocolResponse?.protocols),
          taxonomy_packages: toArray(taxonomyResponse?.packages),
          design_assets: [
            ...toArray(pulled?.design_assets),
            ...toArray(designAssetResponse?.design_assets),
          ],
          active_program: protocolDefinition.program,
          active_protocol: protocolDefinition.id,
          active_vertebrate_submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '',
          active_jurisdiction: exportJurisdiction,
        }
        setSurveyState((current) => mergeSyncPull(current, mergedPull))
      }
      if (failures.length > 0) {
        const detail = failures
          .map(({ label, reason }) => `${label}: ${getApiErrorMessage(reason, 'unknown')}`)
          .join(' · ')
        setError(`Partial pull (${failures.length} of ${settled.length} endpoints failed): ${detail}`)
      }
    } catch (err) {
      // Should be unreachable now that Promise.allSettled never rejects, but
      // we keep the guard so an unexpected throw in the assembly code does
      // not silently break the UI.
      setError(getApiErrorMessage(err, 'Unable to pull survey data.'))
    } finally {
      setLoadingSync(false)
    }
  }, [
    isOnline,
    surveyState.syncMeta?.lastPulledAt,
    protocolDefinition.program,
    protocolDefinition.id,
    exportJurisdiction,
    currentProjectId,
    currentSiteId,
    activeVertebrateSubmoduleId,
    setSurveyState,
    setError,
  ])

  // ── Push sync ──

  const handlePushSync = useCallback(async () => {
    if (!isOnline) return
    setLoadingSync(true)
    setError(null)
    try {
      // Combine the in-memory queue with the durable SQLite outbox (B24) so
      // mutations from ProjectManagementPanel / ObservationListPanel / trash
      // restore — which never touch surveyState — still reach the backend.
      let outboxOps = []
      try {
        outboxOps = await listOutbox()
      } catch (err) {
        console.warn('[useSyncEngine] outbox read failed, pushing state queue only', err)
      }
      const operations = dedupeSyncOperations([
        ...(surveyState.syncQueue || []),
        ...outboxOps,
      ])
      if (operations.length === 0) return
      const response = await pushSurveySync({
        device_id: surveyState.syncMeta?.deviceId || 'field-device-web',
        user_id: 'field-user-web',
        operations: operations.map((operation) => ({
          entity_type: operation.entity_type,
          operation: operation.operation,
          entity_id: operation.entity_id,
          payload: operation.payload,
        })),
      })
      setSurveyState((current) => applySyncResult(current, response.sync_job))
      try {
        await clearOutboxByEntityKeys(collectAppliedSyncKeys(response.sync_job))
        await markOutboxConflicts(collectConflictSyncKeys(response.sync_job))
      } catch (err) {
        // Worst case the same ops are pushed again next time — the server
        // upsert path is idempotent for identical payloads.
        console.warn('[useSyncEngine] outbox cleanup failed', err)
      }
      // Best-effort freshness pull. Isolated from the outer try/catch so a
      // network blip AFTER a successful push does not overwrite the just-
      // applied 'synced' lastStatus with an 'error' one (which would mislead
      // the surveyor into thinking their push failed).
      try {
        const pulled = await pullSurveySync('')
        setSurveyState((current) => mergeSyncPull(current, pulled))
      } catch (pullErr) {
        console.warn('[useSyncEngine] post-push refresh pull failed', pullErr)
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to push queued field data.'))
      setSurveyState((current) => ({
        ...current,
        syncMeta: {
          ...(current.syncMeta || {}),
          lastStatus: 'error',
          lastError: getApiErrorMessage(err, 'Unable to push queued field data.'),
        },
      }))
    } finally {
      setLoadingSync(false)
    }
  }, [
    isOnline,
    surveyState.syncQueue,
    surveyState.syncMeta?.deviceId,
    setSurveyState,
    setError,
  ])

  // ── Bootstrap hydration ──
  //
  // Phase 1 (always): hydrate React state from on-device SQLite. This works
  //   offline and is the reason the app boots into a usable form even when
  //   the backend is unreachable.
  // Phase 2 (online only): pull incremental updates from the remote backend
  //   on top of the local snapshot. Failures here do NOT prevent the app
  //   from becoming ready — local data already populated state.

  useEffect(() => {
    let cancelled = false

    async function bootstrapSurveyState() {
      // Phase 1 — local SQLite hydrate (offline-friendly).
      try {
        await ensureSchema()
        const localSnapshot = await buildLocalPullSnapshot()
        if (!cancelled) {
          setSurveyState((current) => mergeSyncPull(current, localSnapshot))
        }
        // Replay pending mutations recorded in the durable outbox (B24) into
        // the in-memory queue — survives restarts and localStorage quota
        // failures, and covers non-FieldOps mutation surfaces.
        if (!cancelled) {
          await refreshQueueFromOutbox()
        }
      } catch (err) {
        // Local hydrate failure should never block the app. Log + carry on.
        console.warn('[useSyncEngine] local hydrate failed', err)
      }

      if (!isOnline) {
        if (!cancelled) setBootstrapReady(true)
        return
      }
      if (hydratedRef.current) {
        if (!cancelled) setBootstrapReady(true)
        return
      }
      hydratedRef.current = true

      // Phase 2 — best-effort remote pull. Errors stay confined to handlePullSync.
      try {
        await handlePullSync()
      } finally {
        if (!cancelled) setBootstrapReady(true)
      }
    }

    bootstrapSurveyState()
    return () => {
      cancelled = true
    }
  }, [isOnline, handlePullSync, refreshQueueFromOutbox, setSurveyState])

  return {
    isOnline,
    networkOnline,
    loadingSync,
    bootstrapReady,
    handlePullSync,
    handlePushSync,
  }
}
