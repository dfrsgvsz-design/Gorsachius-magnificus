import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bird,
  ClipboardCheck,
  Cpu,
  Database,
  Download,
  FolderOpen,
  Layers3,
  Loader2,
  Map,
  Mic,
  Microscope,
  RefreshCw,
  Shield,
  Upload,
  Wifi,
  Zap,
} from 'lucide-react'
import {
  compareEngines,
  exportDetectionsCSV,
  getApiErrorMessage,
  getDetectionStats,
} from '../../lib/api'
// uses local MetricCard/SystemCard/ComparePanel

const ACCENT_MAP = {
  emerald: {
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/20',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400',
  },
  cyan: {
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/20',
    text: 'text-cyan-400',
    dot: 'bg-cyan-400',
  },
  violet: {
    bg: 'bg-violet-500/10',
    border: 'border-violet-500/20',
    text: 'text-violet-400',
    dot: 'bg-violet-400',
  },
  amber: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  red: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/20',
    text: 'text-red-400',
    dot: 'bg-red-400',
  },
}

function accent(name) {
  return ACCENT_MAP[name] || ACCENT_MAP.emerald
}

const QUICK_ACTIONS = [
  { id: 'fieldops', icon: FolderOpen, color: 'emerald', labelKey: 'dashboardPage.quickActions.fieldSurvey', descKey: 'dashboardPage.quickActions.fieldSurveyDesc' },
  { id: 'analyze', tab: 'monitor', icon: Mic, color: 'cyan', labelKey: 'dashboardPage.quickActions.analyzeAudio', descKey: 'dashboardPage.quickActions.analyzeAudioDesc' },
  { id: 'verify', icon: Shield, color: 'violet', labelKey: 'dashboardPage.quickActions.reviewDetections', descKey: 'dashboardPage.quickActions.reviewDetectionsDesc' },
  { id: 'species', icon: Database, color: 'amber', labelKey: 'dashboardPage.quickActions.speciesDB', descKey: 'dashboardPage.quickActions.speciesDBDesc' },
  { id: 'monitor', icon: Activity, color: 'emerald', labelKey: 'dashboardPage.quickActions.monitoring', descKey: 'dashboardPage.quickActions.monitoringDesc' },
  { id: 'sdm', icon: Map, color: 'cyan', labelKey: 'dashboardPage.quickActions.distribution', descKey: 'dashboardPage.quickActions.distributionDesc' },
]

export default function DashboardTab({
  health, setActiveTab, refreshHealth, healthFetchedAt,
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
  const [detStats, setDetStats] = useState(null)
  const [compareResult, setCompareResult] = useState(null)
  const [compareFile, setCompareFile] = useState(null)
  const [comparing, setComparing] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)

  useEffect(() => {
    setStatsLoading(true)
    getDetectionStats()
      .then(setDetStats)
      .catch(() => {})
      .finally(() => setStatsLoading(false))
  }, [])

  const modelVer = health?.model?.version?.toUpperCase() || 'CNN'
  const numSpecies = health?.num_species_model || health?.num_species || 0
  const totalDetections = detStats?.total || 0
  const pendingReview = detStats?.unverified || detStats?.pending || 0
  const isOnline = health?.status === 'ok'
  const coverage = health?.species_coverage || {}
  const coverageRatio = coverage.coverage_ratio != null
    ? `${(coverage.coverage_ratio * 100).toFixed(0)}%`
    : '--'
  const healthWarnings = (Array.isArray(health?.warnings) ? health.warnings : [])
    .filter((w) => w.level === 'error' || w.level === 'warning')
  const lastSync = healthFetchedAt
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(healthFetchedAt))
    : '--:--'

  const handleCompare = async () => {
    if (!compareFile) return
    setComparing(true)
    setActionError(null)
    try {
      setCompareResult(await compareEngines(compareFile))
    } catch (err) {
      setCompareResult(null)
      setActionError(getApiErrorMessage(err, t('dashboardPage.compareFailed')))
    } finally {
      setComparing(false)
    }
  }

  const handleExportCSV = async () => {
    try {
      setActionError(null)
      const blob = await exportDetectionsCSV()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `detections_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setActionError(getApiErrorMessage(err, t('dashboardPage.exportFailed')))
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Welcome header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-white sm:text-2xl">
            {locale === 'zh' ? '系统总览' : 'System Overview'}
          </h2>
          <p className="mt-1 text-sm text-white/40">
            {locale === 'zh'
              ? `模型 ${modelVer} · ${numSpecies} 物种 · 上次同步 ${lastSync}`
              : `Model ${modelVer} · ${numSpecies} species · Last sync ${lastSync}`
            }
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExportCSV} className="btn-secondary btn-sm">
            <Download className="h-3.5 w-3.5" />
            {locale === 'zh' ? '导出' : 'Export'}
          </button>
          <button onClick={refreshHealth} className="btn-secondary btn-sm">
            <RefreshCw className="h-3.5 w-3.5" />
            {locale === 'zh' ? '刷新' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Warnings */}
      {actionError && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {actionError}
        </div>
      )}

      {healthWarnings.length > 0 && (
        <div className="space-y-2">
          {healthWarnings.slice(0, 2).map((w) => (
            <div
              key={w.code}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${
                w.level === 'error'
                  ? 'border-red-500/20 bg-red-500/10 text-red-400'
                  : 'border-amber-500/20 bg-amber-500/10 text-amber-400'
              }`}
            >
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span className="font-medium">{w.title}:</span>
              <span className="text-white/50">{w.detail}</span>
            </div>
          ))}
        </div>
      )}

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard
          icon={BarChart3}
          label={locale === 'zh' ? '检测记录' : 'Detections'}
          value={statsLoading ? '…' : totalDetections.toLocaleString()}
          color="emerald"
        />
        <MetricCard
          icon={ClipboardCheck}
          label={locale === 'zh' ? '待审核' : 'Pending Review'}
          value={statsLoading ? '…' : pendingReview.toLocaleString()}
          color="cyan"
          alert={pendingReview > 0}
        />
        <MetricCard
          icon={Bird}
          label={locale === 'zh' ? '物种覆盖' : 'Coverage'}
          value={coverageRatio}
          color="violet"
        />
        <MetricCard
          icon={Wifi}
          label={locale === 'zh' ? '系统状态' : 'Status'}
          value={isOnline ? (locale === 'zh' ? '在线' : 'Online') : (locale === 'zh' ? '离线' : 'Offline')}
          color={isOnline ? 'emerald' : 'red'}
        />
      </div>

      {/* System cards row */}
      <div className="grid gap-3 md:grid-cols-3">
        <SystemCard
          icon={Cpu}
          title={locale === 'zh' ? '识别引擎' : 'Detection Engine'}
          items={[
            { label: locale === 'zh' ? '模型版本' : 'Model', value: modelVer },
            { label: locale === 'zh' ? '物种数' : 'Species', value: numSpecies },
            { label: 'BirdNET', value: health?.birdnet_available ? (locale === 'zh' ? '可用' : 'Available') : (locale === 'zh' ? '未安装' : 'N/A') },
          ]}
          color="emerald"
        />
        <SystemCard
          icon={Microscope}
          title={locale === 'zh' ? '数据覆盖' : 'Data Coverage'}
          items={[
            { label: locale === 'zh' ? '模型物种' : 'Model spp.', value: health?.num_species_model || 0 },
            { label: locale === 'zh' ? '数据库物种' : 'DB spp.', value: health?.num_species_db || 0 },
            { label: locale === 'zh' ? '覆盖率' : 'Ratio', value: coverageRatio },
          ]}
          color="cyan"
        />
        <SystemCard
          icon={Layers3}
          title={locale === 'zh' ? '嵌入引擎' : 'Embedding Engine'}
          items={[
            { label: locale === 'zh' ? '记录数' : 'Records', value: health?.embedding_engine?.total_records || 0 },
            { label: locale === 'zh' ? '维度' : 'Dimensions', value: health?.embedding_engine?.embedding_dim || '--' },
            { label: locale === 'zh' ? 'OOD检测' : 'OOD', value: health?.model?.ood_detection ? 'On' : 'Off' },
          ]}
          color="violet"
        />
      </div>

      {/* Quick actions */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-white/70">
          {locale === 'zh' ? '快速导航' : 'Quick Actions'}
        </h3>
        <div className="quick-action-grid">
          {QUICK_ACTIONS.map((action) => {
            const Icon = action.icon
            const a = accent(action.color)
            const fallbackLabel = action.id.charAt(0).toUpperCase() + action.id.slice(1)
            const label = t(action.labelKey, { defaultValue: fallbackLabel })
            return (
              <button
                key={action.id}
                onClick={() => setActiveTab(action.tab || action.id)}
                className="quick-action-card group"
              >
                <div className={`rounded-lg p-2.5 ${a.bg}`}>
                  <Icon className={`h-5 w-5 ${a.text}`} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white group-hover:text-emerald-300 transition-colors">{label}</p>
                  <p className="mt-0.5 text-xs text-white/30 line-clamp-1">
                    {t(action.descKey, { defaultValue: '' })}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-white/15 group-hover:text-white/40 transition-colors shrink-0" />
              </button>
            )
          })}
        </div>
      </div>

      {/* BirdNET comparison */}
      <div className="card-padded">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">
              {locale === 'zh' ? '引擎对比' : 'Engine Comparison'}
            </h3>
            <p className="mt-1 text-xs text-white/30">
              {locale === 'zh' ? '上传音频文件对比平台 CNN 与 BirdNET 识别结果' : 'Upload audio to compare platform CNN vs BirdNET results'}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <label className="flex-1 cursor-pointer">
            <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2.5 transition hover:bg-white/[0.06]">
              <Upload className="h-4 w-4 text-white/30" />
              <span className="truncate text-sm text-white/40">{compareFile ? compareFile.name : (locale === 'zh' ? '选择音频文件…' : 'Select audio file…')}</span>
            </div>
            <input type="file" accept="audio/*" className="hidden" onChange={(e) => setCompareFile(e.target.files?.[0] || null)} />
          </label>
          <button
            onClick={handleCompare}
            disabled={!compareFile || comparing}
            className="btn-primary disabled:opacity-40"
          >
            {comparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
            {locale === 'zh' ? '对比分析' : 'Compare'}
          </button>
        </div>

        {compareResult && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <ComparePanel
              title={`CNN (${compareResult.cnn_model?.version || 'v7'})`}
              detections={compareResult.cnn_model?.detections || []}
              color="emerald"
              emptyLabel={locale === 'zh' ? '无检测结果' : 'No detections'}
            />
            <ComparePanel
              title="BirdNET"
              detections={compareResult.birdnet?.detections || []}
              color="violet"
              emptyLabel={
                compareResult.birdnet?.available
                  ? (locale === 'zh' ? '无检测结果' : 'No detections')
                  : (locale === 'zh' ? 'BirdNET 未安装' : 'BirdNET not installed')
              }
            />
            {compareResult.agreement && (
              <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/8 p-4 md:col-span-2">
                <p className="text-sm font-medium text-cyan-400">
                  {locale === 'zh' ? '一致率' : 'Agreement'}:{' '}
                  {Number.isFinite(compareResult.agreement?.agreement_ratio)
                    ? `${(compareResult.agreement.agreement_ratio * 100).toFixed(0)}%`
                    : '--'
                  }
                </p>
                <p className="mt-1 text-xs text-white/40">
                  {locale === 'zh' ? '共同物种' : 'Shared species'}:{' '}
                  {compareResult.agreement.overlap?.join(', ') || (locale === 'zh' ? '无' : 'None')}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function MetricCard({ icon: Icon, label, value, color, alert = false }) {
  const a = accent(color)
  return (
    <div className="card-padded">
      <div className="flex items-center justify-between">
        <div className={`rounded-lg p-2 ${a.bg}`}>
          <Icon className={`h-4 w-4 ${a.text}`} />
        </div>
        {alert && <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold text-white">{value}</p>
        <p className="mt-0.5 text-xs text-white/40">{label}</p>
      </div>
    </div>
  )
}

function SystemCard({ icon: Icon, title, items, color }) {
  const a = accent(color)
  return (
    <div className="card-padded">
      <div className="flex items-center gap-3 mb-4">
        <div className={`rounded-lg p-2 ${a.bg}`}>
          <Icon className={`h-4 w-4 ${a.text}`} />
        </div>
        <h4 className="text-sm font-semibold text-white">{title}</h4>
      </div>
      <div className="space-y-2.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center justify-between">
            <span className="text-xs text-white/35">{item.label}</span>
            <span className="text-xs font-medium text-white/70">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ComparePanel({ title, detections, color, emptyLabel }) {
  const a = accent(color)
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
      <p className={`text-sm font-semibold mb-3 ${a.text}`}>{title}</p>
      {detections.length === 0 ? (
        <p className="text-sm text-white/25">{emptyLabel}</p>
      ) : (
        <div className="space-y-1.5">
          {detections.slice(0, 5).map((d, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm text-white/60">{d.species_chinese || d.species_scientific}</p>
                <p className="truncate text-xs text-white/25">{d.species_scientific}</p>
              </div>
              <span className={`text-xs font-medium ${a.text}`}>
                {((d.confidence || 0) * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
