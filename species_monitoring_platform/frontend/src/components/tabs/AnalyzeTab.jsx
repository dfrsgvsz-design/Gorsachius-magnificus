import React, { useState, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  BarChart3,
  Bird,
  FileAudio,
  Loader2,
  Shield,
  Upload,
  Waves,
  Zap,
  Camera,
  ImageIcon,
  MapPin as MapPinIcon,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  analyzeAudio,
  analyzeImage,
  analyzeBatch,
  compareSpectrograms,
  generateReport,
  getApiErrorMessage,
} from '../../lib/api'
import { COLORS } from '../../constants'
import { usePlatformConfig } from '../../lib/PlatformConfigContext'
import {
  ConfidenceBadge,
  DiversityRow,
  EmptyPanel,
  InfoNote,
  PageHero,
  SectionHeader,
  StatCard,
  StatusBanner,
} from '../common'

function formatNumber(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '--'
  return Number(value).toFixed(digits)
}

export default function AnalyzeTab() {
  const { t } = useTranslation()
  const platformConfig = usePlatformConfig()
  const featureFlags = platformConfig.features || {}
  const [file, setFile] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [topK, setTopK] = useState(5)
  const [threshold, setThreshold] = useState(0.1)
  const [batchFiles, setBatchFiles] = useState([])
  const [batchResult, setBatchResult] = useState(null)
  const [batchAnalyzing, setBatchAnalyzing] = useState(false)
  const [reportGenerating, setReportGenerating] = useState(false)
  const [lastAnalyzedAt, setLastAnalyzedAt] = useState(null)

  useEffect(() => () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl)
  }, [audioUrl])

  const setSelectedFile = useCallback((nextFile) => {
    if (!nextFile) return
    if (nextFile.size > 100 * 1024 * 1024) {
      setError(t('analyzePage.fileTooLarge'))
      return
    }

    setFile(nextFile)
    setResult(null)
    setError(null)
    setAudioUrl((currentUrl) => {
      if (currentUrl) URL.revokeObjectURL(currentUrl)
      return URL.createObjectURL(nextFile)
    })
  }, [t])

  const handleDrop = useCallback((event) => {
    event.preventDefault()
    setSelectedFile(event.dataTransfer?.files?.[0])
  }, [setSelectedFile])

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files?.[0])
  }

  const handleReset = () => {
    setFile(null)
    setResult(null)
    setError(null)
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioUrl(null)
  }

  const handleAnalyze = async () => {
    if (!file) return
    setAnalyzing(true)
    setError(null)
    setResult(null)

    try {
      const data = await analyzeAudio(file, topK, threshold)
      setResult(data)
      setLastAnalyzedAt(Date.now())
    } catch (err) {
      setError(getApiErrorMessage(err, t('analyzePage.analysisFailed')))
    } finally {
      setAnalyzing(false)
    }
  }

  const handleBatchAnalyze = async () => {
    if (batchFiles.length === 0) return
    setBatchAnalyzing(true)
    setError(null)
    setBatchResult(null)

    try {
      const data = await analyzeBatch(batchFiles, topK)
      setBatchResult(data)
      setLastAnalyzedAt(Date.now())
    } catch (err) {
      setError(getApiErrorMessage(err, t('analyzePage.batchFailed')))
    } finally {
      setBatchAnalyzing(false)
    }
  }

  const handleGenerateReport = async () => {
    if (!file) return
    setReportGenerating(true)
    try {
      const html = await generateReport(file, t('analyzePage.defaultSiteName', { defaultValue: 'Field site' }))
      const blob = new Blob([html], { type: 'text/html' })
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 5000)
    } catch (err) {
      setError(getApiErrorMessage(err, t('analyzePage.reportFailed')))
    } finally {
      setReportGenerating(false)
    }
  }

  const lastAnalyzedLabel = lastAnalyzedAt
    ? new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(lastAnalyzedAt))
    : '--:--:--'

  return (
    <div className="space-y-6">
      <PageHero
        kicker={(
          <>
            <Bird className="h-3.5 w-3.5" />
            {t('analyzePage.badge')}
          </>
        )}
        title={t('analyzePage.title')}
        body={t('analyzePage.body')}
        aside={(
          <>
            <MiniMetric
              label={t('analyzePage.singleFile')}
              value={file ? t('analyzePage.loaded') : t('analyzePage.waiting')}
              tone="emerald"
            />
            <MiniMetric label={t('analyzePage.topK')} value={String(topK)} tone="cyan" />
            <MiniMetric label={t('analyzePage.threshold')} value={threshold.toFixed(2)} tone="amber" />
          </>
        )}
      />

      <section className="section-shell space-y-4 md:space-y-5">
        <div
          className="upload-zone cursor-pointer"
          onDrop={handleDrop}
          onDragOver={(event) => event.preventDefault()}
          onClick={() => document.getElementById('audio-input')?.click()}
        >
          <input
            id="audio-input"
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={handleFileChange}
          />
          <FileAudio className="mx-auto mb-2 h-8 w-8 text-white/40 md:mb-3 md:h-12 md:w-12" />
          {file ? (
            <div className="space-y-0.5 md:space-y-1">
              <p className="truncate text-sm font-medium text-[#30D158]">{file.name}</p>
              <p className="text-xs text-white/40 md:text-sm">
                {t('analyzePage.readyForAnalysis', {
                  size: (file.size / 1024 / 1024).toFixed(2),
                })}
              </p>
            </div>
          ) : (
            <div className="space-y-0.5 md:space-y-1">
              <p className="text-sm text-white/50">{t('analyzePage.dropTitle')}</p>
              <p className="text-xs text-white/25 md:text-sm">{t('analyzePage.dropHint')}</p>
            </div>
          )}
        </div>

        <div className="space-y-3 md:space-y-0 md:flex md:flex-col md:gap-4 lg:flex-row lg:items-center">
          <div className="flex items-center gap-4 md:gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs text-white/40 md:text-sm">{t('analyzePage.topK')}</label>
              <select
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                className="touch-button rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm md:py-1.5"
              >
                {[3, 5, 10].map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>

            <div className="flex flex-1 items-center gap-2">
              <label className="shrink-0 text-xs text-white/40 md:text-sm">{t('analyzePage.confidenceThreshold')}</label>
              <input
                type="range"
                min="0"
                max="0.5"
                step="0.05"
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value))}
                className="w-full min-w-[60px] md:w-28"
              />
              <span className="text-xs font-medium text-[#30D158] md:text-sm">{threshold.toFixed(2)}</span>
            </div>
          </div>

          <div className="flex gap-2 lg:ml-auto">
            {(file || result) && (
              <button
                onClick={handleReset}
                disabled={analyzing}
                className="touch-button flex-1 rounded-[12px] bg-white/[0.06] px-4 py-2.5 text-sm text-white/50 transition-all active:scale-[0.98] disabled:opacity-40 md:flex-none"
              >
                {t('analyzePage.reset')}
              </button>
            )}
            <button
              onClick={handleAnalyze}
              disabled={!file || analyzing}
              className="touch-button flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-gradient-to-r from-[#30D158] to-[#0A84FF] px-5 py-2.5 text-sm font-medium transition-all active:scale-[0.98] disabled:opacity-40 md:flex-none md:px-6"
            >
              {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
              {analyzing ? t('analyzePage.analyzing') : t('analyzePage.runAnalysis')}
            </button>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-3 md:gap-4">
          <InfoNote title={t('analyzePage.interpretationSnapshot')} body={t('analyzePage.nextStepReady')} tone="emerald" />
          <InfoNote title={t('analyzePage.diversityContext')} body={t('analyzePage.diversity.shannonDesc')} tone="cyan" />
          <InfoNote title={t('analyzePage.reviewStatus')} body={t('analyzePage.reviewReady')} tone="amber" />
        </div>
      </section>

      {audioUrl && (
        <section className="section-shell">
          <div className="flex flex-wrap items-center gap-3">
            <Waves className="h-5 w-5 text-[#0A84FF]" />
            <span className="text-sm text-white/50">{file?.name}</span>
            {result && featureFlags.html_report !== false && (
              <button
                onClick={handleGenerateReport}
                disabled={reportGenerating}
                className="ml-auto flex items-center gap-1 rounded-[12px] border border-white/[0.06] bg-[#BF5AF2]/15 px-3 py-1.5 text-xs text-[#BF5AF2] transition-all hover:bg-[#BF5AF2]/25 disabled:opacity-50"
              >
                {reportGenerating ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileAudio className="h-3 w-3" />}
                {reportGenerating ? t('analyzePage.generating') : t('analyzePage.openReport')}
              </button>
            )}
          </div>
          <audio
            src={audioUrl}
            controls
            className="mt-3 h-10 w-full"
            style={{ filter: 'invert(1) hue-rotate(180deg)', opacity: 0.8 }}
          />
        </section>
      )}

      <section className="section-shell space-y-3 md:space-y-4">
        <SectionHeader
          title={(
            <span className="flex items-center gap-2 text-[#0A84FF]">
              <Zap className="h-4 w-4" />
              {t('analyzePage.batchTitle')}
            </span>
          )}
          body={t('analyzePage.batchBody')}
          action={<div className="metric-chip">{t('analyzePage.filesSelected', { count: batchFiles.length })}</div>}
        />

        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex-1 cursor-pointer">
            <div className="touch-button flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2.5 active:scale-[0.98]">
              <Upload className="h-4 w-4 text-white/40" />
              <span className="truncate text-sm text-white/50">
                {batchFiles.length > 0
                  ? t('analyzePage.readyBatch', { count: batchFiles.length })
                  : t('analyzePage.chooseMultiple')}
              </span>
            </div>
            <input
              type="file"
              accept="audio/*"
              multiple
              className="hidden"
              onChange={(event) => setBatchFiles(Array.from(event.target.files || []))}
            />
          </label>
          <button
            onClick={handleBatchAnalyze}
            disabled={batchFiles.length === 0 || batchAnalyzing}
            className="touch-button flex items-center justify-center gap-1.5 rounded-[12px] border border-white/[0.06] bg-[#0A84FF]/15 px-4 py-2.5 text-sm text-[#0A84FF] active:scale-[0.98] disabled:opacity-50"
          >
            {batchAnalyzing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            {t('analyzePage.batchAnalyze')}
          </button>
        </div>

        {batchResult && (
          <div className="surface-card-muted">
            <div className="flex flex-wrap gap-4 text-xs text-white/40">
              <span>{t('analyzePage.files')}: {batchResult.num_files || 0}</span>
              <span>{t('analyzePage.uniqueSpecies')}: {batchResult.total_unique_species || 0}</span>
              <span>{t('analyzePage.shannon')}: {formatNumber(batchResult.aggregated_diversity?.shannon_h, 3)}</span>
            </div>
            <div className="mt-3 space-y-1">
              {(batchResult.file_results || []).slice(0, 10).map((fileResult, index) => (
                <div
                  key={`${fileResult.filename}-${index}`}
                  className="flex justify-between gap-3 border-b border-white/[0.04] py-1 text-xs last:border-0"
                >
                  <span className="max-w-[240px] truncate text-white/50">{fileResult.filename}</span>
                  <span className="text-[#30D158]">
                    {fileResult.top_species?.species_chinese
                      || fileResult.top_species?.species_scientific
                      || t('analyzePage.noSpeciesAboveThreshold')}
                    {' '}
                    ({((fileResult.top_species?.confidence || 0) * 100).toFixed(0)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <StatusBanner tone="error" message={error} />

      {result && <AnalysisResults result={result} />}

      <SpectrogramCompare />

      <ImageAnalyzer />
    </div>
  )
}

function SpectrogramCompare() {
  const { t } = useTranslation()
  const [fileA, setFileA] = useState(null)
  const [fileB, setFileB] = useState(null)
  const [comparing, setComparing] = useState(false)
  const [compareResult, setCompareResult] = useState(null)
  const [compareError, setCompareError] = useState(null)

  const handleCompare = async () => {
    if (!fileA || !fileB) return
    setComparing(true)
    setCompareError(null)
    setCompareResult(null)
    try {
      const data = await compareSpectrograms(fileA, fileB)
      setCompareResult(data)
    } catch (err) {
      setCompareError(getApiErrorMessage(err, t('analyzePage.compareFailed') || 'Comparison failed'))
    } finally {
      setComparing(false)
    }
  }

  return (
    <section className="section-shell space-y-3 md:space-y-4">
      <div>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white md:text-base">
          <Waves className="h-4 w-4 text-[#BF5AF2]" />
          {t('analyzePage.spectrogramCompare') || 'Spectrogram Comparison'}
        </h3>
        <p className="mt-1 text-xs leading-5 text-white/40 md:text-sm">
          {t('analyzePage.spectrogramCompareDesc') || 'Upload two audio files to compare their frequency patterns side by side. Useful for species identification, dialect comparison, and detection verification.'}
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 md:gap-3">
        <label className="cursor-pointer">
          <div className="touch-button flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2.5 active:scale-[0.98]">
            <Upload className="h-4 w-4 shrink-0 text-[#30D158]" />
            <span className="truncate text-sm text-white/50">
              {fileA ? fileA.name : (t('analyzePage.selectFileA') || 'Audio A — select file')}
            </span>
          </div>
          <input type="file" accept="audio/*" className="hidden" onChange={(e) => setFileA(e.target.files?.[0] || null)} />
        </label>
        <label className="cursor-pointer">
          <div className="touch-button flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2.5 active:scale-[0.98]">
            <Upload className="h-4 w-4 shrink-0 text-[#0A84FF]" />
            <span className="truncate text-sm text-white/50">
              {fileB ? fileB.name : (t('analyzePage.selectFileB') || 'Audio B — select file')}
            </span>
          </div>
          <input type="file" accept="audio/*" className="hidden" onChange={(e) => setFileB(e.target.files?.[0] || null)} />
        </label>
      </div>

      <button
        onClick={handleCompare}
        disabled={!fileA || !fileB || comparing}
        className="touch-button flex items-center justify-center gap-2 rounded-[12px] border border-white/[0.06] bg-[#BF5AF2]/15 px-5 py-2.5 text-sm font-medium text-[#BF5AF2] active:scale-[0.97] disabled:opacity-40"
      >
        {comparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Waves className="h-4 w-4" />}
        {comparing ? (t('analyzePage.comparing') || 'Comparing...') : (t('analyzePage.runCompare') || 'Compare spectrograms')}
      </button>

      {compareError && (
        <p className="rounded-2xl border border-white/[0.06] bg-[#FF453A]/8 px-3 py-2 text-xs text-[#FF453A]">{compareError}</p>
      )}

      {compareResult && (
        <div className="grid gap-3 md:gap-4 xl:grid-cols-2">
          {['a', 'b'].map((key) => {
            const item = compareResult[key]
            if (!item) return null
            return (
              <div key={key} className="chart-frame space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-medium text-white/50 md:text-sm">
                    {item.filename} <span className="text-white/25">({item.duration}s)</span>
                  </h4>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                    key === 'a' ? 'border-white/[0.06] bg-[#30D158]/10 text-[#30D158]' : 'border-white/[0.06] bg-[#0A84FF]/10 text-[#0A84FF]'
                  }`}>
                    {key === 'a' ? 'A' : 'B'}
                  </span>
                </div>
                {item.spectrogram_image && (
                  <img src={`data:image/png;base64,${item.spectrogram_image}`} alt={`Spectrogram ${key.toUpperCase()}`} className="w-full rounded-lg" />
                )}
                {item.waveform_image && (
                  <img src={`data:image/png;base64,${item.waveform_image}`} alt={`Waveform ${key.toUpperCase()}`} className="w-full rounded-lg" />
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function AnalysisResults({ result }) {
  const { t } = useTranslation()
  const summary = result?.summary || {}
  const speciesBreakdown = summary.species_breakdown || []
  const alpha = summary.alpha_diversity || {}
  const accumulation = summary.accumulation_curve || {}
  const detections = result?.detections || []
  const topSpecies = speciesBreakdown[0]

  const barData = speciesBreakdown.slice(0, 10).map((species) => {
    const name = String(species.species ?? '')
    return {
      name: name ? name.split(' ').map((w) => w[0] || '').join('').slice(0, 4) : '?',
      fullName: name || '--',
      count: species.count,
    }
  })

  const pieData = speciesBreakdown.slice(0, 8).map((species, index) => {
    const name = String(species.species ?? '')
    const parts = name.split(/\s+/)
    return {
      name: parts[1] || parts[0] || '--',
      value: species.count,
      fill: COLORS[index % COLORS.length],
    }
  })

  const accumulationData = (accumulation.time_points || []).map((timePoint, index) => ({
    time: timePoint,
    species: accumulation.cumulative_species?.[index] || 0,
  }))

  const reviewReadiness = summary.total_detections > 0
    ? t('analyzePage.reviewReady')
    : t('analyzePage.reviewEmpty')

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-2 md:grid-cols-2 md:gap-4 xl:grid-cols-4">
        <StatCard label={t('analyzePage.detectedSpecies')} value={summary.unique_species ?? 0} icon={Bird} color="emerald" />
        <StatCard label={t('analyzePage.detectionEvents')} value={summary.total_detections ?? 0} icon={Activity} color="cyan" />
        <StatCard label={t('analyzePage.shannon')} value={formatNumber(alpha.shannon_index)} icon={BarChart3} color="violet" />
        <StatCard label={t('analyzePage.reviewStatus')} value={reviewReadiness} icon={Shield} color="amber" />
      </section>

      <section className="grid gap-3 md:gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="section-shell">
          <h3 className="subsection-title">{t('analyzePage.interpretationSnapshot')}</h3>
          <div className="mt-3 grid gap-2 md:mt-4 md:grid-cols-2 md:gap-4">
            <InsightCard
              title={t('analyzePage.topSignal')}
              tone="emerald"
              body={topSpecies
                ? t('analyzePage.topSignalBody', { species: topSpecies.species, count: topSpecies.count })
                : t('analyzePage.topSignalEmpty')}
            />
            <InsightCard
              title={t('analyzePage.nextStep')}
              tone="cyan"
              body={summary.total_detections > 0
                ? t('analyzePage.nextStepReady')
                : t('analyzePage.nextStepEmpty')}
            />
          </div>
        </div>

        <div className="section-shell">
          <h3 className="subsection-title">{t('analyzePage.diversityContext')}</h3>
          <div className="mt-3 space-y-1.5 md:mt-4 md:space-y-2">
            <DiversityRow label={t('analyzePage.diversity.richness')} value={alpha.species_richness} desc={t('analyzePage.diversity.richnessDesc')} />
            <DiversityRow label={t('analyzePage.diversity.shannon')} value={formatNumber(alpha.shannon_index)} desc={t('analyzePage.diversity.shannonDesc')} />
            <DiversityRow label={t('analyzePage.diversity.simpson')} value={formatNumber(alpha.simpson_index)} desc={t('analyzePage.diversity.simpsonDesc')} />
            <DiversityRow label={t('analyzePage.diversity.pielou')} value={formatNumber(alpha.pielou_evenness)} desc={t('analyzePage.diversity.pielouDesc')} />
            <DiversityRow label={t('analyzePage.diversity.chao1')} value={formatNumber(alpha.chao1_estimate)} desc={t('analyzePage.diversity.chao1Desc')} />
            <DiversityRow label={t('analyzePage.diversity.total')} value={alpha.total_detections ?? summary.total_detections ?? 0} desc={t('analyzePage.diversity.totalDesc')} />
          </div>
        </div>
      </section>

      {!speciesBreakdown.length && (
        <EmptyPanel
          icon={Bird}
          title={t('analyzePage.noSpeciesAboveThreshold')}
          body={t('analyzePage.nextStepEmpty')}
        />
      )}

      <section className="grid gap-3 md:gap-4 xl:grid-cols-2">
        {result?.waveform_image && (
          <div className="chart-frame">
            <h3 className="mb-2 flex items-center gap-2 text-xs font-medium text-white/50 md:mb-3 md:text-sm">
              <Waves className="h-3.5 w-3.5 text-[#0A84FF] md:h-4 md:w-4" />
              {t('analyzePage.waveform')}
            </h3>
            <img
              src={`data:image/png;base64,${result.waveform_image}`}
              alt={t('analyzePage.waveform')}
              className="w-full rounded-lg"
            />
          </div>
        )}

        {result?.spectrogram_image && (
          <div className="chart-frame">
            <h3 className="mb-2 flex items-center gap-2 text-xs font-medium text-white/50 md:mb-3 md:text-sm">
              <Activity className="h-3.5 w-3.5 text-[#30D158] md:h-4 md:w-4" />
              {t('analyzePage.spectrogram')}
            </h3>
            <img
              src={`data:image/png;base64,${result.spectrogram_image}`}
              alt={t('analyzePage.spectrogram')}
              className="w-full rounded-lg"
            />
          </div>
        )}
      </section>

      <section className="grid gap-3 md:gap-4 xl:grid-cols-2">
        {barData.length > 0 && (
          <div className="chart-frame">
            <h3 className="mb-2 text-xs font-medium text-white/50 md:mb-3 md:text-sm">{t('analyzePage.detectionFrequency')}</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData} margin={{ left: -10, right: 4, top: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="name" stroke="rgba(255,255,255,0.25)" fontSize={11} />
                <YAxis stroke="rgba(255,255,255,0.25)" fontSize={11} width={32} />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(0,0,0,0.8)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: '12px',
                    fontSize: '12px',
                  }}
                  labelFormatter={(value, payload) => payload?.[0]?.payload?.fullName || value}
                />
                <Bar dataKey="count" fill="#30D158" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {pieData.length > 0 && (
          <div className="chart-frame">
            <h3 className="mb-2 text-xs font-medium text-white/50 md:mb-3 md:text-sm">{t('analyzePage.speciesComposition')}</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={72}
                  paddingAngle={3}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  fontSize={11}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`${entry.name}-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: 'rgba(0,0,0,0.8)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: '12px',
                    fontSize: '12px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {accumulationData.length > 0 && (
        <section className="chart-frame">
          <h3 className="mb-2 text-xs font-medium text-white/50 md:mb-3 md:text-sm">{t('analyzePage.accumulation')}</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={accumulationData} margin={{ left: -10, right: 4, top: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="time" stroke="rgba(255,255,255,0.25)" fontSize={11} />
              <YAxis stroke="rgba(255,255,255,0.25)" fontSize={11} width={32} />
              <Tooltip
                contentStyle={{
                  background: 'rgba(0,0,0,0.8)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
              <Line
                type="monotone"
                dataKey="species"
                stroke="#0A84FF"
                strokeWidth={2}
                dot={{ r: 2.5, fill: '#0A84FF' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </section>
      )}

      <section className="section-shell">
        <h3 className="mb-3 text-sm font-medium text-white/50">{t('analyzePage.evidenceTable')}</h3>
        <div className="data-table-wrap">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06]">
                <th className="px-3 py-2 text-left text-white/40">{t('analyzePage.table.scientificName')}</th>
                <th className="px-3 py-2 text-left text-white/40">{t('analyzePage.table.localLabel')}</th>
                <th className="px-3 py-2 text-right text-white/40">{t('analyzePage.table.detections')}</th>
                <th className="px-3 py-2 text-right text-white/40">{t('analyzePage.table.avgConfidence')}</th>
                <th className="px-3 py-2 text-right text-white/40">{t('analyzePage.table.maxConfidence')}</th>
                <th className="px-3 py-2 text-right text-white/40">{t('analyzePage.table.firstSeen')}</th>
              </tr>
            </thead>
            <tbody>
              {speciesBreakdown.map((species, index) => (
                <tr key={`${species.species}-${index}`} className="border-b border-white/[0.04] hover:bg-white/[0.04]">
                  <td className="px-3 py-2 font-mono italic text-[#30D158]">{species.species}</td>
                  <td className="px-3 py-2">
                    {detections.find((detection) => detection.species === species.species)?.species_chinese || '--'}
                  </td>
                  <td className="px-3 py-2 text-right">{species.count}</td>
                  <td className="px-3 py-2 text-right"><ConfidenceBadge value={species.avg_confidence} /></td>
                  <td className="px-3 py-2 text-right"><ConfidenceBadge value={species.max_confidence} /></td>
                  <td className="px-3 py-2 text-right text-white/50">{formatNumber(species.first_detection_time, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function MiniMetric({ label, value, tone }) {
  const tones = {
    emerald: 'border-white/[0.06] bg-[#30D158]/10 text-[#30D158]',
    cyan: 'border-white/[0.06] bg-[#0A84FF]/10 text-[#0A84FF]',
    amber: 'border-white/[0.06] bg-[#FF9F0A]/10 text-[#FF9F0A]',
  }

  return (
    <div className={`rounded-2xl border p-3 ${tones[tone] || tones.emerald}`}>
      <p className="text-[11px] uppercase tracking-[0.16em] text-white/50">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
    </div>
  )
}

function InsightCard({ title, body, tone }) {
  const tones = {
    emerald: 'border-white/[0.06] bg-[#30D158]/10',
    cyan: 'border-white/[0.06] bg-[#0A84FF]/10',
  }

  return (
    <div className={`rounded-2xl border p-4 ${tones[tone] || tones.emerald}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/50">{title}</p>
      <p className="mt-2 text-sm leading-6 text-white/60">{body}</p>
    </div>
  )
}

function ImageAnalyzer() {
  const { t } = useTranslation()
  const [imageFile, setImageFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [imgError, setImgError] = useState(null)

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 20 * 1024 * 1024) {
      setImgError(t('analyzePage.imageTooLarge', { defaultValue: 'Image too large (max 20MB)' }))
      return
    }
    if (preview) URL.revokeObjectURL(preview)
    setImageFile(file)
    setResult(null)
    setImgError(null)
    const url = URL.createObjectURL(file)
    setPreview(url)
  }

  const handleAnalyze = async () => {
    if (!imageFile) return
    setAnalyzing(true)
    setImgError(null)
    try {
      const data = await analyzeImage(imageFile)
      setResult(data)
    } catch (err) {
      setImgError(getApiErrorMessage(
        err,
        t('analyzePage.imageAnalysisFailed', { defaultValue: 'Image analysis failed' }),
      ))
    } finally {
      setAnalyzing(false)
    }
  }

  const handleReset = () => {
    setImageFile(null)
    setResult(null)
    setImgError(null)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
  }

  const exif = result?.exif || {}

  return (
    <section className="section-shell space-y-3 md:space-y-4">
      <div>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white md:text-base">
          <Camera className="h-4 w-4 text-[#FF9F0A]" />
          {t('analyzePage.imageAnalysis') || 'Bird Image Analysis'}
        </h3>
        <p className="mt-1 text-xs leading-5 text-white/40 md:text-sm">
          {t('analyzePage.imageAnalysisDesc') || 'Upload a bird photo to extract GPS location, timestamp, and run visual classification. Results are stored for cross-referencing with acoustic detections.'}
        </p>
      </div>

      {!imageFile ? (
        <label className="cursor-pointer">
          <div className="upload-zone flex flex-col items-center gap-2">
            <ImageIcon className="h-8 w-8 text-white/40 md:h-10 md:w-10" />
            <p className="text-sm text-white/50">{t('analyzePage.selectImage') || 'Select or drop a bird photo'}</p>
            <p className="text-xs text-white/25">JPEG, PNG, HEIC (max 20MB)</p>
          </div>
          <input type="file" accept="image/*" className="hidden" onChange={handleImageSelect} />
        </label>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 md:gap-4">
          <div className="relative overflow-hidden rounded-2xl border border-white/[0.06]">
            {preview && <img src={preview} alt="Preview" className="w-full rounded-2xl object-cover" style={{ maxHeight: 300 }} />}
            <div className="absolute bottom-2 left-2 rounded-[12px] bg-black/60 px-2 py-1 text-[11px] text-white backdrop-blur">
              {imageFile.name} ({(imageFile.size / 1024 / 1024).toFixed(1)} MB)
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex gap-2">
              <button
                onClick={handleAnalyze}
                disabled={analyzing}
                className="touch-button flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-gradient-to-r from-[#FF9F0A] to-[#FF453A] px-4 py-2.5 text-sm font-medium text-white active:scale-[0.97] disabled:opacity-40"
              >
                {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
                {analyzing
                  ? t('analyzePage.analyzingImage', { defaultValue: 'Analyzing...' })
                  : t('analyzePage.analyzeImage', { defaultValue: 'Analyze image' })}
              </button>
              <button onClick={handleReset} className="touch-button rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-2.5 text-sm text-white/50 active:scale-[0.97]">
                {t('analyzePage.reset')}
              </button>
            </div>

            {result && (
              <>
                <div className="space-y-1.5">
                  {exif.latitude != null && (
                    <div className="mobile-stat-row">
                      <MapPinIcon className="h-3.5 w-3.5 text-[#30D158]" />
                      <span className="text-xs text-white/50">{exif.latitude}, {exif.longitude}</span>
                      {exif.altitude != null && <span className="text-[11px] text-white/25">{exif.altitude}m</span>}
                    </div>
                  )}
                  {exif.datetime && (
                    <div className="mobile-stat-row">
                      <Camera className="h-3.5 w-3.5 text-[#0A84FF]" />
                      <span className="text-xs text-white/50">{exif.datetime}</span>
                      {exif.camera_model && <span className="text-[11px] text-white/25">{exif.camera_model}</span>}
                    </div>
                  )}
                  <div className="mobile-stat-row">
                    <ImageIcon className="h-3.5 w-3.5 text-[#FF9F0A]" />
                    <span className="text-xs text-white/50">{exif.width}×{exif.height} {exif.format}</span>
                  </div>
                </div>

                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/25">
                    {t('analyzePage.classification', { defaultValue: 'Classification' })}
                  </p>
                  <div className="space-y-1">
                    {(result.classification || []).map((pred, i) => (
                      <div key={`${pred.label}-${i}`} className="flex items-center justify-between gap-2 text-xs">
                        <span className={pred.is_bird_related ? 'font-medium text-[#30D158]' : 'text-white/50'}>{pred.label}</span>
                        <span className="text-white/25">{(pred.confidence * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                  {result.bird_predictions?.length > 0 && (
                    <p className="mt-2 text-[11px] text-[#30D158]">
                      {t('analyzePage.birdRelated', { defaultValue: 'Bird-related' })}
                      : {result.bird_predictions.map((p) => p.label).join(', ')}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {imgError && <p className="rounded-2xl border border-white/[0.06] bg-[#FF453A]/8 px-3 py-2 text-xs text-[#FF453A]">{imgError}</p>}
    </section>
  )
}
