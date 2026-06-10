import React, {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import 'leaflet/dist/leaflet.css'
import {
  AlertTriangle,
  Globe2,
  Loader2,
  Menu,
  RefreshCw,
  WifiOff,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getHealthStatus } from './lib/api'
import { usePlatformConfig } from './lib/PlatformConfigContext'
import {
  APP_COPY,
  DEFAULT_TAB_ID,
  MOBILE_MORE_TAB_IDS,
  MOBILE_PRIMARY_TAB_IDS,
  NAV_GROUPS,
  TABS,
  TAB_SUMMARIES,
} from './constants'

const DashboardTab = lazy(() => import('./components/tabs/DashboardTab'))
const AnalyzeTab = lazy(() => import('./components/tabs/AnalyzeTab'))
const DevicesTab = lazy(() => import('./components/tabs/DevicesTab'))
const MonitorTab = lazy(() => import('./components/tabs/MonitorTab'))
const VerifyTab = lazy(() => import('./components/tabs/VerifyTab'))
const EmbeddingsTab = lazy(() => import('./components/tabs/EmbeddingsTab'))
const PhenologyTab = lazy(() => import('./components/tabs/PhenologyTab'))
const OccupancyTab = lazy(() => import('./components/tabs/OccupancyTab'))
const FewShotTab = lazy(() => import('./components/tabs/FewShotTab'))
const SoundscapeTab = lazy(() => import('./components/tabs/SoundscapeTab'))
const SettingsTab = lazy(() => import('./components/tabs/SettingsTab'))
const AboutTab = lazy(() => import('./components/tabs/AboutTab'))

const TAB_COMPONENTS = {
  dashboard: DashboardTab,
  analyze: AnalyzeTab,
  devices: DevicesTab,
  monitor: MonitorTab,
  verify: VerifyTab,
  embeddings: EmbeddingsTab,
  phenology: PhenologyTab,
  occupancy: OccupancyTab,
  fewshot: FewShotTab,
  soundscape: SoundscapeTab,
  settings: SettingsTab,
  about: AboutTab,
}

function TabFallback() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="mr-3 h-6 w-6 animate-spin" style={{ color: 'var(--cornell-carnelian)' }} />
      <span style={{ color: 'var(--text-tertiary)' }}>Loading module…</span>
    </div>
  )
}

function buildFallbackHealth(t) {
  return {
    status: 'error',
    runtime_state: 'error',
    model_loaded: false,
    num_species_model: 0,
    num_species_db: 0,
    warnings: [
      {
        code: 'BACKEND_UNAVAILABLE',
        level: 'error',
        title: t('appShell.backendUnavailableTitle'),
        detail: t('appShell.backendUnavailableDetail'),
      },
    ],
  }
}

function formatSyncTime(timestamp) {
  if (!timestamp) return '--:--:--'
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

export default function App() {
  const [activeTab, setActiveTab] = useState(DEFAULT_TAB_ID)
  const [health, setHealth] = useState(null)
  const [isMobile, setIsMobile] = useState(false)
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' ? !navigator.onLine : false)
  const [isMoreOpen, setIsMoreOpen] = useState(false)
  const [healthFetchedAt, setHealthFetchedAt] = useState(null)
  const { i18n, t } = useTranslation()
  const platformConfig = usePlatformConfig()
  const locale = i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
  const appCopy = {
    ...APP_COPY[locale],
    ...(platformConfig.platform ? {
      appName: locale === 'zh' ? (platformConfig.platform.name_zh || APP_COPY.zh.appName) : (platformConfig.platform.name || APP_COPY.en.appName),
      appNameMobile: locale === 'zh' ? (platformConfig.platform.short_name_zh || APP_COPY.zh.appNameMobile) : (platformConfig.platform.short_name || APP_COPY.en.appNameMobile),
      appSubtitle: locale === 'zh' ? (platformConfig.platform.subtitle_zh || APP_COPY.zh.appSubtitle) : (platformConfig.platform.subtitle || APP_COPY.en.appSubtitle),
    } : {}),
  }
  const tabs = useMemo(
    () => TABS.map((tab) => ({ ...tab, label: t(tab.labelKey) })),
    [t],
  )
  const groupedTabs = useMemo(
    () => NAV_GROUPS.map((group) => ({
      ...group,
      label: group.label[locale],
      tabs: group.tabs.map((id) => tabs.find((tab) => tab.id === id)).filter(Boolean),
    })),
    [locale, tabs],
  )
  const mobilePrimaryTabs = useMemo(
    () => tabs.filter((tab) => MOBILE_PRIMARY_TAB_IDS.includes(tab.id)),
    [tabs],
  )
  const mobileMoreTabs = useMemo(
    () => tabs.filter((tab) => MOBILE_MORE_TAB_IDS.includes(tab.id)),
    [tabs],
  )
  const activeTabMeta = tabs.find((tab) => tab.id === activeTab) || tabs[0]
  const activeSummary = TAB_SUMMARIES[locale]?.[activeTab] || TAB_SUMMARIES.en[activeTab] || ''

  const refreshHealth = useCallback(async () => {
    try {
      const nextHealth = await getHealthStatus()
      setHealth(nextHealth)
      setHealthFetchedAt(Date.now())
    } catch {
      setHealth(buildFallbackHealth(t))
      setHealthFetchedAt(Date.now())
    }
  }, [t])

  const toggleLang = () => {
    const next = i18n.language === 'zh' ? 'en' : 'zh'
    i18n.changeLanguage(next)
    localStorage.setItem('acoustic_platform_lang', next)
  }

  useEffect(() => { refreshHealth() }, [refreshHealth])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') refreshHealth()
    }, 30000)
    return () => window.clearInterval(intervalId)
  }, [refreshHealth])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const mediaQuery = window.matchMedia('(max-width: 767px)')
    const updateViewport = (event) => setIsMobile(event.matches)
    setIsMobile(mediaQuery.matches)
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updateViewport)
      return () => mediaQuery.removeEventListener('change', updateViewport)
    }
    mediaQuery.addListener(updateViewport)
    return () => mediaQuery.removeListener(updateViewport)
  }, [])

  useEffect(() => {
    const handleOnline = () => { setIsOffline(false); refreshHealth() }
    const handleOffline = () => setIsOffline(true)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [refreshHealth])

  useEffect(() => {
    if (!isMobile) setIsMoreOpen(false)
  }, [isMobile])

  const isOnline = health?.status === 'ok'
  const ActiveComponent = TAB_COMPONENTS[activeTab]
  let tabProps = {}
  if (activeTab === 'dashboard') {
    tabProps = { health, setActiveTab, refreshHealth, healthFetchedAt }
  } else if (activeTab === 'settings' || activeTab === 'about') {
    tabProps = { health, refreshHealth, healthFetchedAt }
  }

  const currentModel = health?.model?.version?.toUpperCase() || 'CNN'
  const currentSpecies = health?.num_species_model || health?.num_species || 0
  const mobileShowsMoreActive = isMoreOpen || !MOBILE_PRIMARY_TAB_IDS.includes(activeTab)
  const healthWarnings = Array.isArray(health?.warnings) ? health.warnings : []
  const primaryWarning = healthWarnings.find((item) => item.level === 'error')
    || healthWarnings.find((item) => item.level === 'warning')
    || null
  const runtimeState = health?.runtime_state || (isOnline ? 'ready' : 'error')
  const lastSyncLabel = formatSyncTime(healthFetchedAt)

  return (
    <div className="min-h-screen" style={{ background: 'var(--surface-secondary)' }}>
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-white" style={{ borderColor: 'var(--border-default)' }}>
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2.5 md:py-3">
          {/* Brand */}
          <div className="flex min-w-0 flex-1 items-center gap-3 pr-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg md:h-10 md:w-10" style={{ background: 'var(--cornell-carnelian)' }}>
              <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V7a2 2 0 0 1 4 0v4a2 2 0 0 0 2 2" />
              </svg>
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold md:text-base" style={{ color: 'var(--text-primary)' }}>
                {isMobile ? appCopy.appNameMobile : appCopy.appName}
              </h1>
              <p className="hidden text-xs md:block" style={{ color: 'var(--text-tertiary)' }}>
                {appCopy.appSubtitle}
              </p>
              {isMobile && (
                <div className="flex items-center gap-1.5">
                  <span className={`status-dot ${isOnline ? 'status-dot-online' : health === null ? 'animate-pulse bg-gray-300' : 'status-dot-error'}`} style={{ width: 6, height: 6 }} />
                  <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{activeTabMeta.label}</p>
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex shrink-0 items-center gap-1.5 md:gap-2">
            <button
              onClick={toggleLang}
              className="btn-ghost p-2"
              title={i18n.language === 'zh' ? t('appShell.switchToEnglish') : t('appShell.switchToChinese')}
              aria-label={i18n.language === 'zh' ? t('appShell.switchToEnglish') : t('appShell.switchToChinese')}
            >
              <Globe2 className="h-4 w-4" />
              <span className="hidden text-xs md:inline">{i18n.language === 'zh' ? 'EN' : '中文'}</span>
            </button>
            {!isMobile && (
              <button onClick={refreshHealth} className="btn-ghost p-2" title={t('appShell.refreshRuntime')}>
                <RefreshCw className="h-4 w-4" />
              </button>
            )}
            {/* Runtime status */}
            <div className="hidden items-center gap-2 rounded-lg border px-3 py-1.5 md:flex" style={{ borderColor: 'var(--border-default)' }}>
              {isOnline ? (
                <>
                  <span className={`status-dot pulse-dot ${runtimeState === 'warning' ? 'status-dot-warning' : 'status-dot-online'}`} />
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {currentModel} · {currentSpecies} {t('appShell.speciesCount', { count: currentSpecies }).trim()}
                  </span>
                </>
              ) : health === null ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" style={{ color: 'var(--text-tertiary)' }} />
                  <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{t('appShell.connecting')}</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3" style={{ color: 'var(--cornell-carnelian)' }} />
                  <span className="text-xs" style={{ color: 'var(--cornell-carnelian)' }}>{t('appShell.backendOffline')}</span>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Offline Banner */}
      {isOffline && (
        <div className="border-b px-4 py-2 text-center text-xs" style={{ borderColor: '#FDE68A', background: '#FFFBEB', color: '#92400E' }}>
          {t('appShell.offlineBanner')}
        </div>
      )}

      {/* Warning Banner */}
      {primaryWarning && isOnline && (
        <div className="border-b px-4 py-2 text-sm" style={{
          borderColor: primaryWarning.level === 'error' ? 'rgba(179,27,27,0.2)' : '#FDE68A',
          background: primaryWarning.level === 'error' ? 'rgba(179,27,27,0.04)' : '#FFFBEB',
          color: primaryWarning.level === 'error' ? 'var(--cornell-carnelian)' : '#92400E',
        }}>
          <div className="mx-auto flex max-w-7xl items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="font-medium">{primaryWarning.title}:</span>
            <span className="text-xs md:text-sm">{primaryWarning.detail}</span>
          </div>
        </div>
      )}

      {/* Desktop Navigation */}
      {!isMobile && (
        <nav className="border-b bg-white" style={{ borderColor: 'var(--border-default)' }}>
          <div className="mx-auto max-w-7xl px-4">
            <div className="flex items-center gap-1 overflow-x-auto py-1">
              {groupedTabs.map((group, gi) => (
                <React.Fragment key={group.id}>
                  {gi > 0 && (
                    <div className="mx-1.5 h-5 w-px" style={{ background: 'var(--border-default)' }} />
                  )}
                  {group.tabs.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`nav-item text-xs ${activeTab === tab.id ? 'nav-item-active' : ''}`}
                      aria-current={activeTab === tab.id ? 'page' : undefined}
                    >
                      <tab.icon className="h-3.5 w-3.5" aria-hidden="true" />
                      {tab.label}
                    </button>
                  ))}
                </React.Fragment>
              ))}
            </div>
          </div>
        </nav>
      )}

      {/* Mobile More Sheet */}
      {isMobile && isMoreOpen && (
        <MobileMoreSheet
          activeTab={activeTab}
          groups={groupedTabs}
          isOnline={isOnline}
          modelLabel={currentModel}
          speciesCount={currentSpecies}
          onClose={() => setIsMoreOpen(false)}
          onSelectTab={(tabId) => {
            setActiveTab(tabId)
            setIsMoreOpen(false)
          }}
          t={t}
        />
      )}

      {/* Main Content */}
      <main className={`mx-auto max-w-7xl px-4 py-5 md:py-6 ${isMobile ? 'mobile-main' : ''}`}>
        {/* Breadcrumb with tab description */}
        {!isMobile && activeSummary && (
          <p className="mb-4 text-xs" style={{ color: 'var(--text-tertiary)' }}>{activeSummary}</p>
        )}
        <Suspense fallback={<TabFallback />}>
          {ActiveComponent && <ActiveComponent {...tabProps} />}
        </Suspense>
      </main>

      {/* Mobile Bottom Nav */}
      {isMobile && (
        <MobileBottomNav
          activeTab={activeTab}
          moreActive={mobileShowsMoreActive}
          tabs={mobilePrimaryTabs}
          onSelectTab={(tabId) => {
            setActiveTab(tabId)
            setIsMoreOpen(false)
          }}
          onOpenMore={() => setIsMoreOpen((current) => !current)}
          t={t}
        />
      )}

      {/* Footer */}
      <footer className={`border-t py-6 text-center text-xs ${isMobile ? 'mb-2' : 'mt-12'}`} style={{ borderColor: 'var(--border-default)', color: 'var(--text-tertiary)' }}>
        <p>{t('appShell.footerLine1')}</p>
        <p className="mt-1">{t('appShell.footerLine2')}</p>
        <p className="mt-1">{t('appShell.footerRuntime', { status: isOnline ? 'Ready' : 'Offline', time: lastSyncLabel })}</p>
      </footer>
    </div>
  )
}

function MobileBottomNav({ activeTab, moreActive, tabs, onSelectTab, onOpenMore, t }) {
  return (
    <nav className="mobile-bottom-nav md:hidden">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onSelectTab(tab.id)}
          className={`mobile-nav-button ${activeTab === tab.id ? 'mobile-nav-button-active' : ''}`}
          aria-current={activeTab === tab.id ? 'page' : undefined}
        >
          <tab.icon className="h-5 w-5" aria-hidden="true" />
          <span>{tab.label}</span>
          <span className="mobile-nav-dot" />
        </button>
      ))}
      <button
        onClick={onOpenMore}
        className={`mobile-nav-button ${moreActive ? 'mobile-nav-button-active' : ''}`}
      >
        <Menu className="h-5 w-5" />
        <span>{t('appShell.more')}</span>
        <span className="mobile-nav-dot" />
      </button>
    </nav>
  )
}

function MobileMoreSheet({ activeTab, groups, isOnline, modelLabel, speciesCount, onClose, onSelectTab, t }) {
  return (
    <div className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm md:hidden" onClick={onClose}>
      <div
        className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto overscroll-contain rounded-t-2xl border-t bg-white px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-3"
        style={{ borderColor: 'var(--border-default)' }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full" style={{ background: 'var(--border-default)' }} />

        {/* Status bar */}
        <div className="flex items-center justify-between rounded-xl border p-3" style={{ borderColor: 'var(--border-default)' }}>
          <div className="flex items-center gap-2">
            <span className={`status-dot ${isOnline ? 'status-dot-online' : 'status-dot-error'}`} />
            <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
              {isOnline ? `${modelLabel} · Ready` : t('appShell.backendOffline')}
            </span>
          </div>
          <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{speciesCount} species</span>
        </div>

        {/* Tab groups */}
        <div className="mt-3 space-y-4">
          {groups.map((group) => (
            <div key={group.id}>
              <p className="nav-group-label mb-2">{group.label}</p>
              <div className="space-y-1.5">
                {group.tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => onSelectTab(tab.id)}
                    className={`mobile-quick-action w-full ${
                      activeTab === tab.id ? 'border-l-2' : ''
                    }`}
                    style={activeTab === tab.id ? {
                      borderLeftColor: 'var(--cornell-carnelian)',
                      background: 'rgba(179, 27, 27, 0.03)',
                    } : {}}
                  >
                    <tab.icon className="h-5 w-5 shrink-0" style={{ color: activeTab === tab.id ? 'var(--cornell-carnelian)' : 'var(--text-tertiary)' }} />
                    <span className="text-sm font-medium" style={{ color: activeTab === tab.id ? 'var(--cornell-carnelian)' : 'var(--text-primary)' }}>
                      {tab.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
