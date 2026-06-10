import React, { useCallback, useEffect, useState } from 'react'
import {
  Bird,
  ChevronDown,
  ChevronRight,
  Eye,
  Loader2,
  Search,
  Trash2,
} from 'lucide-react'
import {
  deleteSurveyObservation,
  getApiErrorMessage,
  getSurveyObservations,
} from '../../lib/api'

const EVIDENCE_LABELS = {
  visual: { zh: '目视', en: 'Visual' },
  auditory: { zh: '听觉', en: 'Auditory' },
  photo: { zh: '照片', en: 'Photo' },
  specimen: { zh: '标本', en: 'Specimen' },
  trace: { zh: '痕迹', en: 'Trace' },
  camera_trap: { zh: '红外相机', en: 'Camera trap' },
}

const CERTAINTY_LABELS = {
  confirmed: { zh: '已确认', en: 'Confirmed', cls: 'text-[#30D158]' },
  review_needed: { zh: '待审核', en: 'Review', cls: 'text-[#FF9F0A]' },
  uncertain: { zh: '不确定', en: 'Uncertain', cls: 'text-[#FF453A]' },
}

/**
 * Observation list panel — row-list style matching ProjectManagementPanel.
 * Each observation is a clean row with chevron, icon, species name,
 * right-aligned metadata (count, evidence, certainty), and delete button.
 */
export default function ObservationListPanel({ locale = 'zh', isOnline, projectId, siteId, onDataChanged }) {
  const isZh = locale === 'zh'
  const [expanded, setExpanded] = useState(true)
  const [observations, setObservations] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedObs, setExpandedObs] = useState({})

  const refresh = useCallback(async () => {
    if (!isOnline) return
    setLoading(true)
    setError(null)
    try {
      const data = await getSurveyObservations(projectId, siteId)
      setObservations(data.observations || [])
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '加载观测记录失败' : 'Failed to load observations'))
    } finally {
      setLoading(false)
    }
  }, [isOnline, projectId, siteId, isZh])

  useEffect(() => {
    if (expanded && isOnline) refresh()
  }, [expanded, isOnline, refresh])

  function toggleObs(obsId) {
    setExpandedObs((prev) => ({ ...prev, [obsId]: !prev[obsId] }))
  }

  async function handleDelete(obsId) {
    if (!isOnline) return
    setBusy(`delete-${obsId}`)
    setError(null)
    try {
      await deleteSurveyObservation(obsId)
      setConfirmDelete(null)
      setExpandedObs((prev) => { const next = { ...prev }; delete next[obsId]; return next })
      await refresh()
      onDataChanged?.()
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '删除失败' : 'Delete failed'))
    } finally {
      setBusy('')
    }
  }

  const filtered = searchQuery.trim()
    ? observations.filter((obs) => {
        const q = searchQuery.toLowerCase()
        return (
          (obs.chinese_name || '').toLowerCase().includes(q) ||
          (obs.english_name || '').toLowerCase().includes(q) ||
          (obs.scientific_name || '').toLowerCase().includes(q) ||
          (obs.observer || '').toLowerCase().includes(q)
        )
      })
    : observations

  function formatDate(dateStr) {
    if (!dateStr) return ''
    try {
      const d = new Date(dateStr)
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    } catch {
      return dateStr
    }
  }

  function getSpeciesDisplay(obs) {
    if (isZh && obs.chinese_name) return obs.chinese_name
    return obs.scientific_name || obs.english_name || obs.chinese_name || (isZh ? '未知物种' : 'Unknown')
  }

  function getEvidenceLabel(type) {
    const entry = EVIDENCE_LABELS[type]
    return entry ? (isZh ? entry.zh : entry.en) : type || '—'
  }

  function getCertaintyInfo(cert) {
    return CERTAINTY_LABELS[cert] || { zh: cert, en: cert, cls: 'text-white/30' }
  }

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#BF5AF2]/15">
            <Eye className="h-4 w-4 text-[#BF5AF2]" />
          </div>
          <h3 className="text-[15px] font-semibold text-white">
            {isZh ? '观测记录管理' : 'Observation Records'}
          </h3>
          <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">
            {observations.length}
          </span>
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-white/30" /> : <ChevronRight className="h-4 w-4 text-white/30" />}
      </button>

      {expanded && (
        <div className="space-y-3 px-4 pb-4">
          <p className="text-[12px] text-white/30">
            {isZh ? '查看、搜索和管理所有观测记录。点击展开查看详情。' : 'View, search and manage all observation records.'}
          </p>

          {!isOnline && (
            <div className="rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
              {isZh ? '需要网络连接来加载记录。' : 'Network required to load records.'}
            </div>
          )}

          {error && (
            <div className="rounded-[12px] bg-[#FF453A]/10 px-4 py-2.5 text-[13px] text-[#FF453A]">
              {error}
            </div>
          )}

          {/* iOS search bar */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/20" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={isZh ? '搜索物种名/观察者...' : 'Search species/observer...'}
              className="w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] py-[10px] pl-10 pr-4 text-[14px] text-white placeholder:text-white/20 focus:border-[#0A84FF]/40 focus:outline-none"
            />
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-[13px] text-[#BF5AF2]">
              <Loader2 className="h-4 w-4 animate-spin" />
              {isZh ? '加载中...' : 'Loading...'}
            </div>
          )}

          {/* iOS grouped inset observation list */}
          <div className="max-h-[500px] overflow-y-auto rounded-2xl border border-white/[0.06]">
            {filtered.length === 0 && !loading && (
              <p className="px-4 py-5 text-center text-[14px] text-white/25">
                {searchQuery
                  ? (isZh ? '未找到匹配的记录' : 'No matching records')
                  : (isZh ? '暂无观测记录' : 'No observations yet')}
              </p>
            )}
            {filtered.map((obs, idx) => {
              const certInfo = getCertaintyInfo(obs.certainty)
              const isOpen = expandedObs[obs.observation_id]
              return (
                <div key={obs.observation_id} className={idx < filtered.length - 1 ? 'border-b border-white/[0.04]' : ''}>
                  <div className="flex items-center gap-3 px-4 py-[12px] active:bg-white/[0.04]">
                    <button
                      onClick={() => toggleObs(obs.observation_id)}
                      className="shrink-0 text-white/20"
                    >
                      {isOpen
                        ? <ChevronDown className="h-4 w-4" />
                        : <ChevronRight className="h-4 w-4" />}
                    </button>
                    <Bird className="h-4 w-4 shrink-0 text-[#BF5AF2]" />
                    <button
                      onClick={() => toggleObs(obs.observation_id)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <span className="block truncate text-[14px] text-white">
                        {getSpeciesDisplay(obs)}
                      </span>
                      {obs.scientific_name && isZh && obs.chinese_name && (
                        <span className="block truncate text-[12px] italic text-white/25">{obs.scientific_name}</span>
                      )}
                    </button>
                    <div className="flex shrink-0 items-center gap-2 text-[12px] text-white/30">
                      <span>×{obs.count || 1}</span>
                      <span>{getEvidenceLabel(obs.evidence_type)}</span>
                      <span className={certInfo.cls}>{isZh ? certInfo.zh : certInfo.en}</span>
                    </div>
                    {confirmDelete?.id === obs.observation_id ? (
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          onClick={() => handleDelete(obs.observation_id)}
                          disabled={busy === `delete-${obs.observation_id}`}
                          className="rounded-md bg-[#FF453A] px-2 py-1 text-[11px] font-medium text-white disabled:opacity-50"
                        >
                          {busy === `delete-${obs.observation_id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : (isZh ? '确认' : 'OK')}
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="rounded-md px-2 py-1 text-[11px] text-white/40 active:text-white"
                        >
                          {isZh ? '取消' : '×'}
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete({ id: obs.observation_id, name: getSpeciesDisplay(obs) })}
                        className="shrink-0 rounded-md p-1.5 text-white/15 active:bg-[#FF453A]/10 active:text-[#FF453A]"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>

                  {/* Expanded detail panel */}
                  {isOpen && (
                    <div className="mx-4 mb-3 rounded-[12px] border border-white/[0.06] bg-white/[0.02] px-4 py-3">
                      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[12px]">
                        {obs.observed_at && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '时间' : 'Time'}:</span>
                            <span className="text-white/60">{formatDate(obs.observed_at)}</span>
                          </div>
                        )}
                        {obs.observer && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '观察者' : 'Observer'}:</span>
                            <span className="text-white/60">{obs.observer}</span>
                          </div>
                        )}
                        {obs.protocol && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '协议' : 'Protocol'}:</span>
                            <span className="text-white/60">{obs.protocol}</span>
                          </div>
                        )}
                        {obs.behavior && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '行为' : 'Behavior'}:</span>
                            <span className="text-white/60">{obs.behavior}</span>
                          </div>
                        )}
                        {obs.breeding_code && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '繁殖码' : 'Breeding'}:</span>
                            <span className="text-white/60">{obs.breeding_code}</span>
                          </div>
                        )}
                        {obs.habitat_notes && (
                          <div className="col-span-2 flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '栖息地' : 'Habitat'}:</span>
                            <span className="text-white/60">{obs.habitat_notes}</span>
                          </div>
                        )}
                        {obs.latitude && obs.longitude && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '坐标' : 'Coords'}:</span>
                            <span className="text-white/60">{Number(obs.latitude).toFixed(5)}, {Number(obs.longitude).toFixed(5)}</span>
                          </div>
                        )}
                        {obs.confidence != null && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '置信度' : 'Confidence'}:</span>
                            <span className="text-white/60">{Math.round(obs.confidence * 100)}%</span>
                          </div>
                        )}
                        {obs.sign_type && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '痕迹类型' : 'Sign'}:</span>
                            <span className="text-white/60">{obs.sign_type}</span>
                          </div>
                        )}
                        {(obs.media || []).length > 0 && (
                          <div className="flex items-center gap-1">
                            <span className="text-white/25">{isZh ? '媒体' : 'Media'}:</span>
                            <span className="text-white/60">{obs.media.length} {isZh ? '个附件' : 'files'}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Summary stats */}
          {observations.length > 0 && (
            <div className="flex items-center gap-4 px-1 text-[12px] text-white/25">
              <span>{isZh ? '合计' : 'Total'} <strong className="text-white/50">{observations.length}</strong> {isZh ? '条' : ''}</span>
              <span>{isZh ? '物种' : 'Species'} <strong className="text-white/50">{new Set(observations.map((o) => o.scientific_name || o.chinese_name).filter(Boolean)).size}</strong></span>
              <span>{isZh ? '个体' : 'Individuals'} <strong className="text-white/50">{observations.reduce((sum, o) => sum + (o.count || 1), 0)}</strong></span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
