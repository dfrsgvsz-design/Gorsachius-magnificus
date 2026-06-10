import React, { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bird,
  Cpu,
  Download,
  Globe2,
  Mic,
  Radio,
  RefreshCw,
  Shield,
  Upload,
  Waves,
  Wifi,
  Zap,
} from 'lucide-react'
import {
  compareEngines,
  exportDetectionsCSV,
  getApiErrorMessage,
  getDetectionStats,
} from '../../lib/api'
import { StatCard, StatusBanner } from '../common'
import { COLORS } from '../../constants'

const WORKFLOW_CARDS = [
  { id: 'soundscape', icon: Waves, color: COLORS.teal },
  { id: 'analyze', icon: Mic, color: COLORS.processBlue },
  { id: 'verify', icon: Shield, color: COLORS.forest },
  { id: 'monitor', icon: Radio, color: COLORS.carnelian },
]

export default function DashboardTab({ health, setActiveTab, refreshHealth, healthFetchedAt }) {
  const { t } = useTranslation()
  const [detStats, setDetStats] = useState(null)
  const [compareResult, setCompareResult] = useState(null)
  const [compareFile, setCompareFile] = useState(null)
  const [comparing, setComparing] = useState(false)
  const [actionError, setActionError] = useState(null)

  useEffect(() => {
    getDetectionStats().then(setDetStats).catch((err) => {
      setActionError(getApiErrorMessage(err, t('dashboardPage.detStatsFailed', { defaultValue: 'Failed to load detection stats' })))
    })
  }, [t])

  const refreshOverview = async () => {
    setActionError(null)
    await Promise.allSettled([
      typeof refreshHealth === 'function' ? refreshHealth() : Promise.resolve(),
      getDetectionStats().then(setDetStats),
    ])
  }

  const handleCompare = async () => {
    if (!compareFile) return
    setComparing(true)
    setActionError(null)
    try {
      const result = await compareEngines(compareFile)
      setCompareResult(result)
    } catch (error) {
      setCompareResult(null)
      setActionError(getApiErrorMessage(error, t('dashboardPage.compareFailed', { defaultValue: 'Engine comparison failed' })))
    } finally {
      setComparing(false)
    }
  }

  const handleExportCSV = async () => {
    try {
      setActionError(null)
      const blob = await exportDetectionsCSV()
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `detections_${new Date().toISOString().slice(0, 10)}.csv`
      anchor.click()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      setActionError(getApiErrorMessage(error, t('dashboardPage.exportFailed', { defaultValue: 'Export failed' })))
    }
  }

  const modelVer = health?.model?.version?.toUpperCase() || 'CNN'
  const numSpecies = health?.num_species_model || health?.num_species || 0
  const totalDetections = detStats?.total || 0
  const pendingReview = detStats?.unverified || detStats?.pending || 0
  const runtimeState = health?.runtime_state || 'ready'
  const isOnline = health?.status === 'ok'
  const lastSync = healthFetchedAt
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(healthFetchedAt))
    : '--:--:--'

  const workflowLabels = {
    soundscape: {
      en: { title: 'Soundscape Analysis', desc: 'Compute ecoacoustic indices (ACI, NDSI, ADI, BIO) and assess ecosystem health against baselines.' },
      zh: { title: '声景分析', desc: '计算声景生态指数（ACI、NDSI、ADI、BIO）并评估生态系统健康状况。' },
    },
    analyze: {
      en: { title: 'Species Detection', desc: 'Upload audio recordings for AI-powered species identification and classification.' },
      zh: { title: '物种检测', desc: '上传音频录音进行 AI 物种识别与分类。' },
    },
    verify: {
      en: { title: 'Detection Review', desc: 'Validate AI detections with expert review before downstream analysis.' },
      zh: { title: '检测审核', desc: '在下游分析前进行专家级 AI 检测验证。' },
    },
    monitor: {
      en: { title: 'Live Monitoring', desc: 'Real-time acoustic data streams from field recording devices.' },
      zh: { title: '实时监测', desc: '来自野外录音设备的实时声学数据流。' },
    },
  }

  const locale = t('tabs.dashboard') === '仪表盘' || t('tabs.dashboard') === '概览' ? 'zh' : 'en'

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="card-elevated overflow-hidden p-5 md:p-8">
        <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div>
            <div className="section-kicker">
              <Waves className="h-3.5 w-3.5" />
              {locale === 'zh' ? '声景生态指数平台' : 'Ecoacoustic Index Platform'}
            </div>
            <h2 className="mt-3 text-xl font-bold md:text-2xl" style={{ color: 'var(--text-primary)' }}>
              {locale === 'zh' ? '声景生态系统健康概览' : 'Ecosystem Acoustic Health Overview'}
            </h2>
            <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {locale === 'zh'
                ? '通过声景指数分析监测生态系统健康状况。平台支持标准声学指数计算、AI 物种检测和基线健康评分。'
                : 'Monitor ecosystem health through soundscape index analysis. The platform supports standard acoustic index computation, AI species detection, and baseline health scoring.'}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button onClick={() => setActiveTab('soundscape')} className="btn-primary">
                <Waves className="h-4 w-4" />
                {locale === 'zh' ? '声景分析' : 'Soundscape Analysis'}
              </button>
              <button onClick={() => setActiveTab('analyze')} className="btn-secondary">
                <Upload className="h-4 w-4" />
                {locale === 'zh' ? '物种检测' : 'Species Detection'}
              </button>
              <button onClick={refreshOverview} className="btn-ghost">
                <RefreshCw className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Status cards */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-1 lg:gap-2">
            <MiniStat label={locale === 'zh' ? '检测记录' : 'Detection Records'} value={totalDetections} icon={BarChart3} />
            <MiniStat label={locale === 'zh' ? '待审核' : 'Pending Review'} value={pendingReview} icon={Shield} />
            <MiniStat label={locale === 'zh' ? '运行状态' : 'Runtime Status'} value={isOnline ? 'Online' : 'Offline'} icon={Activity} online={isOnline} />
            <MiniStat label={locale === 'zh' ? '在线设备' : 'Online Devices'} value={health?.devices_online || 0} icon={Wifi} />
          </div>
        </div>
      </section>

      {actionError && <StatusBanner tone="error" message={actionError} />}

      {/* Key Metrics */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label={locale === 'zh' ? '模型版本' : 'Model Version'} value={modelVer} icon={Cpu} color="teal" />
        <StatCard label={locale === 'zh' ? '可识别物种' : 'Recognizable Species'} value={numSpecies} icon={Bird} color="blue" />
        <StatCard label="BirdNET" value={health?.birdnet_available ? (locale === 'zh' ? '可用' : 'Available') : (locale === 'zh' ? '未安装' : 'Optional')} icon={Globe2} color="forest" />
        <StatCard label={locale === 'zh' ? '最后同步' : 'Last Sync'} value={lastSync} icon={RefreshCw} color="default" />
      </div>

      {/* Workflow cards */}
      <section>
        <h3 className="mb-3 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          {locale === 'zh' ? '分析工作流' : 'Analysis Workflows'}
        </h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {WORKFLOW_CARDS.map((card) => {
            const labels = workflowLabels[card.id]?.[locale] || workflowLabels[card.id]?.en || {}
            return (
              <button
                key={card.id}
                onClick={() => setActiveTab(card.id)}
                className="card-interactive group p-4 text-left"
              >
                <div className="flex items-center justify-between">
                  <div className="rounded-lg p-2" style={{ background: `${card.color}15` }}>
                    <card.icon className="h-5 w-5" style={{ color: card.color }} />
                  </div>
                  <ArrowRight className="h-4 w-4 opacity-0 transition-opacity group-hover:opacity-60" style={{ color: 'var(--text-tertiary)' }} />
                </div>
                <h4 className="mt-3 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {labels.title}
                </h4>
                <p className="mt-1 text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
                  {labels.desc}
                </p>
              </button>
            )
          })}
        </div>
      </section>

      {/* BirdNET Comparison & Export */}
      <section className="card p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <h3 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
              {locale === 'zh' ? '引擎对比与数据导出' : 'Engine Comparison & Data Export'}
            </h3>
            <p className="mt-1 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {locale === 'zh'
                ? '将平台 CNN 模型检测结果与 BirdNET 基准进行对比分析。支持检测记录 CSV 导出。'
                : 'Compare platform CNN detections against BirdNET baseline. Export detection records as CSV.'}
            </p>
          </div>
          <button onClick={handleExportCSV} className="btn-secondary shrink-0">
            <Download className="h-4 w-4" />
            {locale === 'zh' ? '导出 CSV' : 'Export CSV'}
          </button>
        </div>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <label className="flex-1 cursor-pointer">
            <div className="flex items-center gap-2 rounded-lg border px-3 py-2.5 transition-all" style={{ borderColor: 'var(--border-default)' }}>
              <Upload className="h-4 w-4" style={{ color: 'var(--text-tertiary)' }} />
              <span className="truncate text-sm" style={{ color: compareFile ? 'var(--text-primary)' : 'var(--text-tertiary)' }}>
                {compareFile ? compareFile.name : (locale === 'zh' ? '选择音频文件…' : 'Select audio file…')}
              </span>
            </div>
            <input type="file" accept="audio/*" className="hidden" onChange={(event) => setCompareFile(event.target.files?.[0] || null)} />
          </label>
          <button onClick={handleCompare} disabled={!compareFile || comparing} className="btn-primary disabled:opacity-50 sm:w-auto">
            {comparing ? <Zap className="h-4 w-4 animate-pulse" /> : <Globe2 className="h-4 w-4" />}
            {locale === 'zh' ? '运行对比' : 'Compare Engines'}
          </button>
        </div>

        {compareResult && (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <ComparePanel
              title={`${locale === 'zh' ? '平台 CNN' : 'Platform CNN'} (${compareResult.cnn_model?.version || 'v7'})`}
              detections={compareResult.cnn_model?.detections || []}
              color={COLORS.teal}
              emptyLabel={locale === 'zh' ? '无检测结果' : 'No detections returned'}
            />
            <ComparePanel
              title="BirdNET"
              detections={compareResult.birdnet?.detections || []}
              color={COLORS.processBlue}
              emptyLabel={compareResult.birdnet?.available ? (locale === 'zh' ? '无检测结果' : 'No detections returned') : (locale === 'zh' ? 'BirdNET 未安装' : 'BirdNET not installed')}
            />
            {compareResult.agreement && (
              <div className="rounded-xl border p-4 md:col-span-2" style={{ borderColor: 'rgba(0,102,153,0.2)', background: 'rgba(0,102,153,0.03)' }}>
                <p className="text-sm font-semibold" style={{ color: 'var(--cornell-blue)' }}>
                  {locale === 'zh' ? '一致率' : 'Agreement ratio'}:{' '}
                  {Number.isFinite(compareResult.agreement?.agreement_ratio) ? `${(compareResult.agreement.agreement_ratio * 100).toFixed(0)}%` : '--'}
                </p>
                <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {locale === 'zh' ? '共同检出物种' : 'Shared species'}:{' '}
                  {compareResult.agreement.overlap?.join(', ') || (locale === 'zh' ? '无' : 'None')}
                </p>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}

function MiniStat({ label, value, icon: Icon, online }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border p-3" style={{ borderColor: 'var(--border-default)', background: 'white' }}>
      <Icon className="h-4 w-4 shrink-0" style={{ color: 'var(--text-tertiary)' }} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
        <p className="text-sm font-semibold" style={{ color: online === false ? 'var(--cornell-carnelian)' : 'var(--text-primary)' }}>
          {value}
        </p>
      </div>
    </div>
  )
}

function ComparePanel({ title, detections, color, emptyLabel }) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border-default)' }}>
      <p className="mb-3 text-sm font-semibold" style={{ color }}>{title}</p>
      {detections.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{emptyLabel}</p>
      ) : (
        <div className="space-y-2">
          {detections.slice(0, 5).map((detection, index) => (
            <div key={`${title}-${index}`} className="flex items-center justify-between rounded-lg p-2.5" style={{ background: 'var(--surface-secondary)' }}>
              <div className="min-w-0">
                <p className="truncate text-sm" style={{ color: 'var(--text-primary)' }}>
                  {detection.species_chinese || detection.species_scientific}
                </p>
                <p className="truncate text-xs" style={{ color: 'var(--text-tertiary)' }}>{detection.species_scientific}</p>
              </div>
              <span className="text-xs font-medium" style={{ color }}>
                {((detection.confidence || 0) * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
