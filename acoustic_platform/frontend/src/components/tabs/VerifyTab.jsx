import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Filter,
  ListChecks,
  RefreshCw,
  Search,
  Shield,
  TriangleAlert,
  UserRound,
  X,
} from 'lucide-react'
import {
  batchVerifyDetections,
  getApiErrorMessage,
  getDetectionStats,
  getOccupancyData,
  getSessionDetections,
  getSiteDetections,
  getUnverifiedDetections,
  verifyDetection,
} from '../../lib/api'
import { LoadingState, StatCard, StatusBanner } from '../common'

function formatPercent(value) {
  return `${((value || 0) * 100).toFixed(1)}%`
}

function formatTimeOffset(detection) {
  if (detection.time_start != null) {
    return `${Number(detection.time_start).toFixed(1)}s - ${Number(detection.time_end ?? detection.time_start).toFixed(1)}s`
  }
  if (detection.time_offset != null) {
    return `${Number(detection.time_offset).toFixed(1)}s`
  }
  return '--'
}

function confidenceBand(confidence) {
  if (confidence >= 0.7) return 'high'
  if (confidence >= 0.4) return 'mid'
  return 'low'
}

export default function VerifyTab() {
  const { t } = useTranslation()
  const [detections, setDetections] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [submittingId, setSubmittingId] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [query, setQuery] = useState('')
  const [band, setBand] = useState('all')
  const [onlyNovel, setOnlyNovel] = useState(false)
  const [reviewerName, setReviewerName] = useState('field-reviewer')
  const [reviewNotes, setReviewNotes] = useState('')
  const [context, setContext] = useState({
    loading: false,
    session: null,
    site: null,
    occupancy: null,
  })

  const loadData = useCallback(async () => {
    setError(null)
    setRefreshing(true)
    try {
      const [pending, summary] = await Promise.all([getUnverifiedDetections(), getDetectionStats()])
      const items = Array.isArray(pending) ? pending : []
      setDetections(items)
      setStats(summary || null)
      setLastUpdated(Date.now())
      setSelectedIds((prev) => prev.filter((id) => items.some((item) => item.detection_id === id)))
      setActiveId((prev) => (items.some((item) => item.detection_id === prev) ? prev : items[0]?.detection_id || null))
    } catch (err) {
      setError(getApiErrorMessage(err, t('verifyPage.loadFailed')))
    } finally {
      setRefreshing(false)
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadData()
  }, [loadData])

  const filteredDetections = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return detections.filter((item) => {
      const matchesQuery = !normalizedQuery || [
        item.species_chinese,
        item.species_scientific,
        item.species_english,
        item.site_name,
        item.device_id,
        item.session_id,
      ].some((value) => String(value || '').toLowerCase().includes(normalizedQuery))

      const matchesBand = band === 'all' || confidenceBand(item.confidence || 0) === band
      const matchesNovel = !onlyNovel || Boolean(item._meta?.ood_detected)
      return matchesQuery && matchesBand && matchesNovel
    })
  }, [band, detections, onlyNovel, query])

  useEffect(() => {
    if (!filteredDetections.length) {
      setActiveId(null)
      return
    }
    if (!filteredDetections.some((item) => item.detection_id === activeId)) {
      setActiveId(filteredDetections[0].detection_id)
    }
  }, [activeId, filteredDetections])

  const activeDetection = useMemo(
    () => filteredDetections.find((item) => item.detection_id === activeId)
      || detections.find((item) => item.detection_id === activeId)
      || null,
    [activeId, detections, filteredDetections],
  )

  useEffect(() => {
    let cancelled = false

    async function loadContext() {
      if (!activeDetection?.session_id || !activeDetection?.site_name || !activeDetection?.species) {
        setContext({
          loading: false,
          session: null,
          site: null,
          occupancy: null,
        })
        return
      }

      setContext((prev) => ({ ...prev, loading: true }))
      try {
        const [session, site, occupancy] = await Promise.all([
          getSessionDetections(activeDetection.session_id),
          getSiteDetections(activeDetection.site_name),
          getOccupancyData(activeDetection.site_name, activeDetection.species),
        ])
        if (!cancelled) {
          setContext({
            loading: false,
            session,
            site,
            occupancy,
          })
        }
      } catch {
        if (!cancelled) {
          setContext({
            loading: false,
            session: null,
            site: null,
            occupancy: null,
          })
        }
      }
    }

    loadContext()
    return () => {
      cancelled = true
    }
  }, [activeDetection])

  const queueSummary = useMemo(() => {
    const highConfidence = detections.filter((item) => (item.confidence || 0) >= 0.7).length
    const flaggedAsNovel = detections.filter((item) => item._meta?.ood_detected).length
    return { highConfidence, flaggedAsNovel }
  }, [detections])

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const selectedCount = selectedIds.length
  const allFilteredSelected = filteredDetections.length > 0
    && filteredDetections.every((item) => selectedSet.has(item.detection_id))

  const lastUpdatedLabel = lastUpdated
    ? new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(lastUpdated))
    : '--:--:--'

  const applyLocalVerification = useCallback((ids, status) => {
    setDetections((prev) => prev.filter((item) => !ids.includes(item.detection_id)))
    setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)))
    setActiveId((prev) => (ids.includes(prev) ? null : prev))
    setStats((prev) => {
      if (!prev) return prev
      const next = { ...prev }
      next.unverified = Math.max(0, (next.unverified || 0) - ids.length)
      if (status === 'confirmed') next.confirmed = (next.confirmed || 0) + ids.length
      if (status === 'rejected') next.rejected = (next.rejected || 0) + ids.length
      if (status === 'uncertain') next.uncertain = (next.uncertain || 0) + ids.length
      const reviewed = (next.confirmed || 0) + (next.rejected || 0) + (next.uncertain || 0)
      next.verification_rate = next.total ? reviewed / next.total : 0
      return next
    })
  }, [])

  const handleVerify = async (detectionId, status) => {
    setSubmittingId(detectionId)
    setError(null)
    try {
      await verifyDetection(detectionId, status, reviewerName || 'anonymous', reviewNotes)
      applyLocalVerification([detectionId], status)
    } catch (err) {
      setError(getApiErrorMessage(err, t('verifyPage.verificationFailed')))
    } finally {
      setSubmittingId(null)
    }
  }

  const handleBatchVerify = async (status) => {
    if (!selectedIds.length) return
    setSubmittingId(`batch-${status}`)
    setError(null)
    try {
      await batchVerifyDetections(selectedIds, status, reviewerName || 'anonymous', reviewNotes)
      applyLocalVerification(selectedIds, status)
    } catch (err) {
      setError(getApiErrorMessage(err, t('verifyPage.batchVerificationFailed')))
    } finally {
      setSubmittingId(null)
    }
  }

  const toggleSelection = (detectionId) => {
    setSelectedIds((prev) => (
      prev.includes(detectionId)
        ? prev.filter((id) => id !== detectionId)
        : [...prev, detectionId]
    ))
  }

  const toggleAllFiltered = () => {
    if (allFilteredSelected) {
      setSelectedIds((prev) => prev.filter((id) => !filteredDetections.some((item) => item.detection_id === id)))
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...filteredDetections.map((item) => item.detection_id)])))
    }
  }

  if (loading) return <LoadingState text={t('verifyPage.loading')} />

  return (
    <div className="space-y-6">
      <section className="glass-card space-y-4 p-4 md:space-y-5 md:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 max-w-3xl">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-300 md:gap-2 md:px-3 md:py-1 md:text-xs">
              <Shield className="h-3 w-3 md:h-3.5 md:w-3.5" />
              {t('verifyPage.badge')}
            </div>
            <h2 className="mt-2 text-lg font-bold text-white md:mt-3 md:text-2xl">{t('verifyPage.title')}</h2>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-gray-300 md:mt-2 md:text-sm md:leading-6">
              {t('verifyPage.body')}
            </p>
          </div>

          <button
            onClick={loadData}
            disabled={refreshing}
            className="touch-button flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-2 text-[11px] text-gray-300 active:scale-[0.97] md:gap-2 md:px-3 md:text-xs"
          >
            <RefreshCw className={`h-3 w-3 md:h-3.5 md:w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{refreshing ? t('verifyPage.refreshing') : t('verifyPage.refreshQueue')}</span>
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 md:grid-cols-2 md:gap-4 xl:grid-cols-4">
          <StatCard label={t('verifyPage.pendingReview')} value={detections.length} icon={AlertCircle} color="amber" />
          <StatCard label={t('verifyPage.selected')} value={selectedCount} icon={ListChecks} color="blue" />
          <StatCard label={t('verifyPage.noveltyFlagged')} value={queueSummary.flaggedAsNovel} icon={TriangleAlert} color="carnelian" />
          <StatCard label={t('verifyPage.verificationRate')} value={formatPercent(stats?.verification_rate)} icon={CheckCircle2} color="forest" />
        </div>

        <div className="grid gap-3 md:gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-2 rounded-xl border border-white/10 bg-white/5 p-3 md:space-y-3 md:rounded-2xl md:p-4">
            <div className="flex items-center gap-2 text-xs font-medium text-white md:text-sm">
              <Filter className="h-3.5 w-3.5 text-cyan-400 md:h-4 md:w-4" />
              {t('verifyPage.filterQueue')}
            </div>
            <div className="grid gap-2 md:grid-cols-2 md:gap-3 xl:grid-cols-3">
              <label className="space-y-1 md:space-y-2">
                <span className="text-[10px] uppercase tracking-[0.14em] text-gray-500 md:text-xs md:tracking-[0.16em]">{t('verifyPage.search')}</span>
                <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
                  <Search className="h-3.5 w-3.5 text-gray-500 md:h-4 md:w-4" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={t('verifyPage.searchPlaceholder')}
                    className="touch-button w-full bg-transparent text-sm text-white outline-none placeholder:text-gray-500"
                  />
                </div>
              </label>

              <label className="space-y-1 md:space-y-2">
                <span className="text-[10px] uppercase tracking-[0.14em] text-gray-500 md:text-xs md:tracking-[0.16em]">{t('verifyPage.confidenceBand')}</span>
                <select
                  value={band}
                  onChange={(event) => setBand(event.target.value)}
                  className="touch-button w-full rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm text-white outline-none"
                >
                  <option value="all">{t('verifyPage.bandAll')}</option>
                  <option value="low">{t('verifyPage.bandLow')}</option>
                  <option value="mid">{t('verifyPage.bandMid')}</option>
                  <option value="high">{t('verifyPage.bandHigh')}</option>
                </select>
              </label>

              <label className="touch-button flex items-center gap-3 rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2.5 text-xs text-gray-300 md:py-3 md:text-sm">
                <input
                  type="checkbox"
                  checked={onlyNovel}
                  onChange={(event) => setOnlyNovel(event.target.checked)}
                  className="h-4 w-4 rounded border-white/20 bg-transparent"
                />
                {t('verifyPage.onlyNovel')}
              </label>
            </div>
          </div>

          <div className="space-y-2 rounded-xl border border-white/10 bg-white/5 p-3 md:space-y-3 md:rounded-2xl md:p-4">
            <div className="flex items-center gap-2 text-xs font-medium text-white md:text-sm">
              <UserRound className="h-3.5 w-3.5 text-emerald-400 md:h-4 md:w-4" />
              {t('verifyPage.reviewerMeta')}
            </div>
            <div className="grid gap-2 md:gap-3">
              <label className="space-y-1 md:space-y-2">
                <span className="text-[10px] uppercase tracking-[0.14em] text-gray-500 md:text-xs md:tracking-[0.16em]">{t('verifyPage.reviewer')}</span>
                <input
                  value={reviewerName}
                  onChange={(event) => setReviewerName(event.target.value)}
                  className="touch-button w-full rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm text-white outline-none"
                  placeholder={t('verifyPage.reviewerPlaceholder')}
                />
              </label>
              <label className="space-y-1 md:space-y-2">
                <span className="text-[10px] uppercase tracking-[0.14em] text-gray-500 md:text-xs md:tracking-[0.16em]">{t('verifyPage.sharedNote')}</span>
                <textarea
                  value={reviewNotes}
                  onChange={(event) => setReviewNotes(event.target.value)}
                  rows={2}
                  className="w-full rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm text-white outline-none"
                  placeholder={t('verifyPage.sharedNotePlaceholder')}
                />
              </label>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-400 md:gap-3 md:text-xs">
          <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 md:px-3 md:py-1">{t('verifyPage.lastSync', { time: lastUpdatedLabel })}</span>
          <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 md:px-3 md:py-1">{t('verifyPage.filterMatches', { count: filteredDetections.length })}</span>
          <span className="hidden rounded-full border border-white/10 bg-white/5 px-2 py-0.5 sm:inline-block md:px-3 md:py-1">{t('verifyPage.highConfidenceAwaiting', { count: queueSummary.highConfidence })}</span>
        </div>
      </section>

      <StatusBanner tone="error" message={error} />

      {selectedCount > 0 && (
        <section className="glass-card flex flex-col gap-2 p-3 md:flex-row md:items-center md:justify-between md:gap-3 md:p-4 lg:flex-row">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-white md:text-sm">{t('verifyPage.selectedRecords', { count: selectedCount })}</p>
            <p className="text-[11px] text-gray-400 md:text-xs">{t('verifyPage.selectedHint')}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleBatchVerify('confirmed')}
              disabled={submittingId === 'batch-confirmed'}
              className="touch-button flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-emerald-500/30 bg-emerald-500/20 px-3 py-2 text-xs font-medium text-emerald-300 active:scale-[0.97] disabled:opacity-60 md:flex-none md:px-4 md:text-sm"
            >
              <Check className="h-3.5 w-3.5 md:h-4 md:w-4" />
              {submittingId === 'batch-confirmed' ? t('verifyPage.confirmingSelected') : t('verifyPage.confirmSelected')}
            </button>
            <button
              onClick={() => handleBatchVerify('rejected')}
              disabled={submittingId === 'batch-rejected'}
              className="touch-button flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-red-500/30 bg-red-500/15 px-3 py-2 text-xs font-medium text-red-300 active:scale-[0.97] disabled:opacity-60 md:flex-none md:px-4 md:text-sm"
            >
              <X className="h-3.5 w-3.5 md:h-4 md:w-4" />
              {submittingId === 'batch-rejected' ? t('verifyPage.rejectingSelected') : t('verifyPage.rejectSelected')}
            </button>
          </div>
        </section>
      )}

      <section className="grid gap-4 md:gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-2 md:space-y-3">
          <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 md:rounded-2xl md:px-4 md:py-3">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-white md:text-sm">{t('verifyPage.queueTitle')}</p>
              <p className="text-[11px] text-gray-400 md:text-xs">{t('verifyPage.queueHint')}</p>
            </div>
            <label className="flex shrink-0 items-center gap-1.5 text-[11px] text-gray-300 md:gap-2 md:text-xs">
              <input
                type="checkbox"
                checked={allFilteredSelected}
                onChange={toggleAllFiltered}
                className="h-4 w-4 rounded border-white/20 bg-transparent"
              />
              <span className="hidden sm:inline">{t('verifyPage.selectAllFiltered')}</span>
            </label>
          </div>

          {filteredDetections.length === 0 ? (
            <div className="glass-card py-10 text-center text-gray-500 md:py-14">
              <Shield className="mx-auto mb-2 h-8 w-8 opacity-30 md:mb-3 md:h-10 md:w-10" />
              <p className="text-xs text-gray-300 md:text-sm">{t('verifyPage.noMatches')}</p>
              <p className="mt-1 text-[11px] text-gray-500 md:text-xs">{t('verifyPage.noMatchesHint')}</p>
            </div>
          ) : (
            filteredDetections.map((detection) => {
              const confidence = detection.confidence || 0
              const tone = confidence >= 0.7
                ? 'text-emerald-400'
                : confidence >= 0.4
                  ? 'text-amber-400'
                  : 'text-red-400'
              const isActive = detection.detection_id === activeId
              const isSelected = selectedSet.has(detection.detection_id)

              return (
                <button
                  key={detection.detection_id}
                  type="button"
                  onClick={() => setActiveId(detection.detection_id)}
                  className={`glass-card w-full p-3 text-left transition-all md:p-5 ${isActive ? 'border-cyan-400/40 bg-cyan-500/5' : ''}`}
                >
                  <div className="space-y-3 xl:flex xl:items-start xl:justify-between xl:gap-4 xl:space-y-0">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 md:gap-3">
                        <label
                          className="flex items-center gap-1.5 text-[11px] text-gray-300 md:gap-2 md:text-xs"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelection(detection.detection_id)}
                            className="h-4 w-4 rounded border-white/20 bg-transparent"
                          />
                        </label>
                        <p className="text-sm font-semibold text-emerald-300 md:text-lg">
                          {detection.species_chinese || detection.species || t('verifyPage.unknownSpecies')}
                        </p>
                        {detection.species_scientific && (
                          <span className="hidden text-sm italic text-gray-500 sm:inline">{detection.species_scientific}</span>
                        )}
                        {detection._meta?.ood_detected && (
                          <span className="rounded-full border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-300 md:px-2.5 md:py-1 md:text-[11px]">
                            {t('verifyPage.novelOod')}
                          </span>
                        )}
                      </div>

                      <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-gray-400 md:mt-3 md:gap-3 md:text-xs">
                        <MetaPill label={t('verifyPage.labels.confidence')} value={<span className={tone}>{formatPercent(confidence)}</span>} />
                        <MetaPill label={t('verifyPage.labels.site')} value={detection.site_name || '--'} />
                        <MetaPill label={t('verifyPage.labels.window')} value={formatTimeOffset(detection)} />
                      </div>
                    </div>

                    <div className="flex gap-2 xl:min-w-[200px] xl:flex-col" onClick={(event) => event.stopPropagation()}>
                      <button
                        onClick={() => handleVerify(detection.detection_id, 'confirmed')}
                        disabled={submittingId === detection.detection_id}
                        className="touch-button flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-emerald-500/30 bg-emerald-500/20 px-3 py-2 text-xs font-medium text-emerald-300 active:scale-[0.97] disabled:opacity-60 md:px-4 md:py-2.5 md:text-sm xl:flex-none"
                      >
                        {submittingId === detection.detection_id ? <RefreshCw className="h-3.5 w-3.5 animate-spin md:h-4 md:w-4" /> : <Check className="h-3.5 w-3.5 md:h-4 md:w-4" />}
                        {t('verifyPage.confirm')}
                      </button>
                      <button
                        onClick={() => handleVerify(detection.detection_id, 'rejected')}
                        disabled={submittingId === detection.detection_id}
                        className="touch-button flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-red-500/30 bg-red-500/15 px-3 py-2 text-xs font-medium text-red-300 active:scale-[0.97] disabled:opacity-60 md:px-4 md:py-2.5 md:text-sm xl:flex-none"
                      >
                        <X className="h-3.5 w-3.5 md:h-4 md:w-4" />
                        {t('verifyPage.reject')}
                      </button>
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>

        <aside className="glass-card h-fit space-y-4 p-5">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-300">{t('verifyPage.inspectorTag')}</p>
            <h3 className="mt-2 text-xl font-semibold text-white">
              {activeDetection
                ? (activeDetection.species_chinese || activeDetection.species || t('verifyPage.detectionDetail'))
                : t('verifyPage.inspectorEmptyTitle')}
            </h3>
            <p className="mt-1 text-sm leading-6 text-gray-400">
              {activeDetection ? t('verifyPage.inspectorBody') : t('verifyPage.inspectorEmptyBody')}
            </p>
          </div>

          {activeDetection ? (
            <>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                <InspectorCard title={t('verifyPage.snapshot')}>
                  <InspectorRow label={t('verifyPage.labels.scientific')} value={activeDetection.species_scientific || activeDetection.species || '--'} />
                  <InspectorRow label={t('verifyPage.labels.confidence')} value={formatPercent(activeDetection.confidence)} />
                  <InspectorRow label={t('verifyPage.labels.site')} value={activeDetection.site_name || '--'} />
                  <InspectorRow label={t('verifyPage.labels.session')} value={activeDetection.session_id || '--'} />
                  <InspectorRow label={t('verifyPage.labels.window')} value={formatTimeOffset(activeDetection)} />
                </InspectorCard>

                <InspectorCard title={t('verifyPage.context')}>
                  {context.loading ? (
                    <p className="text-sm text-gray-400">{t('verifyPage.loadingContext')}</p>
                  ) : (
                    <>
                      <InspectorRow label={t('verifyPage.sessionRecords')} value={context.session?.total ?? '--'} />
                      <InspectorRow label={t('verifyPage.siteRecords')} value={context.site?.total ?? '--'} />
                      <InspectorRow label={t('verifyPage.siteSurveys')} value={context.occupancy?.n_surveys ?? '--'} />
                      <InspectorRow label={t('verifyPage.detectionProbability')} value={context.occupancy ? formatPercent(context.occupancy.detection_probability) : '--'} />
                    </>
                  )}
                </InspectorCard>
              </div>

              {context.occupancy && (
                <InspectorCard title={t('verifyPage.occupancyPreview')}>
                  <div className="flex flex-wrap gap-2">
                    {(context.occupancy.detection_history || []).map((item, index) => (
                      <span
                        key={`${activeDetection.detection_id}-${index}`}
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                          item === 1
                            ? 'border border-emerald-500/30 bg-emerald-500/15 text-emerald-300'
                            : 'border border-white/10 bg-white/5 text-gray-400'
                        }`}
                      >
                        {item === 1
                          ? t('verifyPage.surveyDetected', { index: index + 1 })
                          : t('verifyPage.surveyNotDetected', { index: index + 1 })}
                      </span>
                    ))}
                  </div>
                </InspectorCard>
              )}

              <InspectorCard title={t('verifyPage.sessionComposition')}>
                <div className="space-y-2">
                  {(context.session?.detections || []).slice(0, 5).map((item) => (
                    <div key={item.detection_id} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs">
                      <span className="text-gray-200">{item.species_chinese || item.species || t('verifyPage.unknownSpecies')}</span>
                      <span className="text-gray-500">{formatPercent(item.confidence)}</span>
                    </div>
                  ))}
                  {!context.loading && !(context.session?.detections || []).length && (
                    <p className="text-sm text-gray-500">{t('verifyPage.noSessionContext')}</p>
                  )}
                </div>
              </InspectorCard>
            </>
          ) : (
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-gray-400">
              {t('verifyPage.nothingSelected')}
            </div>
          )}
        </aside>
      </section>
    </div>
  )
}

function MetaPill({ label, value }) {
  return (
    <div className="rounded-full border border-white/10 bg-white/5 px-2 py-1 md:px-3 md:py-1.5">
      <span className="text-gray-500">{label}: </span>
      <span className="text-gray-200">{value}</span>
    </div>
  )
}

function InspectorCard({ title, children }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3 md:rounded-2xl md:p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-500 md:text-xs md:tracking-[0.16em]">{title}</p>
      <div className="mt-2 space-y-1.5 md:mt-3 md:space-y-2">{children}</div>
    </div>
  )
}

function InspectorRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs md:gap-4 md:text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-right text-gray-200">{value}</span>
    </div>
  )
}
