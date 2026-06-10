import React, { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity, Bird, Eye, Loader2, RefreshCw, Search, Sparkles, Zap,
} from 'lucide-react'
import {
  CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  getApiErrorMessage,
  getEmbeddingCluster, getEmbeddingSimilarity, getEmbeddingStats, getMonitoringSessions, getNovelSounds,
} from '../../lib/api'
import { LoadingState, StatCard, StatusBanner } from '../common'

const CLUSTER_COLORS = [
  '#10b981', '#06b6d4', '#8b5cf6', '#f59e0b', '#ef4444',
  '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16',
  '#a855f7', '#22d3ee', '#f43f5e', '#eab308', '#64748b',
]

function similarityTone(value) {
  if (value >= 0.85) return 'bg-[#30D158]/20 text-[#30D158]'
  if (value >= 0.65) return 'bg-[#0A84FF]/20 text-[#0A84FF]'
  if (value >= 0.45) return 'bg-[#FF9F0A]/20 text-[#FF9F0A]'
  return 'bg-white/[0.06] text-white/50'
}

export default function EmbeddingsTab() {
  const { t } = useTranslation()

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return t('embeddingsPage.timePlaceholder')
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(timestamp))
  }
  const [embStats, setEmbStats] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState('')
  const [clusterData, setClusterData] = useState(null)
  const [similarityData, setSimilarityData] = useState(null)
  const [novelData, setNovelData] = useState([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const loadOverview = async () => {
    setRefreshing(true)
    setError(null)
    try {
      const [stats, monitoringSessions] = await Promise.all([
        getEmbeddingStats(),
        getMonitoringSessions(),
      ])
      setEmbStats(stats)
      setSessions(Array.isArray(monitoringSessions) ? monitoringSessions : [])
      setLastUpdated(Date.now())
    } catch (err) {
      setEmbStats(null)
      setSessions([])
      setError(getApiErrorMessage(err, t('embeddingsPage.loadFailed')))
    } finally {
      setRefreshing(false)
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOverview()
  }, [])

  const loadSessionAnalysis = async () => {
    if (!sessionId.trim()) return
    setAnalyzing(true)
    setError(null)

    const [clusterResult, similarityResult, noveltyResult] = await Promise.allSettled([
      getEmbeddingCluster(sessionId.trim()),
      getEmbeddingSimilarity(sessionId.trim()),
      getNovelSounds(sessionId.trim()),
    ])

    if (clusterResult.status === 'fulfilled') {
      setClusterData(clusterResult.value)
      setLastUpdated(Date.now())
    } else {
      setClusterData(null)
      setError(getApiErrorMessage(clusterResult.reason, t('embeddingsPage.noEmbeddingsForSession')))
    }

    if (similarityResult.status === 'fulfilled') {
      setSimilarityData(similarityResult.value)
    } else {
      setSimilarityData(null)
    }

    if (noveltyResult.status === 'fulfilled') {
      setNovelData(noveltyResult.value?.novel_sounds || [])
    } else {
      setNovelData([])
    }

    setAnalyzing(false)
  }

  const { scatterData, speciesColors } = useMemo(() => {
    const colors = {}
    let colorIndex = 0
    const points = (clusterData?.points || []).map((point) => {
      if (!colors[point.species]) {
        colors[point.species] = CLUSTER_COLORS[colorIndex % CLUSTER_COLORS.length]
        colorIndex += 1
      }
      return {
        x: point.x,
        y: point.y,
        species: point.species,
        cluster: point.cluster,
        fill: colors[point.species],
      }
    })
    return { scatterData: points, speciesColors: colors }
  }, [clusterData])

  const topNovel = novelData.slice(0, 8)
  const sessionOptions = sessions.map((session) => session.session_id).filter(Boolean)
  const lastUpdatedLabel = formatTimestamp(lastUpdated)

  if (loading) return <LoadingState text={t('embeddingsPage.loading')} />

  return (
    <div className="space-y-6">
      <section className="glass-card space-y-5 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/[0.06] bg-[#BF5AF2]/10 px-3 py-1 text-xs font-medium text-[#BF5AF2]">
              <Sparkles className="h-3.5 w-3.5" />
              {t('embeddingsPage.badge')}
            </div>
            <h2 className="mt-3 text-2xl font-bold text-white">{t('embeddingsPage.title')}</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/50">
              {t('embeddingsPage.body')}
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-2xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-sm text-white/50">
            <span>{t('embeddingsPage.sessionHint')}</span>
            <button
              onClick={loadOverview}
              disabled={refreshing}
              className="ml-auto inline-flex items-center gap-1 rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1 text-xs text-white/50 hover:bg-white/[0.08] disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? t('embeddingsPage.refreshing') : t('embeddingsPage.refresh')}
            </button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard label={t('embeddingsPage.statEmbeddingRecords')} value={embStats?.total_embeddings || 0} icon={Zap} color="violet" />
          <StatCard label={t('embeddingsPage.statUniqueSpecies')} value={embStats?.unique_species || 0} icon={Bird} color="cyan" />
          <StatCard label={t('embeddingsPage.statSessions')} value={embStats?.sessions || 0} icon={Activity} color="emerald" />
          <StatCard label={t('embeddingsPage.statEmbeddingDim')} value={embStats?.embedding_dim || '--'} icon={Eye} color="amber" />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <EmbNote title={t('embeddingsPage.noteWhyTitle')} body={t('embeddingsPage.noteWhyBody')} />
          <EmbNote title={t('embeddingsPage.noteWatchTitle')} body={t('embeddingsPage.noteWatchBody')} />
          <EmbNote title={t('embeddingsPage.noteNoveltyTitle')} body={t('embeddingsPage.noteNoveltyBody')} />
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-white/40">
          <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1">{t('embeddingsPage.lastSync', { time: lastUpdatedLabel })}</span>
          <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1">
            {refreshing ? t('embeddingsPage.syncReloading') : t('embeddingsPage.syncCurrent')}
          </span>
        </div>
      </section>

      <section className="glass-card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-white">{t('embeddingsPage.loadSessionTitle')}</h3>
          <p className="mt-1 text-xs leading-5 text-white/40">
            {t('embeddingsPage.loadSessionBody')}
          </p>
        </div>
        <div className="flex flex-col gap-3 lg:flex-row">
          <input
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            placeholder={t('embeddingsPage.sessionIdPlaceholder')}
            className="flex-1 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
          />
          <select
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white"
          >
            <option value="">{t('embeddingsPage.recentSessions')}</option>
            {sessionOptions.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <button
            onClick={loadSessionAnalysis}
            disabled={analyzing || !sessionId.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-[12px] border border-white/[0.06] bg-[#BF5AF2]/15 px-4 py-2 text-sm text-[#BF5AF2] hover:bg-[#BF5AF2]/25 disabled:opacity-50"
          >
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {t('embeddingsPage.inspectSession')}
          </button>
        </div>
        <div className="mt-3">
          <StatusBanner tone="error" message={error} />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="glass-card p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-white">{t('embeddingsPage.embeddingMapTitle')}</h3>
              <p className="mt-1 text-xs leading-5 text-white/40">
                {t('embeddingsPage.embeddingMapBody')}
              </p>
            </div>
            {clusterData && (
              <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-3 py-1 text-xs text-white/40">
                {t('embeddingsPage.mapPointsClusters', { points: clusterData.n_points, clusters: clusterData.n_clusters })}
              </span>
            )}
          </div>

          {scatterData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={400}>
                <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis type="number" dataKey="x" stroke="rgba(255,255,255,0.35)" tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 10 }} />
                  <YAxis type="number" dataKey="y" stroke="rgba(255,255,255,0.35)" tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 10 }} />
                  <Tooltip
                    content={({ payload }) => {
                      if (!payload?.[0]) return null
                      const point = payload[0].payload
                      return (
                        <div className="rounded-2xl border border-white/[0.06] bg-[#1c1c1e] px-3 py-2 text-xs">
                          <p className="font-medium text-[#30D158]">{point.species}</p>
                          <p className="mt-1 text-white/40">{t('embeddingsPage.tooltipCluster', { cluster: point.cluster })}</p>
                        </div>
                      )
                    }}
                  />
                  <Scatter
                    data={scatterData}
                    shape={(props) => (
                      <circle
                        cx={props.cx}
                        cy={props.cy}
                        r={4}
                        fill={props.payload.fill}
                        fillOpacity={0.82}
                        stroke={props.payload.fill}
                        strokeWidth={1}
                      />
                    )}
                  />
                </ScatterChart>
              </ResponsiveContainer>

              <div className="mt-4 flex flex-wrap gap-2">
                {Object.entries(speciesColors).map(([species, color]) => (
                  <span key={species} className="rounded-full border border-white/[0.06] px-2.5 py-1 text-xs" style={{ color }}>
                    {species}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <EmptyPanel
              icon={Eye}
              title={t('embeddingsPage.emptyMapTitle')}
              body={t('embeddingsPage.emptyMapBody')}
            />
          )}
        </div>

        <div className="space-y-4">
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white">{t('embeddingsPage.novelTitle')}</h3>
            <p className="mt-1 text-xs leading-5 text-white/40">
              {t('embeddingsPage.novelBody')}
            </p>

            {topNovel.length > 0 ? (
              <div className="mt-4 space-y-2">
                {topNovel.map((item) => (
                  <div key={`${item.record_index}-${item.time_offset}`} className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-[#30D158]">{item.predicted_species}</p>
                      <span className="text-xs text-[#BF5AF2]">
                        {t('embeddingsPage.noveltyScore', { score: Number(item.novelty_score ?? 0).toFixed(2) })}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-white/40">
                      {t('embeddingsPage.novelMeta', {
                        time: Number(item.time_offset || 0).toFixed(1),
                        confidence: (Number(item.confidence || 0) * 100).toFixed(1),
                      })}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4 text-sm text-white/40">
                {t('embeddingsPage.novelEmpty')}
              </div>
            )}
          </div>

          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white">{t('embeddingsPage.guideTitle')}</h3>
            <div className="mt-4 space-y-3">
              <EmbGuide title={t('embeddingsPage.guideTightTitle')} body={t('embeddingsPage.guideTightBody')} />
              <EmbGuide title={t('embeddingsPage.guideMixedTitle')} body={t('embeddingsPage.guideMixedBody')} />
              <EmbGuide title={t('embeddingsPage.guideOutliersTitle')} body={t('embeddingsPage.guideOutliersBody')} />
            </div>
          </div>
        </div>
      </section>

      <section className="glass-card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-white">{t('embeddingsPage.similarityTitle')}</h3>
          <p className="mt-1 text-xs leading-5 text-white/40">
            {t('embeddingsPage.similarityBody')}
          </p>
        </div>

        {similarityData?.species?.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-2 text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left text-white/25">{t('embeddingsPage.speciesColumn')}</th>
                  {similarityData.species.map((species) => (
                    <th key={species} className="px-2 py-1 text-left text-white/25">{species}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {similarityData.species.map((rowSpecies, rowIndex) => (
                  <tr key={rowSpecies}>
                    <td className="px-2 py-1 text-white/50">{rowSpecies}</td>
                    {(similarityData.similarity_matrix[rowIndex] || []).map((value, colIndex) => (
                      <td key={`${rowSpecies}-${similarityData.species[colIndex]}`} className={`rounded-lg px-2 py-1 ${similarityTone(value)}`}>
                        {Number(value).toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyPanel
            icon={Bird}
            title={t('embeddingsPage.emptySimilarityTitle')}
            body={t('embeddingsPage.emptySimilarityBody')}
          />
        )}
      </section>
    </div>
  )
}

function EmbNote({ title, body }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/25">{title}</p>
      <p className="mt-2 text-sm leading-6 text-white/60">{body}</p>
    </div>
  )
}

function EmbGuide({ title, body }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <p className="text-sm font-medium text-white">{title}</p>
      <p className="mt-2 text-sm leading-6 text-white/50">{body}</p>
    </div>
  )
}

function EmptyPanel({ icon: Icon, title, body }) {
  return (
    <div className="flex h-64 items-center justify-center text-center text-white/25">
      <div>
        <Icon className="mx-auto mb-3 h-8 w-8 opacity-30" />
        <p className="text-sm text-white/50">{title}</p>
        <p className="mt-1 text-xs text-white/25">{body}</p>
      </div>
    </div>
  )
}
