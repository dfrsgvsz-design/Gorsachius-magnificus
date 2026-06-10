import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BarChart, Bar, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Calendar, Loader2, TrendingDown, TrendingUp } from 'lucide-react'
import { getApiErrorMessage, getPhenology, getPhenologyTrend, getPhenologyOverview } from '../../lib/api'
import { EmptyPanel, LoadingState, PageHero, SectionHeader, StatCard, StatusBanner } from '../common'
import { COLORS } from '../../constants'

export default function PhenologyTab() {
  const { t } = useTranslation()
  const [year, setYear] = useState(new Date().getFullYear())
  const [overview, setOverview] = useState(null)
  const [selectedSpecies, setSelectedSpecies] = useState(null)
  const [detail, setDetail] = useState(null)
  const [trend, setTrend] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getPhenologyOverview(year)
      setOverview(data)
      if (data.species?.length > 0 && !selectedSpecies) {
        setSelectedSpecies(data.species[0].species)
      }
    } catch (err) {
      setError(getApiErrorMessage(err, t('phenologyPage.loadFailed', { defaultValue: 'Failed to load phenology data' })))
    } finally {
      setLoading(false)
    }
  }, [year, t, selectedSpecies])

  useEffect(() => { loadOverview() }, [loadOverview])

  useEffect(() => {
    if (!selectedSpecies) return
    Promise.allSettled([
      getPhenology(selectedSpecies, year),
      getPhenologyTrend(selectedSpecies, `${year - 2},${year - 1},${year}`),
    ]).then(([detailRes, trendRes]) => {
      if (detailRes.status === 'fulfilled') setDetail(detailRes.value)
      if (trendRes.status === 'fulfilled') setTrend(trendRes.value)
    })
  }, [selectedSpecies, year])

  if (loading) return <LoadingState text={t('phenologyPage.loading', { defaultValue: 'Loading phenology...' })} />

  const dailyData = detail?.daily_curve
    ? Object.entries(detail.daily_curve).map(([doy, count]) => ({ doy: Number(doy), count: Number(count) }))
    : []

  const hourlyData = detail?.hourly_pattern
    ? Object.entries(detail.hourly_pattern).map(([h, c]) => ({ hour: Number(h), count: c })).sort((a, b) => a.hour - b.hour)
    : []

  const speciesList = overview?.species || []

  return (
    <div className="space-y-6">
      <PageHero
        kicker={<><Calendar className="h-3.5 w-3.5" />{t('phenologyPage.badge', { defaultValue: 'Acoustic phenology' })}</>}
        title={t('phenologyPage.title', { defaultValue: 'Seasonal vocal activity patterns and phenological trends' })}
        body={t('phenologyPage.body', { defaultValue: 'Analyze when species start and stop calling, identify peak activity periods, and detect multi-year shifts that may signal climate-driven changes.' })}
        metrics={<>
          <StatCard label={t('phenologyPage.speciesTracked', { defaultValue: 'Species tracked' })} value={speciesList.length} icon={Calendar} color="emerald" />
          {detail?.status === 'ok' && <>
            <StatCard label={t('phenologyPage.seasonLength', { defaultValue: 'Season length' })} value={`${detail.season_length_days}d`} icon={Calendar} color="cyan" />
            <StatCard label={t('phenologyPage.totalDetections', { defaultValue: 'Total detections' })} value={detail.total_detections} icon={Calendar} color="violet" />
          </>}
        </>}
      />

      <StatusBanner tone="error" message={error} />

      <div className="flex flex-wrap items-center gap-3">
        <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
          {[...Array(5)].map((_, i) => { const y = new Date().getFullYear() - i; return <option key={y} value={y}>{y}</option> })}
        </select>
        <select value={selectedSpecies || ''} onChange={(e) => setSelectedSpecies(e.target.value)} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
          {speciesList.map((s) => <option key={s.species} value={s.species}>{s.species}</option>)}
        </select>
      </div>

      {speciesList.length === 0 ? (
        <EmptyPanel icon={Calendar} title={t('phenologyPage.noData', { defaultValue: 'No phenology data' })} body={t('phenologyPage.noDataBody', { defaultValue: 'Run acoustic analyses to generate detection data for phenology extraction.' })} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="section-shell">
            <SectionHeader title={t('phenologyPage.seasonalCurve', { defaultValue: 'Seasonal activity curve' })} />
            {dailyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={dailyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="doy" stroke="#64748b" tick={{ fontSize: 11 }} label={{ value: 'Day of year', position: 'insideBottom', offset: -2, fill: '#94a3b8', fontSize: 11 }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                  <Line type="monotone" dataKey="count" stroke={COLORS.chart[0]} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : <p className="py-8 text-center text-sm text-gray-500">{t('phenologyPage.selectSpecies', { defaultValue: 'Select a species to view its seasonal pattern' })}</p>}
          </section>

          <section className="section-shell">
            <SectionHeader title={t('phenologyPage.hourlyPattern', { defaultValue: 'Hourly activity pattern' })} />
            {hourlyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={hourlyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="hour" stroke="#64748b" tick={{ fontSize: 11 }} label={{ value: 'Hour', position: 'insideBottom', offset: -2, fill: '#94a3b8', fontSize: 11 }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="count" fill={COLORS.chart[1]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="py-8 text-center text-sm text-gray-500">—</p>}
          </section>

          {trend && trend.trend !== 'insufficient_data' && (
            <section className="section-shell xl:col-span-2">
              <SectionHeader title={t('phenologyPage.trendAnalysis', { defaultValue: 'Multi-year phenological trend' })} />
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    {trend.first_detection_trend_days_per_year < 0 ? <TrendingDown className="h-4 w-4 text-amber-400" /> : <TrendingUp className="h-4 w-4 text-cyan-400" />}
                    {t('phenologyPage.onsetTrend', { defaultValue: 'Onset trend' })}
                  </div>
                  <p className="mt-2 text-lg font-semibold text-white">{trend.first_detection_trend_days_per_year > 0 ? '+' : ''}{trend.first_detection_trend_days_per_year} {t('phenologyPage.daysPerYear', { defaultValue: 'days/year' })}</p>
                  <p className="mt-1 text-xs text-gray-500">p = {trend.first_detection_p_value}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <p className="text-sm text-gray-400">{t('phenologyPage.peakTrend', { defaultValue: 'Peak trend' })}</p>
                  <p className="mt-2 text-lg font-semibold text-white">{trend.peak_trend_days_per_year > 0 ? '+' : ''}{trend.peak_trend_days_per_year} {t('phenologyPage.daysPerYear', { defaultValue: 'days/year' })}</p>
                  <p className="mt-1 text-xs text-gray-500">p = {trend.peak_p_value}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <p className="text-sm text-gray-400">{t('phenologyPage.interpretation', { defaultValue: 'Interpretation' })}</p>
                  <p className={`mt-2 text-lg font-semibold ${trend.interpretation === 'advancing' ? 'text-amber-300' : trend.interpretation === 'delaying' ? 'text-cyan-300' : 'text-gray-300'}`}>
                    {trend.interpretation === 'advancing' ? t('phenologyPage.advancing', { defaultValue: '⚠ Phenology advancing' }) : trend.interpretation === 'delaying' ? t('phenologyPage.delaying', { defaultValue: 'Phenology delaying' }) : t('phenologyPage.stable', { defaultValue: 'Stable' })}
                  </p>
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
