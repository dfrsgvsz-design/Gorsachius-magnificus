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
  Bird,
  ChevronLeft,
  ChevronRight,
  Download,
  Globe2,
  Loader2,
  Menu,
  RefreshCw,
  WifiOff,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getHealthStatus, IS_HYBRID_LOCAL_MODE } from './lib/api'
import { usePlatformConfig } from './lib/PlatformConfigContext'
import {
  APP_COPY,
  DEFAULT_SURVEY_MODULE_ID,
  DEFAULT_TAB_ID,
  MOBILE_MORE_TAB_IDS,
  MOBILE_PRIMARY_TAB_IDS,
  NAV_GROUPS,
  SURVEY_MODULES,
  TABS,
  TAB_SUMMARIES,
} from './constants'

const DashboardTab = lazy(() => import('./components/tabs/DashboardTab'))
const SpeciesTab = lazy(() => import('./components/tabs/SpeciesTab'))
const DevicesTab = lazy(() => import('./components/tabs/DevicesTab'))
const FieldOpsTab = lazy(() => import('./components/tabs/FieldOpsTab'))
const MonitorTab = lazy(() => import('./components/tabs/MonitorTab'))
const VerifyTab = lazy(() => import('./components/tabs/VerifyTab'))
const SDMTab = lazy(() => import('./components/tabs/SDMTab'))
const SettingsTab = lazy(() => import('./components/tabs/SettingsTab'))
const AboutTab = lazy(() => import('./components/tabs/AboutTab'))

const TAB_COMPONENTS = {
  dashboard: DashboardTab,
  species: SpeciesTab,
  devices: DevicesTab,
  fieldops: FieldOpsTab,
  monitor: MonitorTab,
  verify: VerifyTab,
  sdm: SDMTab,
  settings: SettingsTab,
  about: AboutTab,
}

function TabFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <Loader2 className="mr-3 h-5 w-5 animate-spin text-emerald-400" />
      <span className="text-sm text-white/40">Loading…</span>
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

// Hybrid-local mode: native APK ships without VITE_API_BASE_URL on purpose.
// All CRUD lives in the on-device SQLite, so a backend health probe makes no
// sense. Return a synthetic health object that satisfies status='ok' but
// carries a `hybrid_local` flag so the status indicator can render "Local
// mode" instead of "Backend offline".
function buildHybridLocalHealth() {
  return {
    status: 'ok',
    runtime_state: 'hybrid_local',
    model_loaded: false,
    num_species_model: 0,
    num_species_db: 0,
    warnings: [],
    hybrid_local: true,
  }
}

function formatSyncTime(ts) {
  if (!ts) return '--:--'
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(ts))
}

export default function App() {
  const [activeTab, setActiveTab] = useState(DEFAULT_TAB_ID)
  const [activeSurveyModule, setActiveSurveyModule] = useState(DEFAULT_SURVEY_MODULE_ID)
  const [health, setHealth] = useState(null)
  const [isMobile, setIsMobile] = useState(false)
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' ? !navigator.onLine : false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('sidebar_collapsed') === 'true' } catch { return false }
  })
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [isMoreOpen, setIsMoreOpen] = useState(false)
  const [deferredPrompt, setDeferredPrompt] = useState(null)
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

  const surveyModules = useMemo(
    () => SURVEY_MODULES.map((mod) => ({
      ...mod,
      label: mod.label[locale] || mod.label.en,
      description: mod.description[locale] || mod.description.en,
      shellHint: mod.shellHint[locale] || mod.shellHint.en,
      protocols: mod.protocols[locale] || mod.protocols.en,
    })),
    [locale],
  )

  const activeSurveyModuleMeta = surveyModules.find((m) => m.id === activeSurveyModule) || surveyModules[0]

  const navGroups = useMemo(
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

  const refreshHealth = useCallback(async () => {
    // Hybrid-local builds intentionally have no backend — skip the probe and
    // present a synthetic "ready" health object so the UI shows "Local mode"
    // instead of cycling through Connecting → Backend offline.
    if (IS_HYBRID_LOCAL_MODE) {
      setHealth(buildHybridLocalHealth())
      setHealthFetchedAt(Date.now())
      return
    }
    try {
      const data = await getHealthStatus()
      setHealth(data)
      setHealthFetchedAt(Date.now())
    } catch {
      setHealth(buildFallbackHealth(t))
      setHealthFetchedAt(Date.now())
    }
  }, [t])

  const toggleLang = () => {
    const next = i18n.language === 'zh' ? 'en' : 'zh'
    i18n.changeLanguage(next)
    localStorage.setItem('species_monitoring_platform_lang', next)
  }

  const handleInstall = async () => {
    if (!deferredPrompt) return
    deferredPrompt.prompt()
    try { await deferredPrompt.userChoice } catch { /* ignore */ }
    setDeferredPrompt(null)
  }

  useEffect(() => { refreshHealth() }, [refreshHealth])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') refreshHealth()
    }, 30000)
    return () => window.clearInterval(id)
  }, [refreshHealth])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const mq = window.matchMedia('(max-width: 767px)')
    const update = (e) => setIsMobile(e.matches)
    setIsMobile(mq.matches)
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', update)
      return () => mq.removeEventListener('change', update)
    }
    mq.addListener(update)
    return () => mq.removeListener(update)
  }, [])

  useEffect(() => {
    const onOnline = () => { setIsOffline(false); refreshHealth() }
    const onOffline = () => setIsOffline(true)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [refreshHealth])

  useEffect(() => {
    const onBefore = (e) => { e.preventDefault(); setDeferredPrompt(e) }
    const onInstalled = () => setDeferredPrompt(null)
    window.addEventListener('beforeinstallprompt', onBefore)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBefore)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  useEffect(() => {
    try { localStorage.setItem('sidebar_collapsed', String(sidebarCollapsed)) } catch { /* ignore */ }
  }, [sidebarCollapsed])

  useEffect(() => {
    if (!isMobile) { setMobileSidebarOpen(false); setIsMoreOpen(false) }
  }, [isMobile])

  const isOnline = health?.status === 'ok'
  const isHybridLocal = Boolean(health?.hybrid_local)
  const ActiveComponent = TAB_COMPONENTS[activeTab]

  let tabProps = {}
  if (activeTab === 'dashboard') {
    tabProps = { health, setActiveTab, refreshHealth, healthFetchedAt }
  } else if (activeTab === 'settings' || activeTab === 'about') {
    tabProps = { health, refreshHealth, healthFetchedAt }
  } else if (activeTab === 'fieldops') {
    tabProps = {
      activeModule: activeSurveyModule,
      moduleMeta: activeSurveyModuleMeta,
      onSelectModule: setActiveSurveyModule,
    }
  }

  const healthWarnings = Array.isArray(health?.warnings) ? health.warnings : []
  const primaryWarning = healthWarnings.find((w) => w.level === 'error')
    || healthWarnings.find((w) => w.level === 'warning')
    || null

  const runtimeState = health?.runtime_state || (isOnline ? 'ready' : 'error')
  const currentModel = health?.model?.version?.toUpperCase() || 'CNN'
  const currentSpecies = health?.num_species_model || health?.num_species || 0
  const mobileShowsMoreActive = isMoreOpen || !MOBILE_PRIMARY_TAB_IDS.includes(activeTab)

  const handleNavClick = (tabId) => {
    setActiveTab(tabId)
    if (isMobile) setMobileSidebarOpen(false)
  }

  return (
    <div className={`app-layout ${sidebarCollapsed && !isMobile ? 'sidebar-collapsed' : ''}`}>
      {/* Sidebar overlay for mobile */}
      <div
        className={`sidebar-overlay ${mobileSidebarOpen ? 'visible' : ''}`}
        onClick={() => setMobileSidebarOpen(false)}
      />

      {/* Sidebar */}
      <aside className={`app-sidebar ${sidebarCollapsed && !isMobile ? 'collapsed' : ''} ${mobileSidebarOpen ? 'mobile-open' : ''}`}>
        <div className="app-sidebar-header">
          <div className="app-sidebar-brand">
            <div className="app-sidebar-logo">
              <Bird className="h-5 w-5 text-white" />
            </div>
            <div className="min-w-0 nav-label">
              <div className="app-sidebar-title">
                {isMobile ? appCopy.appNameMobile : (sidebarCollapsed ? '' : appCopy.appNameMobile)}
              </div>
              {!sidebarCollapsed && (
                <div className="app-sidebar-subtitle">{appCopy.appSubtitle}</div>
              )}
            </div>
          </div>
          {isMobile && (
            <button
              onClick={() => setMobileSidebarOpen(false)}
              className="btn-ghost btn-icon"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        <nav className="app-sidebar-nav">
          {navGroups.map((group) => (
            <div key={group.id} className="sidebar-nav-group">
              <div className="sidebar-nav-group-label">{group.label}</div>
              {group.tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => handleNavClick(tab.id)}
                  className={`sidebar-nav-item ${activeTab === tab.id ? 'active' : ''}`}
                  data-testid={`nav-tab-${tab.id}`}
                  data-active={activeTab === tab.id ? 'true' : 'false'}
                >
                  <tab.icon className="nav-icon" />
                  <span className="nav-label">{tab.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="app-sidebar-footer">
          {!isMobile && (
            <button
              onClick={() => setSidebarCollapsed((c) => !c)}
              className="sidebar-nav-item w-full justify-center"
              title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {sidebarCollapsed
                ? <ChevronRight className="nav-icon" />
                : <ChevronLeft className="nav-icon" />
              }
              <span className="nav-label">
                {sidebarCollapsed ? '' : (locale === 'zh' ? '收起' : 'Collapse')}
              </span>
            </button>
          )}

          <div className={`mt-2 flex items-center gap-2 px-2 ${sidebarCollapsed && !isMobile ? 'justify-center' : ''}`}>
            <span
              data-testid="app-status-dot"
              data-state={isOnline ? 'online' : health === null ? 'connecting' : 'offline'}
              className={`status-dot ${isOnline ? 'status-dot-online' : health === null ? 'status-dot-warning' : 'status-dot-offline'}`}
            />
            {(!sidebarCollapsed || isMobile) && (
              <span className="text-xs text-white/40 nav-label">
                {isHybridLocal
                  ? t('appShell.hybridLocalMode')
                  : isOnline
                    ? `${currentModel} · ${currentSpecies} spp.`
                    : health === null
                      ? t('appShell.connecting')
                      : t('appShell.backendOffline')
                }
              </span>
            )}
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="app-main">
        {/* Top bar */}
        <header className="app-topbar">
          <div className="flex items-center gap-3">
            {isMobile && (
              <button
                onClick={() => setMobileSidebarOpen(true)}
                className="btn-ghost btn-icon"
              >
                <Menu className="h-5 w-5" />
              </button>
            )}
            <div className="min-w-0">
              <h1 className="text-sm font-semibold text-white/90 truncate">
                {activeTabMeta.label}
              </h1>
              {!isMobile && (
                <p className="text-xs text-white/30 truncate">
                  {TAB_SUMMARIES[locale]?.[activeTab] || ''}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {deferredPrompt && !isMobile && (
              <button onClick={handleInstall} className="btn-secondary btn-sm">
                <Download className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{t('appShell.install')}</span>
              </button>
            )}

            <button onClick={toggleLang} className="btn-ghost btn-icon" title={i18n.language === 'zh' ? 'English' : '中文'}>
              <Globe2 className="h-4 w-4" />
            </button>

            <button onClick={refreshHealth} className="btn-ghost btn-icon" title={t('appShell.refreshRuntime')}>
              <RefreshCw className={`h-4 w-4 ${health === null ? 'animate-spin' : ''}`} />
            </button>

            {!isMobile && (
              <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-1.5">
                <span className={`status-dot ${isOnline ? 'status-dot-online' : health === null ? 'status-dot-warning' : 'status-dot-offline'}`} />
                <span className="text-xs text-white/50">
                  {isHybridLocal
                    ? t('appShell.hybridLocalMode')
                    : isOnline
                      ? `${currentModel} · ${currentSpecies} ${t('appShell.speciesCount', { count: currentSpecies }).trim()}`
                      : health === null
                        ? t('appShell.connecting')
                        : t('appShell.backendOffline')
                  }
                </span>
              </div>
            )}
          </div>
        </header>

        {/* Banners */}
        {isOffline && (
          <div className="offline-banner">
            <WifiOff className="inline h-3.5 w-3.5 mr-1.5" />
            {t('appShell.offlineBanner')}
          </div>
        )}

        {primaryWarning && isOnline && (() => {
          const wCode = primaryWarning.code || ''
          const titleKey = `appShell.warningTitle_${wCode}`
          const detailKey = `appShell.warningDetail_${wCode}`
          const hasKey = t(titleKey) !== titleKey
          const detailParams = wCode === 'SPECIES_COVERAGE_GAP'
            ? { model: health?.num_species_model || 0, db: health?.num_species_db || 0, missing: Math.max(0, (health?.num_species_db || 0) - (health?.num_species_model || 0)) }
            : {}
          return (
            <div className={`health-warning-banner ${primaryWarning.level === 'error' ? 'level-error' : 'level-warning'}`}>
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span className="font-medium text-sm">{hasKey ? t(titleKey) : primaryWarning.title}:</span>
              <span className="text-xs">{hasKey ? t(detailKey, detailParams) : primaryWarning.detail}</span>
            </div>
          )
        })()}

        {/* Main content */}
        <main className={`app-content ${isMobile ? 'mobile-main' : ''}`}>
          <Suspense fallback={<TabFallback />}>
            {ActiveComponent && <ActiveComponent {...tabProps} />}
          </Suspense>
        </main>
      </div>

      {/* Mobile bottom nav */}
      {isMobile && (
        <>
          <MobileBottomNav
            activeTab={activeTab}
            moreActive={mobileShowsMoreActive}
            tabs={mobilePrimaryTabs}
            onSelectTab={(tabId) => { setActiveTab(tabId); setIsMoreOpen(false) }}
            onOpenMore={() => setIsMoreOpen((c) => !c)}
            t={t}
          />

          {isMoreOpen && (
            <MobileMoreSheet
              activeTab={activeTab}
              groups={navGroups.map((g) => ({
                ...g,
                tabs: g.tabs.filter((tab) => mobileMoreTabs.some((m) => m.id === tab.id)),
              })).filter((g) => g.tabs.length > 0)}
              isOnline={isOnline}
              isHybridLocal={isHybridLocal}
              locale={locale}
              modelLabel={currentModel}
              speciesCount={currentSpecies}
              modules={surveyModules}
              activeModule={activeSurveyModule}
              onClose={() => setIsMoreOpen(false)}
              onSelectModule={setActiveSurveyModule}
              onSelectTab={(tabId) => { setActiveTab(tabId); setIsMoreOpen(false) }}
              onInstall={deferredPrompt ? handleInstall : null}
              t={t}
            />
          )}

          {deferredPrompt && !isMoreOpen && (
            <div className="install-banner md:hidden">
              <div className="flex items-center justify-between gap-3 rounded-xl border border-emerald-500/20 bg-[#0c1117]/95 px-3 py-2.5 shadow-lg backdrop-blur-xl">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-white">{t('appShell.installMobileTitle')}</p>
                  <p className="truncate text-[11px] text-white/30">{t('appShell.installMobileBody')}</p>
                </div>
                <button
                  onClick={handleInstall}
                  className="btn-primary btn-sm shrink-0"
                >
                  {t('appShell.install')}
                </button>
              </div>
            </div>
          )}
        </>
      )}
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
        >
          <tab.icon className="h-5 w-5" />
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

function MobileMoreSheet({
  activeTab,
  activeModule,
  groups,
  isOnline,
  isHybridLocal,
  locale,
  modelLabel,
  modules,
  speciesCount,
  onClose,
  onSelectModule,
  onSelectTab,
  onInstall,
  t,
}) {
  return (
    <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm md:hidden" onClick={onClose}>
      <div
        className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto overscroll-contain rounded-t-2xl border-t border-white/[0.08] bg-[#0c1117]/98 px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/15" />

        <div className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2.5">
          <div className="flex items-center gap-2">
            <span className={`status-dot ${isOnline ? 'status-dot-online' : 'status-dot-offline'}`} />
            <span className="text-xs font-medium text-white">
              {isHybridLocal
                ? t('appShell.hybridLocalMode')
                : isOnline
                  ? `${modelLabel} · ${t('appShell.statusReady')}`
                  : t('appShell.backendOffline')}
            </span>
          </div>
          <span className="text-[11px] text-white/30">{speciesCount} spp.</span>
        </div>

        <div className="mt-3 space-y-3">
          {Array.isArray(modules) && modules.length > 0 && (
            <div>
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-white/25">
                {t('appShell.surveyModules')}
              </p>
              <div className="space-y-1.5">
                {modules.map((mod) => {
                  const ModIcon = mod.icon
                  const isActive = activeModule === mod.id
                  return (
                    <button
                      key={mod.id}
                      onClick={() => onSelectModule(mod.id)}
                      className={`mobile-quick-action w-full ${isActive ? 'border-emerald-500/20 bg-emerald-500/8' : ''}`}
                    >
                      <ModIcon className={`h-5 w-5 shrink-0 ${isActive ? 'text-emerald-400' : 'text-white/30'}`} />
                      <span className={`text-sm font-medium ${isActive ? 'text-emerald-300' : 'text-white'}`}>{mod.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
          {groups.map((group) => (
            <div key={group.id}>
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-white/25">{group.label}</p>
              <div className="space-y-1.5">
                {group.tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => onSelectTab(tab.id)}
                    className={`mobile-quick-action w-full ${activeTab === tab.id ? 'border-emerald-500/20 bg-emerald-500/8' : ''}`}
                  >
                    <tab.icon className={`h-5 w-5 shrink-0 ${activeTab === tab.id ? 'text-emerald-400' : 'text-white/30'}`} />
                    <span className={`text-sm font-medium ${activeTab === tab.id ? 'text-emerald-300' : 'text-white'}`}>{tab.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {onInstall && (
          <button onClick={onInstall} className="mt-3 btn-primary w-full py-3 rounded-xl">
            <Download className="h-4 w-4" />
            {t('appShell.installHome')}
          </button>
        )}
      </div>
    </div>
  )
}
