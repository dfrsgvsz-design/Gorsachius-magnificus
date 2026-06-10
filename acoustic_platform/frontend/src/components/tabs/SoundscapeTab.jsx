import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Cell,
} from 'recharts'
import { Activity, BarChart3, Download, Info, Loader2, Upload, Waves } from 'lucide-react'
import { getApiErrorMessage } from '../../lib/api'
import { PageHero, SectionHeader, StatCard, StatusBanner } from '../common'
import { COLORS } from '../../constants'

const api = {
  analyzeSoundscape: (file, siteName) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`/api/soundscape/analyze?site_name=${encodeURIComponent(siteName)}`, { method: 'POST', body: form }).then((r) => r.json())
  },
  getBaseline: (siteName) => fetch(`/api/soundscape/baseline/${encodeURIComponent(siteName)}`).then((r) => r.json()),
}

const INDEX_META = {
  aci:      { label: 'ACI',      full: 'Acoustic Complexity Index',              desc_en: 'Temporal variation intensity — higher values indicate more complex soundscapes', desc_zh: '时间变化强度——值越高表示声景越复杂', unit: '', color: COLORS.chart[0] },
  ndsi:     { label: 'NDSI',     full: 'Normalized Difference Soundscape Index', desc_en: 'Biophony vs anthrophony ratio — ranges from -1 (anthropogenic) to +1 (biological)', desc_zh: '生物声与人为声比率——范围 -1（人为主导）到 +1（生物主导）', unit: '', color: COLORS.chart[1] },
  adi:      { label: 'ADI',      full: 'Acoustic Diversity Index',               desc_en: 'Shannon diversity across frequency bands — higher means more evenly distributed energy', desc_zh: '频段间香农多样性——值越高表示能量分布越均匀', unit: '', color: COLORS.chart[2] },
  bio:      { label: 'BIO',      full: 'Bioacoustic Index',                      desc_en: 'Energy concentrated in biological frequency range (2–11 kHz)', desc_zh: '生物频率范围（2-11 kHz）中的集中能量', unit: '', color: COLORS.chart[3] },
  h:        { label: 'Entropy',  full: 'Spectral Entropy',                       desc_en: 'Frequency distribution uniformity — high entropy indicates even spectral spread', desc_zh: '频率分布均匀度——高熵值表示频谱分布均匀', unit: 'bits', color: COLORS.chart[4] },
  evenness: { label: 'Evenness', full: 'Acoustic Evenness',                      desc_en: 'Gini-based energy distribution across frequency bands', desc_zh: '基于基尼系数的频段能量分布', unit: '', color: COLORS.chart[5] },
}

function healthStatus(status) {
  const map = {
    healthy:           { label_en: 'Healthy',  label_zh: '健康',   style: { background: 'rgba(45,106,79,0.08)', color: 'var(--cornell-forest)' } },
    moderate:          { label_en: 'Moderate', label_zh: '中等',   style: { background: 'rgba(245,158,11,0.08)', color: '#D97706' } },
    degraded:          { label_en: 'Degraded', label_zh: '退化',   style: { background: 'rgba(179,27,27,0.08)', color: 'var(--cornell-carnelian)' } },
    severely_degraded: { label_en: 'Severely Degraded', label_zh: '严重退化', style: { background: 'rgba(179,27,27,0.12)', color: 'var(--cornell-carnelian)' } },
  }
  return map[status] || map.moderate
}

export default function SoundscapeTab() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
  const [file, setFile] = useState(null)
  const [siteName, setSiteName] = useState('')
  const [result, setResult] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [showInfo, setShowInfo] = useState(null)

  const handleAnalyze = async () => {
    if (!file) return
    setAnalyzing(true)
    setError(null)
    setResult(null)
    try {
      const data = await api.analyzeSoundscape(file, siteName)
      if (data.error) {
        setError(data.error)
      } else {
        setResult(data)
      }
    } catch (err) {
      setError(getApiErrorMessage(err, locale === 'zh' ? '声景分析失败' : 'Soundscape analysis failed'))
    } finally {
      setAnalyzing(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragActive(false)
    const dropped = e.dataTransfer.files?.[0]
    const audioExtensions = /\.(wav|mp3|ogg|flac|m4a|aac|wma|opus)$/i
    if (dropped && (dropped.type.startsWith('audio/') || audioExtensions.test(dropped.name))) setFile(dropped)
  }

  const handleExportJSON = () => {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `soundscape_${siteName || 'analysis'}_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const indices = result?.indices || {}
  const health = result?.health || null

  const radarData = Object.entries(INDEX_META)
    .filter(([key]) => indices[key] != null)
    .map(([key, meta]) => {
      let norm = indices[key]
      if (key === 'ndsi') norm = (norm + 1) * 50
      else if (key === 'aci') norm = Math.min(100, norm * 30)
      else if (key === 'h') norm = Math.min(100, norm * 12)
      else if (key === 'adi') norm = Math.min(100, norm * 30)
      else if (key === 'bio') norm = Math.min(100, norm * 2)
      else if (key === 'evenness') norm = Math.min(100, norm * 100)
      return {
        index: meta.label,
        value: Math.max(0, Math.min(100, norm)),
        raw: Number(indices[key]).toFixed(4),
        key,
      }
    })

  const healthBarData = health?.index_scores
    ? Object.entries(health.index_scores).map(([key, score]) => ({
        index: INDEX_META[key]?.label || key.toUpperCase(),
        score,
        key,
        color: INDEX_META[key]?.color || COLORS.chart[0],
      }))
    : []

  const hStatus = health?.status ? healthStatus(health.status) : null

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="card-elevated p-5 md:p-8">
        <div className="section-kicker">
          <Waves className="h-3.5 w-3.5" />
          {locale === 'zh' ? '声景分析' : 'Soundscape Analysis'}
        </div>
        <h2 className="mt-3 text-xl font-bold md:text-2xl" style={{ color: 'var(--text-primary)' }}>
          {locale === 'zh' ? '声景生态指数与生态系统健康评分' : 'Ecoacoustic Indices & Ecosystem Health Scoring'}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
          {locale === 'zh'
            ? '上传音频录音计算标准声学指数（ACI, NDSI, ADI, BIO, 熵, 均匀度）。提供站点名称时，系统将参照基线数据评估生态系统健康状况。'
            : 'Upload audio recordings to compute standard acoustic indices (ACI, NDSI, ADI, BIO, Entropy, Evenness). When a site name is provided, the system scores ecosystem health relative to stored baselines.'}
        </p>
      </section>

      <StatusBanner tone="error" message={error} />

      {/* Upload Section */}
      <section className="card p-5 md:p-6">
        <SectionHeader
          title={locale === 'zh' ? '上传音频文件' : 'Upload Audio Recording'}
          body={locale === 'zh' ? '支持 WAV, MP3, FLAC 等常见音频格式' : 'Supports WAV, MP3, FLAC and other common audio formats'}
        />
        <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
          <div
            className={`upload-zone cursor-pointer ${dragActive ? 'border-[var(--cornell-teal)]' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
          >
            <Upload className="mx-auto mb-3 h-8 w-8" style={{ color: 'var(--text-tertiary)' }} />
            <label className="cursor-pointer text-sm font-medium" style={{ color: 'var(--cornell-blue)' }}>
              {locale === 'zh' ? '点击选择文件或拖拽到此处' : 'Click to select or drag and drop'}
              <input type="file" accept="audio/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </label>
            {file && (
              <div className="mt-3 flex items-center justify-center gap-2">
                <Activity className="h-4 w-4" style={{ color: 'var(--cornell-teal)' }} />
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{file.name}</span>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3 md:w-64">
            <div>
              <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                {locale === 'zh' ? '站点名称（可选）' : 'Site Name (optional)'}
              </label>
              <input
                value={siteName}
                onChange={(e) => setSiteName(e.target.value)}
                placeholder={locale === 'zh' ? '用于健康评分基线对比' : 'For health scoring against baseline'}
                className="input-field"
              />
            </div>
            <button
              onClick={handleAnalyze}
              disabled={analyzing || !file}
              className="btn-primary w-full disabled:opacity-50"
            >
              {analyzing ? (
                <><Loader2 className="h-4 w-4 animate-spin" />{locale === 'zh' ? '分析中…' : 'Analyzing…'}</>
              ) : (
                <><Waves className="h-4 w-4" />{locale === 'zh' ? '分析声景' : 'Analyze Soundscape'}</>
              )}
            </button>
          </div>
        </div>
      </section>

      {/* Results */}
      {result && (
        <>
          {/* Health summary */}
          {health && hStatus && (
            <div className="grid gap-3 md:grid-cols-3">
              <StatCard
                label={locale === 'zh' ? '健康评分' : 'Health Score'}
                value={health.overall_score ?? '—'}
                subtitle={`/ 100`}
                icon={Waves}
                color="teal"
              />
              <div className="card flex items-center justify-between p-4">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {locale === 'zh' ? '生态状态' : 'Ecosystem Status'}
                </span>
                <span className="rounded-full px-4 py-1.5 text-sm font-semibold" style={hStatus.style}>
                  {locale === 'zh' ? hStatus.label_zh : hStatus.label_en}
                </span>
              </div>
              <StatCard
                label="NDSI"
                value={indices.ndsi?.toFixed(3) ?? '—'}
                subtitle={locale === 'zh' ? '生物声 vs 人为声' : 'Biophony vs Anthrophony'}
                icon={BarChart3}
                color="blue"
              />
            </div>
          )}

          {/* Export button */}
          <div className="flex justify-end">
            <button onClick={handleExportJSON} className="btn-ghost text-xs">
              <Download className="h-3.5 w-3.5" />
              {locale === 'zh' ? '导出 JSON' : 'Export JSON'}
            </button>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {/* Index table */}
            <section className="card p-5">
              <SectionHeader
                title={locale === 'zh' ? '声学指数结果' : 'Acoustic Index Results'}
                body={locale === 'zh' ? '六项标准声景生态指数' : 'Six standard ecoacoustic indices'}
              />
              <div className="mt-4 space-y-2">
                {Object.entries(INDEX_META).map(([key, meta]) => (
                  indices[key] != null && (
                    <div
                      key={key}
                      className="flex items-center justify-between rounded-lg border p-3 transition-all"
                      style={{ borderColor: 'var(--border-subtle)', background: showInfo === key ? 'var(--surface-secondary)' : 'white' }}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 h-3 w-3 shrink-0 rounded-sm" style={{ background: meta.color }} />
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{meta.label}</p>
                            <button
                              onClick={() => setShowInfo(showInfo === key ? null : key)}
                              className="rounded p-0.5 transition-colors hover:bg-gray-100"
                            >
                              <Info className="h-3.5 w-3.5" style={{ color: 'var(--text-tertiary)' }} />
                            </button>
                          </div>
                          <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{meta.full}</p>
                          {showInfo === key && (
                            <p className="mt-1.5 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                              {locale === 'zh' ? meta.desc_zh : meta.desc_en}
                            </p>
                          )}
                        </div>
                      </div>
                      <span className="shrink-0 font-mono text-sm font-semibold" style={{ color: meta.color }}>
                        {Number(indices[key]).toFixed(4)}
                      </span>
                    </div>
                  )
                ))}
              </div>
            </section>

            {/* Radar chart */}
            {radarData.length > 0 && (
              <section className="card p-5">
                <SectionHeader
                  title={locale === 'zh' ? '指数雷达图' : 'Index Radar Profile'}
                  body={locale === 'zh' ? '各指数归一化后的相对分布' : 'Normalized distribution of acoustic indices'}
                />
                <div className="mt-4">
                  <ResponsiveContainer width="100%" height={320}>
                    <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
                      <PolarGrid stroke="#E5E7EB" />
                      <PolarAngleAxis
                        dataKey="index"
                        tick={{ fontSize: 12, fill: '#4B5563' }}
                      />
                      <PolarRadiusAxis
                        angle={30}
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: '#9CA3AF' }}
                        axisLine={false}
                      />
                      <Radar
                        dataKey="value"
                        stroke={COLORS.teal}
                        fill={COLORS.teal}
                        fillOpacity={0.15}
                        strokeWidth={2}
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'white',
                          border: '1px solid #E5E7EB',
                          borderRadius: 8,
                          fontSize: 12,
                          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                        }}
                        formatter={(value, name, props) => [`${props.payload.raw}`, props.payload.index]}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            )}
          </div>

          {/* Health breakdown */}
          {healthBarData.length > 0 && (
            <section className="card p-5">
              <SectionHeader
                title={locale === 'zh' ? '健康评分分解' : 'Health Score Breakdown'}
                body={locale === 'zh' ? '各指数相对于站点基线的评分（50 = 基线均值）' : 'Each index scored against site baseline (50 = baseline mean)'}
              />
              <div className="mt-4">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={healthBarData} barSize={40}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                    <XAxis dataKey="index" stroke="#9CA3AF" tick={{ fontSize: 12, fill: '#4B5563' }} />
                    <YAxis domain={[0, 100]} stroke="#9CA3AF" tick={{ fontSize: 11, fill: '#9CA3AF' }} />
                    <Tooltip
                      contentStyle={{
                        background: 'white',
                        border: '1px solid #E5E7EB',
                        borderRadius: 8,
                        fontSize: 12,
                        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                      }}
                      formatter={(value) => [`${Number(value).toFixed(1)}`, 'Score']}
                    />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                      {healthBarData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          {/* Reference info */}
          {result.site_name && (
            <div className="card-accent">
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                {locale === 'zh' ? '分析站点' : 'Analysis Site'}
              </p>
              <p className="mt-1 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{result.site_name}</p>
              {health && (
                <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {locale === 'zh' ? '基线对比已启用——健康评分基于该站点的历史参考数据计算。' : 'Baseline comparison active — health scores computed against stored reference data for this site.'}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
