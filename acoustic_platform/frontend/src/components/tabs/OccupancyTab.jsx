import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BarChart, Bar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from 'recharts'
import { BarChart3, Loader2, MapPin } from 'lucide-react'
import { getApiErrorMessage, analyzeOccupancy, getOccupancyVerificationTargets } from '../../lib/api'
import { EmptyPanel, PageHero, SectionHeader, StatCard, StatusBanner } from '../common'
import { COLORS } from '../../constants'

export default function OccupancyTab() {
  const { t } = useTranslation()
  const [species, setSpecies] = useState('')
  const [nSurveys, setNSurveys] = useState(6)
  const [surveyDays, setSurveyDays] = useState(7)
  const [result, setResult] = useState(null)
  const [targets, setTargets] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)

  const handleAnalyze = async () => {
    if (!species.trim()) return
    setAnalyzing(true)
    setError(null)
    setResult(null)
    setTargets(null)
    try {
      const data = await analyzeOccupancy({ species: species.trim(), n_surveys: nSurveys, survey_duration_days: surveyDays })
      if (data.error) {
        setError(data.error)
      } else {
        setResult(data)
        try {
          const t2 = await getOccupancyVerificationTargets(species.trim())
          setTargets(t2.targets || [])
        } catch { /* optional */ }
      }
    } catch (err) {
      setError(getApiErrorMessage(err, t('occupancyPage.analyzeFailed', { defaultValue: 'Occupancy analysis failed' })))
    } finally {
      setAnalyzing(false)
    }
  }

  const siteData = (result?.sites || []).map((s) => ({
    site: s.site.length > 12 ? s.site.slice(0, 12) + '…' : s.site,
    fullSite: s.site,
    probability: s.occupancy_probability,
    detected: s.detected,
  }))

  return (
    <div className="space-y-6">
      <PageHero
        kicker={<><BarChart3 className="h-3.5 w-3.5" />{t('occupancyPage.badge', { defaultValue: 'Occupancy modeling' })}</>}
        title={t('occupancyPage.title', { defaultValue: 'Estimate true species occupancy corrected for imperfect detection' })}
        body={t('occupancyPage.body', { defaultValue: 'Naive occupancy (detected / total sites) underestimates true occupancy because species can be present but undetected. This tool applies the MacKenzie et al. (2002) model to correct for detection probability.' })}
      />

      <StatusBanner tone="error" message={error} />

      <section className="section-shell space-y-4">
        <SectionHeader title={t('occupancyPage.parameters', { defaultValue: 'Analysis parameters' })} />
        <div className="grid gap-3 md:grid-cols-4">
          <input value={species} onChange={(e) => setSpecies(e.target.value)} placeholder={t('occupancyPage.speciesPlaceholder', { defaultValue: 'Scientific name (e.g. Gorsachius magnificus)' })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500 md:col-span-2" />
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400">{t('occupancyPage.surveys', { defaultValue: 'Surveys' })}</label>
            <input type="number" value={nSurveys} onChange={(e) => setNSurveys(Number(e.target.value))} min={2} max={20} className="w-16 rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-white" />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400">{t('occupancyPage.windowDays', { defaultValue: 'Window (d)' })}</label>
            <input type="number" value={surveyDays} onChange={(e) => setSurveyDays(Number(e.target.value))} min={1} max={30} className="w-16 rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-white" />
          </div>
        </div>
        <button onClick={handleAnalyze} disabled={analyzing || !species.trim()} className="touch-button rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white active:scale-[0.97] disabled:opacity-50">
          {analyzing ? <><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t('occupancyPage.analyzing', { defaultValue: 'Analyzing...' })}</> : t('occupancyPage.runModel', { defaultValue: 'Run occupancy model' })}
        </button>
      </section>

      {result && (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <StatCard label={t('occupancyPage.trueOccupancy', { defaultValue: 'True occupancy (ψ)' })} value={`${(result.psi * 100).toFixed(1)}%`} icon={BarChart3} color="emerald" />
            <StatCard label={t('occupancyPage.detectionProb', { defaultValue: 'Detection prob (p)' })} value={`${(result.p * 100).toFixed(1)}%`} icon={BarChart3} color="cyan" />
            <StatCard label={t('occupancyPage.naiveOccupancy', { defaultValue: 'Naive occupancy' })} value={`${(result.naive_occupancy * 100).toFixed(1)}%`} icon={BarChart3} color="amber" />
            <StatCard label={t('occupancyPage.sites', { defaultValue: 'Sites analyzed' })} value={result.n_sites} icon={MapPin} color="violet" />
          </div>

          {siteData.length > 0 && (
            <section className="section-shell">
              <SectionHeader title={t('occupancyPage.siteOccupancy', { defaultValue: 'Site-level occupancy probability' })} />
              <ResponsiveContainer width="100%" height={Math.max(200, siteData.length * 28)}>
                <BarChart data={siteData} layout="vertical" margin={{ left: 80 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" domain={[0, 1]} stroke="#64748b" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="site" stroke="#64748b" tick={{ fontSize: 11 }} width={80} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} formatter={(v) => [`${(v * 100).toFixed(1)}%`, 'Occupancy']} />
                  <Bar dataKey="probability" radius={[0, 4, 4, 0]}>
                    {siteData.map((entry, i) => (
                      <Cell key={i} fill={entry.detected ? COLORS.chart[0] : COLORS.chart[3]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-2 flex gap-4 text-xs text-gray-500">
                <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: COLORS.chart[0] }} />{t('occupancyPage.detected', { defaultValue: 'Detected' })}</span>
                <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: COLORS.chart[3] }} />{t('occupancyPage.undetected', { defaultValue: 'Not detected (inferred)' })}</span>
              </div>
            </section>
          )}

          {targets && targets.length > 0 && (
            <section className="section-shell">
              <SectionHeader title={t('occupancyPage.verificationTargets', { defaultValue: 'Priority verification targets' })} body={t('occupancyPage.verificationBody', { defaultValue: 'Sites where human review would be most informative for reducing occupancy uncertainty.' })} />
              <div className="space-y-2">
                {targets.map((tgt, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 p-3">
                    <div>
                      <p className="text-sm font-medium text-white">{tgt.site}</p>
                      <p className="text-xs text-gray-500">{tgt.reason}</p>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${tgt.priority === 'high' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'}`}>{tgt.priority}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
