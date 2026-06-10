import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  AlertTriangle, Bird, KeyRound, RefreshCw, Server, Shield,
} from 'lucide-react'
import { getApiErrorMessage, getEBirdKeyStatus, getXCKeyStatus, setEBirdKey, setXCKey } from '../../lib/api'
import { usePlatformConfig } from '../../lib/PlatformConfigContext'
import { StatusBanner } from '../common'

export default function SettingsTab({ health, refreshHealth, healthFetchedAt }) {
  const { t } = useTranslation()
  const platformConfig = usePlatformConfig()
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

  const warnings = Array.isArray(health?.warnings) ? health.warnings : []
  const coverage = health?.species_coverage || {}
  const lastSyncLabel = healthFetchedAt
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(healthFetchedAt))
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
    { id: 'species', name: t('settingsPage.featureSpeciesName'), enabled: true, desc: t('settingsPage.featureSpeciesDesc') },
    { id: 'birdnet', name: t('settingsPage.featureBirdnetName'), enabled: Boolean(health?.birdnet_available) && featureFlags.birdnet_comparison !== false, desc: t('settingsPage.featureBirdnetDesc') },
    { id: 'ood', name: t('settingsPage.featureOodName'), enabled: Boolean(health?.model?.ood_detection), desc: t('settingsPage.featureOodDesc') },
    { id: 'soundscape', name: 'Soundscape Analysis', enabled: featureFlags.soundscape_analysis !== false, desc: 'Ecoacoustic indices and ecosystem health scoring' },
    { id: 'device', name: t('settingsPage.featureDeviceName'), enabled: true, desc: t('settingsPage.featureDeviceDesc') },
    { id: 'realtime', name: t('settingsPage.featureRealtimeName'), enabled: featureFlags.realtime_streaming !== false, desc: t('settingsPage.featureRealtimeDesc') },
    { id: 'diversity', name: t('settingsPage.featureDiversityName'), enabled: true, desc: t('settingsPage.featureDiversityDesc') },
    { id: 'darwin_core', name: t('settingsPage.featureDarwinCoreName', 'Darwin Core Export'), enabled: featureFlags.darwin_core_export === true, desc: t('settingsPage.featureDarwinCoreDesc', 'Export detection data in Darwin Core standard format') },
  ]

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="card-elevated p-5 md:p-6">
        <div className="max-w-3xl">
          <div className="section-kicker">
            <Server className="h-3.5 w-3.5" />
            {t('settingsPage.runtimeBadge')}
          </div>
          <h2 className="mt-3 text-xl font-bold md:text-2xl" style={{ color: 'var(--text-primary)' }}>{t('settingsPage.heroTitle')}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
            {t('settingsPage.heroBody')}
          </p>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <SettingsNote title={t('settingsPage.noteLightweightTitle')} body={t('settingsPage.noteLightweightBody')} />
          <SettingsNote title={t('settingsPage.noteExternalTitle')} body={t('settingsPage.noteExternalBody')} />
          <SettingsNote title={t('settingsPage.noteScientificTitle')} body={t('settingsPage.noteScientificBody')} />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <span className="metric-chip">{t('settingsPage.lastSync', { time: lastSyncLabel })}</span>
          <span className="metric-chip">
            {t('settingsPage.coverage', { model: coverage.model_species || 0, db: coverage.database_species || 0 })}
          </span>
          <button
            onClick={async () => {
              await Promise.allSettled([loadKeyStatus(), refreshHealth?.()])
            }}
            className="btn-ghost text-xs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {t('settingsPage.refreshRuntime')}
          </button>
        </div>
      </section>

      {error && <StatusBanner tone="error" message={error} />}

      {warnings.length > 0 && (
        <section className="card p-5">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" style={{ color: '#D97706' }} />
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('settingsPage.runtimeWarnings')}</h3>
          </div>
          {warnings.map((warning) => (
            <div key={warning.code} className="mb-2 rounded-lg border p-3 text-sm" style={{
              borderColor: warning.level === 'error' ? 'rgba(179,27,27,0.2)' : 'rgba(245,158,11,0.2)',
              background: warning.level === 'error' ? 'rgba(179,27,27,0.04)' : '#FFFBEB',
              color: warning.level === 'error' ? 'var(--cornell-carnelian)' : '#92400E',
            }}>
              <p className="font-medium">{warning.title}</p>
              <p className="mt-1 text-xs leading-5 opacity-80">{warning.detail}</p>
            </div>
          ))}
        </section>
      )}

      {/* System Information */}
      <section className="card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Server className="h-4 w-4" style={{ color: 'var(--cornell-blue)' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('settingsPage.systemInformation')}</h3>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {systemInfo.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between rounded-lg border p-3 text-sm" style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface-secondary)' }}>
              <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
              <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{value}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Xeno-canto API Key */}
      <section className="card p-5">
        <div className="mb-4 flex items-center gap-2">
          <KeyRound className="h-4 w-4" style={{ color: 'var(--cornell-teal)' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('settingsPage.xcTitle')}</h3>
        </div>
        <div className="mb-3 flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <span className={`status-dot ${xcKeyStatus?.configured ? 'status-dot-online' : 'status-dot-error'}`} />
          {xcKeyStatus?.configured ? t('settingsPage.xcKeyConfigured') : t('settingsPage.xcKeyNotConfigured')}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={newKey}
            onChange={(event) => setNewKey(event.target.value)}
            type="password"
            placeholder={t('settingsPage.xcKeyPlaceholder')}
            className="input-field flex-1"
          />
          <button onClick={handleSaveKey} disabled={saving || !newKey.trim()} className="btn-primary disabled:opacity-50">
            {saving ? t('settingsPage.saving') : t('settingsPage.saveKey')}
          </button>
        </div>
        <p className="mt-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {t('settingsPage.xcKeyObtainPrefix')}
          <a href="https://xeno-canto.org/account" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--cornell-blue)' }} className="hover:underline">xeno-canto.org/account</a>
          {t('settingsPage.xcKeyObtainSuffix')}
        </p>
      </section>

      {/* eBird API Key */}
      <section className="card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Bird className="h-4 w-4" style={{ color: 'var(--cornell-forest)' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('settingsPage.ebirdTitle')}</h3>
        </div>
        <div className="mb-3 flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <span className={`status-dot ${ebirdKeyStatus?.configured ? 'status-dot-online' : 'status-dot-error'}`} />
          {ebirdKeyStatus?.configured ? t('settingsPage.ebirdKeyConfigured') : t('settingsPage.ebirdKeyNotConfigured')}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={newEBirdKey}
            onChange={(event) => setNewEBirdKey(event.target.value)}
            type="password"
            placeholder={t('settingsPage.ebirdKeyPlaceholder')}
            className="input-field flex-1"
          />
          <button onClick={handleSaveEBirdKey} disabled={savingEBird || !newEBirdKey.trim()} className="btn-primary disabled:opacity-50">
            {savingEBird ? t('settingsPage.saving') : t('settingsPage.saveKey')}
          </button>
        </div>
        <p className="mt-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {t('settingsPage.ebirdKeyObtainPrefix')}
          <a href="https://ebird.org/api/keygen" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--cornell-blue)' }} className="hover:underline">ebird.org/api/keygen</a>
          {t('settingsPage.ebirdKeyObtainSuffix')}
        </p>
      </section>

      {/* Feature Availability */}
      <section className="card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Shield className="h-4 w-4" style={{ color: 'var(--cornell-forest)' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('settingsPage.featureAvailability')}</h3>
        </div>
        <div className="space-y-2">
          {features.map((feature) => (
            <div key={feature.id} className="flex items-center justify-between gap-3 rounded-lg border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface-secondary)' }}>
              <div className="min-w-0">
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{feature.name}</p>
                <p className="truncate text-xs" style={{ color: 'var(--text-tertiary)' }}>{feature.desc}</p>
              </div>
              <span className="shrink-0 rounded-full px-2.5 py-1 text-xs font-medium" style={
                feature.enabled
                  ? { background: 'rgba(45,106,79,0.08)', color: 'var(--cornell-forest)' }
                  : { background: 'var(--surface-secondary)', color: 'var(--text-tertiary)' }
              }>
                {feature.enabled ? t('settingsPage.valueEnabled') : t('settingsPage.valueDisabled')}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function SettingsNote({ title, body }) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border-default)', background: 'var(--surface-secondary)' }}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] md:text-xs" style={{ color: 'var(--text-tertiary)' }}>{title}</p>
      <p className="mt-1.5 text-xs leading-5 md:mt-2 md:text-sm md:leading-6" style={{ color: 'var(--text-primary)' }}>{body}</p>
    </div>
  )
}
