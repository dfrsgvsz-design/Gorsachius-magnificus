import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BarChart, Bar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis } from 'recharts'
import { Loader2, Upload, Waves } from 'lucide-react'
import { getApiErrorMessage } from '../../lib/api'
import { PageHero, SectionHeader, StatCard, StatusBanner } from '../common'
import { COLORS } from '../../constants'

const api = {
  analyzeSoundscape: (file, siteName) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`/api/soundscape/analyze?site_name=${encodeURIComponent(siteName)}`, { method: 'POST', body: form }).then((r) => r.json())
  },
}

const INDEX_LABELS = { aci: 'ACI', ndsi: 'NDSI', adi: 'ADI', bio: 'BIO', h: 'Entropy', evenness: 'Evenness' }
const INDEX_DESCRIPTIONS = {
  aci: 'Acoustic Complexity Index — temporal variation intensity',
  ndsi: 'Normalized Difference Soundscape Index — biophony vs anthrophony',
  adi: 'Acoustic Diversity Index — frequency band evenness',
  bio: 'Bioacoustic Index — biological frequency band energy',
  h: 'Spectral Entropy — frequency distribution uniformity',
  evenness: 'Acoustic Evenness — energy distribution across bands',
}

function statusColor(status) {
  if (status === 'healthy') return 'text-[#30D158] bg-[#30D158]/15'
  if (status === 'moderate') return 'text-[#FF9F0A] bg-[#FF9F0A]/15'
  if (status === 'degraded') return 'text-[#FF453A] bg-[#FF453A]/15'
  return 'text-white/40 bg-white/[0.06]'
}

export default function SoundscapeTab() {
  const { t } = useTranslation()
  const [file, setFile] = useState(null)
  const [siteName, setSiteName] = useState('')
  const [result, setResult] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)

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
      setError(getApiErrorMessage(err, t('soundscapePage.analyzeFailed', { defaultValue: 'Soundscape analysis failed' })))
    } finally {
      setAnalyzing(false)
    }
  }

  const indices = result?.indices || {}
  const health = result?.health || null

  const radarData = Object.entries(INDEX_LABELS)
    .filter(([key]) => indices[key] != null)
    .map(([key, label]) => ({
      index: label,
      value: Math.min(100, Math.max(0, indices[key] * (key === 'ndsi' ? 50 : key === 'aci' ? 30 : key === 'h' ? 10 : 1))),
      raw: Number(indices[key]).toFixed(3),
    }))

  const healthBarData = health?.index_scores
    ? Object.entries(health.index_scores).map(([key, score]) => ({ index: INDEX_LABELS[key] || key, score }))
    : []

  return (
    <div className="space-y-6">
      <PageHero
        kicker={<><Waves className="h-3.5 w-3.5" />{t('soundscapePage.badge', { defaultValue: 'Soundscape analysis' })}</>}
        title={t('soundscapePage.title', { defaultValue: 'Ecoacoustic indices and ecosystem health scoring' })}
        body={t('soundscapePage.body', { defaultValue: 'Compute standard acoustic indices (ACI, NDSI, ADI, BIO, Entropy) from audio recordings. When a site baseline exists, the system scores ecosystem health relative to reference conditions.' })}
      />

      <StatusBanner tone="error" message={error} />

      <section className="section-shell space-y-4">
        <SectionHeader title={t('soundscapePage.upload', { defaultValue: 'Upload audio for analysis' })} />
        <div className="grid gap-3 md:grid-cols-3">
          <div className="md:col-span-2">
            <div className="rounded-[12px] border border-dashed border-white/[0.12] p-4 text-center">
              <Upload className="mx-auto mb-2 h-6 w-6 text-white/20" />
              <label className="cursor-pointer text-sm text-[#0A84FF] hover:underline">
                {t('soundscapePage.selectFile', { defaultValue: 'Select audio file' })}
                <input type="file" accept="audio/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </label>
              {file && <p className="mt-2 text-xs text-white/40">{file.name}</p>}
            </div>
          </div>
          <div className="space-y-2">
            <input value={siteName} onChange={(e) => setSiteName(e.target.value)} placeholder={t('soundscapePage.siteOptional', { defaultValue: 'Site name (optional, for health scoring)' })} className="touch-button w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20" />
            <button onClick={handleAnalyze} disabled={analyzing || !file} className="touch-button w-full rounded-[12px] bg-[#0A84FF] px-4 py-2 text-sm font-medium text-white active:scale-[0.97] disabled:opacity-50">
              {analyzing ? <><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t('soundscapePage.analyzing', { defaultValue: 'Analyzing...' })}</> : t('soundscapePage.analyze', { defaultValue: 'Analyze soundscape' })}
            </button>
          </div>
        </div>
      </section>

      {result && (
        <>
          {health && (
            <div className="grid gap-3 md:grid-cols-3">
              <StatCard label={t('soundscapePage.healthScore', { defaultValue: 'Health score' })} value={health.overall_score ?? '—'} icon={Waves} color="emerald" />
              <div className="flex items-center gap-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
                <span className="text-sm text-white/40">{t('soundscapePage.status', { defaultValue: 'Status' })}</span>
                <span className={`ml-auto rounded-full px-3 py-1 text-sm font-medium ${statusColor(health.status)}`}>{health.status}</span>
              </div>
              <StatCard label="NDSI" value={indices.ndsi?.toFixed(3) ?? '—'} icon={Waves} color="cyan" />
            </div>
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            <section className="section-shell">
              <SectionHeader title={t('soundscapePage.indicesTitle', { defaultValue: 'Acoustic indices' })} />
              <div className="space-y-2">
                {Object.entries(INDEX_LABELS).map(([key, label]) => (
                  indices[key] != null && (
                    <div key={key} className="flex items-center justify-between rounded-2xl bg-white/[0.03] p-3">
                      <div>
                        <p className="text-sm font-medium text-white">{label}</p>
                        <p className="text-[11px] text-white/25">{INDEX_DESCRIPTIONS[key]}</p>
                      </div>
                      <span className="text-sm font-mono text-[#30D158]">{Number(indices[key]).toFixed(4)}</span>
                    </div>
                  )
                ))}
              </div>
            </section>

            {healthBarData.length > 0 && (
              <section className="section-shell">
                <SectionHeader title={t('soundscapePage.healthBreakdown', { defaultValue: 'Health score breakdown' })} body={t('soundscapePage.healthBreakdownBody', { defaultValue: 'Each index scored against site baseline (50 = baseline mean)' })} />
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={healthBarData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="index" stroke="#64748b" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} stroke="#64748b" tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                      {healthBarData.map((entry, i) => (
                        <BarChart key={i} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  )
}
