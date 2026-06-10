import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  AlertTriangle, Bird, KeyRound, RefreshCw, Server, Shield,
} from 'lucide-react'
import { getApiErrorMessage, getEBirdKeyStatus, getXCKeyStatus, setEBirdKey, setXCKey } from '../../lib/api'
import { usePlatformConfig } from '../../lib/PlatformConfigContext'
import { ProjectManagementPanel } from '../fieldops'
import { AdminGate, SpeciesImportPanel } from '../common'

export default function SettingsTab({ health, refreshHealth, healthFetchedAt }) {
  const { t, i18n } = useTranslation()
  const platformConfig = usePlatformConfig()
  const locale = i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
  const isOnline = health?.status === 'ok'
  const featureFlags = platformConfig.features || {}
  const [xcKeyStatus, setXcKeyStatus] = useState(null)
  const [ebirdKeyStatus, setEbirdKeyStatus] = useState(null)
  const [newKey, setNewKey] = useState('')
  const [newEBirdKey, setNewEBirdKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [savingEBird, setSavingEBird] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  const loadKeyStatus = async () => {
    setRefreshing(true)
    try {
      const [xcStatus, ebirdStatus] = await Promise.allSettled([getXCKeyStatus(), getEBirdKeyStatus()])
      if (xcStatus.status === 'fulfilled') setXcKeyStatus(xcStatus.value)
      if (ebirdStatus.status === 'fulfilled') setEbirdKeyStatus(ebirdStatus.value)
    } finally {
      setRefreshing(false)
    }
  }

  const handleSaveEBirdKey = async () => {
    if (!newEBirdKey.trim()) return
    setSavingEBird(true)
    setError(null)
    try {
      await setEBirdKey(newEBirdKey.trim())
      setEbirdKeyStatus({ configured: true })
      setNewEBirdKey('')
      await loadKeyStatus()
    } catch (err) {
      setError(getApiErrorMessage(err, t('settingsPage.saveEbirdKeyFailed')))
    } finally {
      setSavingEBird(false)
    }
  }

  useEffect(() => {
    loadKeyStatus().catch(() => {})
  }, [])

  const handleSaveKey = async () => {
    if (!newKey.trim()) return
    setSaving(true)
    setError(null)
    try {
      await setXCKey(newKey.trim())
      setXcKeyStatus({ configured: true })
      setNewKey('')
      await loadKeyStatus()
      await refreshHealth?.()
    } catch (err) {
      setError(getApiErrorMessage(err, t('settingsPage.saveApiKeyFailed')))
    } finally {
      setSaving(false)
    }
  }

  const warnings = (Array.isArray(health?.warnings) ? health.warnings : []).filter((w) => w.level === 'error' || w.level === 'warning')
  const coverage = health?.species_coverage || {}
  const lastSyncLabel = healthFetchedAt
    ? new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(healthFetchedAt))
    : '--:--:--'

  const systemInfo = [
    [t('settingsPage.sysPlatformVersion'), 'V7.0'],
    [t('settingsPage.sysRuntimeState'), health?.runtime_state || '--'],
    [t('settingsPage.sysModelArchitecture'), health?.model?.architecture || '--'],
    [t('settingsPage.sysInferenceDevice'), health?.device || '--'],
    [t('settingsPage.sysModelSpeciesCount'), health?.num_species_model || 0],
    [t('settingsPage.sysDatabaseSpeciesCount'), health?.num_species_db || 0],
    [t('settingsPage.sysBirdnetBaseline'), health?.birdnet_available ? t('settingsPage.valueAvailable') : t('settingsPage.valueNotInstalled')],
    [t('settingsPage.sysOodDetection'), health?.model?.ood_detection ? t('settingsPage.valueEnabled') : t('settingsPage.valueDisabled')],
    [t('settingsPage.sysDualChannelMel'), health?.model?.dual_channel_mel ? t('settingsPage.valueEnabled') : t('settingsPage.valueDisabled')],
  ]

  const features = [
    {
      id: 'species',
      name: t('settingsPage.featureSpeciesName'),
      enabled: true,
      desc: t('settingsPage.featureSpeciesDesc'),
    },
    {
      id: 'birdnet',
      name: t('settingsPage.featureBirdnetName'),
      enabled: Boolean(health?.birdnet_available) && featureFlags.birdnet_comparison !== false,
      desc: t('settingsPage.featureBirdnetDesc'),
    },
    {
      id: 'ood',
      name: t('settingsPage.featureOodName'),
      enabled: Boolean(health?.model?.ood_detection),
      desc: t('settingsPage.featureOodDesc'),
    },
    {
      id: 'device',
      name: t('settingsPage.featureDeviceName'),
      enabled: true,
      desc: t('settingsPage.featureDeviceDesc'),
    },
    {
      id: 'realtime',
      name: t('settingsPage.featureRealtimeName'),
      enabled: featureFlags.realtime_streaming !== false,
      desc: t('settingsPage.featureRealtimeDesc'),
    },
    {
      id: 'diversity',
      name: t('settingsPage.featureDiversityName'),
      enabled: true,
      desc: t('settingsPage.featureDiversityDesc'),
    },
    {
      id: 'report',
      name: t('settingsPage.featureReportName'),
      enabled: featureFlags.html_report !== false,
      desc: t('settingsPage.featureReportDesc'),
    },
    {
      id: 'darwin_core',
      name: t('settingsPage.featureDarwinCoreName', 'Darwin Core Export'),
      enabled: featureFlags.darwin_core_export === true,
      desc: t('settingsPage.featureDarwinCoreDesc', 'Export detection data in Darwin Core standard format'),
    },
    {
      id: 'user_accounts',
      name: t('settingsPage.featureUserAccountsName', 'User Accounts'),
      enabled: featureFlags.user_accounts === true,
      desc: t('settingsPage.featureUserAccountsDesc', 'Multi-user login and role-based access control'),
    },
  ]

  return (
    <div className="space-y-6">
      <section className="card-padded space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="section-kicker">
              <Server className="h-3 w-3" />
              {t('settingsPage.runtimeBadge')}
            </div>
            <h2 className="section-title">{t('settingsPage.heroTitle')}</h2>
            <p className="section-copy">{t('settingsPage.heroBody')}</p>
          </div>
          <button
            onClick={async () => {
              await Promise.allSettled([loadKeyStatus(), refreshHealth?.()])
            }}
            className="btn-secondary btn-sm shrink-0"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {t('settingsPage.refreshRuntime')}
          </button>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          <span className="badge badge-neutral">{t('settingsPage.lastSync', { time: lastSyncLabel })}</span>
          <span className="badge badge-neutral">{t('settingsPage.coverage', { model: coverage.model_species || 0, db: coverage.database_species || 0 })}</span>
        </div>
      </section>

      {warnings.length > 0 && (
        <section className="glass-card space-y-3 p-5">
          <div className="mb-1 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-[#FF9F0A]" />
            <h3 className="text-sm font-semibold text-white">{t('settingsPage.runtimeWarnings')}</h3>
          </div>
          {warnings.map((warning) => {
            const wCode = warning.code || ''
            const titleKey = `appShell.warningTitle_${wCode}`
            const detailKey = `appShell.warningDetail_${wCode}`
            const hasKey = t(titleKey) !== titleKey
            const detailParams = wCode === 'SPECIES_COVERAGE_GAP'
              ? { model: health?.num_species_model || 0, db: health?.num_species_db || 0, missing: Math.max(0, (health?.num_species_db || 0) - (health?.num_species_model || 0)) }
              : {}
            return (
              <div key={warning.code} className={`rounded-2xl border p-3 text-sm ${
                warning.level === 'error'
                  ? 'border-white/[0.06] bg-[#FF453A]/10 text-[#FF453A]'
                  : warning.level === 'warning'
                    ? 'border-white/[0.06] bg-[#FF9F0A]/10 text-[#FF9F0A]'
                    : 'border-white/[0.06] bg-[#0A84FF]/10 text-[#0A84FF]'
              }`}>
                <p className="font-medium">{hasKey ? t(titleKey) : warning.title}</p>
                <p className="mt-1 text-xs leading-5 opacity-90">{hasKey ? t(detailKey, detailParams) : warning.detail}</p>
              </div>
            )
          })}
        </section>
      )}

      <section className="glass-card p-4 md:p-5">
        <div className="mb-3 flex items-center gap-2 md:mb-4">
          <Server className="h-3.5 w-3.5 text-[#0A84FF] md:h-4 md:w-4" />
          <h3 className="text-xs font-semibold text-white md:text-sm">{t('settingsPage.systemInformation')}</h3>
        </div>
        <div className="grid gap-2 md:grid-cols-2 md:gap-3">
          {systemInfo.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between rounded-2xl bg-white/[0.03] p-2.5 text-xs md:p-3 md:text-sm">
              <span className="text-white/40">{label}</span>
              <span className="text-white">{value}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="glass-card p-4 md:p-5">
        <div className="mb-3 flex items-center gap-2 md:mb-4">
          <KeyRound className="h-3.5 w-3.5 text-[#BF5AF2] md:h-4 md:w-4" />
          <h3 className="text-xs font-semibold text-white md:text-sm">{t('settingsPage.xcTitle')}</h3>
        </div>
        <div className="mb-2.5 flex items-center gap-2 text-[11px] text-white/40 md:mb-3 md:text-xs">
          <span className={`h-2 w-2 rounded-full ${xcKeyStatus?.configured ? 'bg-[#30D158]' : 'bg-[#FF453A]'}`} />
          {xcKeyStatus?.configured ? t('settingsPage.xcKeyConfigured') : t('settingsPage.xcKeyNotConfigured')}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={newKey}
            onChange={(event) => setNewKey(event.target.value)}
            type="password"
            placeholder={t('settingsPage.xcKeyPlaceholder')}
            className="touch-button flex-1 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
          />
          <button
            onClick={handleSaveKey}
            disabled={saving || !newKey.trim()}
            className="touch-button rounded-[12px] border border-white/[0.06] bg-[#0A84FF]/15 px-4 py-2 text-sm text-[#0A84FF] active:scale-[0.97] disabled:opacity-50"
          >
            {saving ? t('settingsPage.saving') : t('settingsPage.saveKey')}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-white/25 md:text-xs">
          {t('settingsPage.xcKeyObtainPrefix')}
          <a href="https://xeno-canto.org/account" target="_blank" rel="noopener noreferrer" className="text-[#0A84FF] hover:underline">xeno-canto.org/account</a>
          {t('settingsPage.xcKeyObtainSuffix')}
        </p>
        {error && <p className="mt-2 text-xs text-[#FF453A]">{error}</p>}
      </section>

      <section className="glass-card p-4 md:p-5">
        <div className="mb-3 flex items-center gap-2 md:mb-4">
          <Bird className="h-3.5 w-3.5 text-[#30D158] md:h-4 md:w-4" />
          <h3 className="text-xs font-semibold text-white md:text-sm">{t('settingsPage.ebirdTitle')}</h3>
        </div>
        <div className="mb-2.5 flex items-center gap-2 text-[11px] text-white/40 md:mb-3 md:text-xs">
          <span className={`h-2 w-2 rounded-full ${ebirdKeyStatus?.configured ? 'bg-[#30D158]' : 'bg-[#FF453A]'}`} />
          {ebirdKeyStatus?.configured ? t('settingsPage.ebirdKeyConfigured') : t('settingsPage.ebirdKeyNotConfigured')}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={newEBirdKey}
            onChange={(event) => setNewEBirdKey(event.target.value)}
            type="password"
            placeholder={t('settingsPage.ebirdKeyPlaceholder')}
            className="touch-button flex-1 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
          />
          <button
            onClick={handleSaveEBirdKey}
            disabled={savingEBird || !newEBirdKey.trim()}
            className="touch-button rounded-[12px] border border-white/[0.06] bg-[#0A84FF]/15 px-4 py-2 text-sm text-[#0A84FF] active:scale-[0.97] disabled:opacity-50"
          >
            {savingEBird ? t('settingsPage.saving') : t('settingsPage.saveKey')}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-white/25 md:text-xs">
          {t('settingsPage.ebirdKeyObtainPrefix')}
          <a href="https://ebird.org/api/keygen" target="_blank" rel="noopener noreferrer" className="text-[#0A84FF] hover:underline">ebird.org/api/keygen</a>
          {t('settingsPage.ebirdKeyObtainSuffix')}
        </p>
      </section>

      <section className="glass-card p-4 md:p-5">
        <div className="mb-3 flex items-center gap-2 md:mb-4">
          <Shield className="h-3.5 w-3.5 text-[#30D158] md:h-4 md:w-4" />
          <h3 className="text-xs font-semibold text-white md:text-sm">{t('settingsPage.featureAvailability')}</h3>
        </div>
        <div className="space-y-1.5 md:space-y-2">
          {features.map((feature) => (
            <div key={feature.id} className="flex items-center justify-between gap-3 rounded-2xl bg-white/[0.03] p-2.5 md:p-3">
              <div className="min-w-0">
                <p className="text-xs font-medium text-white md:text-sm">{feature.name}</p>
                <p className="truncate text-[11px] text-white/25 md:text-xs">{feature.desc}</p>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] md:px-2.5 md:py-1 md:text-xs ${
                feature.enabled
                  ? 'bg-[#30D158]/15 text-[#30D158]'
                  : 'bg-white/[0.06] text-white/30'
              }`}>
                {feature.enabled ? t('settingsPage.valueEnabled') : t('settingsPage.valueDisabled')}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ── 物种数据导入 ── */}
      <SpeciesImportPanel
        locale={locale}
        onImportComplete={refreshHealth}
      />

      {/* ── 后台管理：项目/站点/路线（PIN 守门，避免 APK 被拿到野外后误删数据）── */}
      <AdminGate locale={locale}>
        <ProjectManagementPanel
          locale={locale}
          isOnline={isOnline}
          onDataChanged={refreshHealth}
        />
      </AdminGate>
    </div>
  )
}
