import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Bug,
  Database,
  Leaf,
  MapPinned,
  RefreshCw,
  ShieldCheck,
  Sprout,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  getApiErrorMessage,
  getSurveyProtocols,
  getSurveyTaxonomyPackages,
} from '../../lib/api'
import { LoadingState, StatusBanner } from '../common'

const COPY = {
  en: {
    badge: 'Taxonomy and protocol readiness',
    title: 'Species monitoring reference packages',
    body: 'Review the taxonomy package wiring, survey protocols, and catalog completeness for terrestrial vertebrates, plants, and insects before release.',
    refresh: 'Refresh',
    refreshing: 'Refreshing...',
    module: 'Module',
    jurisdiction: 'Jurisdiction',
    packages: 'Packages',
    protocols: 'Protocols',
    catalogEntries: 'Catalog entries',
    lastSyncPrefix: 'Last sync',
    packageStatusSeed: 'Seed only',
    packageStatusReady: 'Exhaustive',
    packageStatusUnknown: 'Unspecified',
    packageStatusBody: 'Current package metadata is still seed-only or non-exhaustive. Release-grade species imports are still required for this slice.',
    packageStatusReadyBody: 'Current package metadata is marked exhaustive for this slice.',
    packageSection: 'Taxonomy packages',
    protocolSection: 'Survey protocols',
    assetPackage: 'Asset package',
    backbone: 'Backbone',
    taxonGroups: 'Taxon groups',
    languages: 'Languages',
    protocolsLabel: 'Protocols',
    catalogStatus: 'Catalog status',
    localSeedAssets: 'Local seed assets',
    noPackages: 'No taxonomy package metadata is available for the selected slice.',
    noProtocols: 'No survey protocol metadata is available for the selected slice.',
    requiredEventFields: 'Required event fields',
    requiredRecordFields: 'Required record fields',
    designAssets: 'Design assets',
    trackPolicy: 'Track policy',
    moduleVertebrates: 'Terrestrial vertebrates',
    modulePlants: 'Plants',
    moduleInsects: 'Insects',
    jurisdictionMainland: 'Mainland China',
    jurisdictionTaiwan: 'Taiwan',
  },
  zh: {
    badge: '名录与协议完备度',
    title: '物种监测参考包',
    body: '在发布前检查陆生脊椎动物、植物、昆虫三条线当前接入的 taxonomy 包、调查协议和名录完备状态。',
    refresh: '刷新',
    refreshing: '刷新中...',
    module: '模块',
    jurisdiction: '地区',
    packages: '名录包',
    protocols: '调查协议',
    catalogEntries: '名录条目',
    lastSyncPrefix: '最近同步',
    packageStatusSeed: '仅种子数据',
    packageStatusReady: '完整名录',
    packageStatusUnknown: '状态未声明',
    packageStatusBody: '当前名录包的元数据仍为种子状态或不完整，正式上线前仍需导入权威物种名录。',
    packageStatusReadyBody: '当前切片的名录包元数据已标记为完整。',
    packageSection: '分类名录包',
    protocolSection: '调查协议',
    assetPackage: '资源包',
    backbone: '来源骨干',
    taxonGroups: '分类组',
    languages: '语言',
    protocolsLabel: '协议',
    catalogStatus: '名录状态',
    localSeedAssets: '本地种子资源',
    noPackages: '当前筛选条件下还没有可用的分类名录包元数据。',
    noProtocols: '当前筛选条件下还没有可用的调查协议元数据。',
    requiredEventFields: '必填事件字段',
    requiredRecordFields: '必填记录字段',
    designAssets: '设计资产',
    trackPolicy: '轨迹策略',
    moduleVertebrates: '陆生脊椎动物',
    modulePlants: '植物',
    moduleInsects: '昆虫',
    jurisdictionMainland: '中国大陆',
    jurisdictionTaiwan: '台湾',
  },
}

const PROGRAM_OPTIONS = [
  { id: 'terrestrial_vertebrates', icon: Database, copyKey: 'moduleVertebrates' },
  { id: 'plants', icon: Leaf, copyKey: 'modulePlants' },
  { id: 'insects', icon: Bug, copyKey: 'moduleInsects' },
]

const JURISDICTION_OPTIONS = [
  { id: 'mainland_china', copyKey: 'jurisdictionMainland' },
  { id: 'taiwan', copyKey: 'jurisdictionTaiwan' },
]

function formatTimestamp(timestamp) {
  if (!timestamp) return '--:--:--'
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

export default function SpeciesTab() {
  const { i18n } = useTranslation()
  const locale = i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
  const copy = COPY[locale]
  const [program, setProgram] = useState('terrestrial_vertebrates')
  const [jurisdiction, setJurisdiction] = useState('mainland_china')
  const [packages, setPackages] = useState([])
  const [protocols, setProtocols] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const loadReferenceData = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const [taxonomyData, protocolData] = await Promise.all([
        getSurveyTaxonomyPackages({ program, jurisdiction }),
        getSurveyProtocols({ program }),
      ])
      setPackages(taxonomyData.packages || [])
      setProtocols(protocolData.protocols || [])
      setLastUpdated(Date.now())
    } catch (err) {
      setPackages([])
      setProtocols([])
      setError(getApiErrorMessage(err, 'Failed to load species monitoring reference data.'))
    } finally {
      setRefreshing(false)
      setLoading(false)
    }
  }, [jurisdiction, program])

  useEffect(() => {
    loadReferenceData()
  }, [loadReferenceData])

  const selectedProgram = useMemo(
    () => PROGRAM_OPTIONS.find((item) => item.id === program) || PROGRAM_OPTIONS[0],
    [program],
  )
  const selectedJurisdiction = useMemo(
    () => JURISDICTION_OPTIONS.find((item) => item.id === jurisdiction) || JURISDICTION_OPTIONS[0],
    [jurisdiction],
  )
  const totalCatalogEntries = useMemo(
    () => packages.reduce((sum, item) => sum + Number(item.catalog_count || 0), 0),
    [packages],
  )
  const allSeedOnly = packages.length > 0 && packages.every(
    (item) => item.seed_only,
  )

  const SelectedProgramIcon = selectedProgram.icon

  return (
    <div className="space-y-5">
      <section className="glass-card space-y-3 p-4 md:space-y-4 md:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 max-w-3xl">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.06] bg-[#0A84FF]/10 px-2.5 py-0.5 text-[11px] font-medium text-[#0A84FF] md:gap-2 md:px-3 md:py-1 md:text-xs">
              <Database className="h-3 w-3 md:h-3.5 md:w-3.5" />
              {copy.badge}
            </div>
            <h2 className="mt-2 text-lg font-bold text-white md:mt-3 md:text-2xl">{copy.title}</h2>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-white/50 md:mt-2 md:text-sm md:leading-6">
              {copy.body}
            </p>
          </div>

          <button
            onClick={loadReferenceData}
            disabled={refreshing}
            className="touch-button inline-flex items-center gap-1 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-2.5 py-1.5 text-[11px] text-white/50 active:scale-[0.97] md:px-3 md:text-xs"
          >
            <RefreshCw className={`h-3 w-3 md:h-3.5 md:w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{refreshing ? copy.refreshing : copy.refresh}</span>
          </button>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-xs font-medium uppercase tracking-[0.2em] text-white/40">{copy.module}</span>
            <div className="relative">
              <SelectedProgramIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#30D158]" />
              <select
                value={program}
                onChange={(event) => setProgram(event.target.value)}
                className="touch-button w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] py-2.5 pl-10 pr-4 text-sm text-white focus:border-[#0A84FF]/40 focus:outline-none"
              >
                {PROGRAM_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id} className="bg-black text-white">
                    {copy[option.copyKey]}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="space-y-1.5">
            <span className="text-xs font-medium uppercase tracking-[0.2em] text-white/40">{copy.jurisdiction}</span>
            <div className="relative">
              <MapPinned className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#0A84FF]" />
              <select
                value={jurisdiction}
                onChange={(event) => setJurisdiction(event.target.value)}
                className="touch-button w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] py-2.5 pl-10 pr-4 text-sm text-white focus:border-[#0A84FF]/40 focus:outline-none"
              >
                {JURISDICTION_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id} className="bg-black text-white">
                    {copy[option.copyKey]}
                  </option>
                ))}
              </select>
            </div>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-white/40 md:gap-3 md:text-xs">
          <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-2 py-0.5 md:px-3 md:py-1">
            {packages.length} {copy.packages}
          </span>
          <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-2 py-0.5 md:px-3 md:py-1">
            {protocols.length} {copy.protocols}
          </span>
          <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-2 py-0.5 md:px-3 md:py-1">
            {totalCatalogEntries} {copy.catalogEntries}
          </span>
          <span className="rounded-full border border-white/[0.06] bg-white/[0.04] px-2 py-0.5 md:px-3 md:py-1">
            {copy.lastSyncPrefix} {formatTimestamp(lastUpdated)}
          </span>
        </div>
      </section>

      <StatusBanner tone="error" message={error} />

      {loading ? (
        <LoadingState text={copy.refreshing} />
      ) : (
        <>
          <section className={`glass-card flex items-start gap-3 p-4 ${allSeedOnly ? 'border border-white/[0.06] bg-[#FF9F0A]/8' : 'border border-white/[0.06] bg-[#30D158]/8'}`}>
            {allSeedOnly ? (
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[#FF9F0A]" />
            ) : (
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#30D158]" />
            )}
            <div>
              <p className={`text-sm font-semibold ${allSeedOnly ? 'text-[#FF9F0A]' : 'text-[#30D158]'}`}>
                {allSeedOnly ? copy.packageStatusSeed : copy.packageStatusReady}
              </p>
              <p className="mt-1 text-sm text-white/50">
                {allSeedOnly ? copy.packageStatusBody : copy.packageStatusReadyBody}
              </p>
              <p className="mt-2 text-xs uppercase tracking-[0.2em] text-white/25">
                {copy[selectedProgram.copyKey]} / {copy[selectedJurisdiction.copyKey]}
              </p>
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Sprout className="h-4 w-4 text-[#30D158]" />
              <h3 className="text-sm font-semibold text-white md:text-base">{copy.packageSection}</h3>
            </div>
            {packages.length === 0 ? (
              <div className="glass-card p-4 text-sm text-white/40">{copy.noPackages}</div>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {packages.map((item) => (
                  <PackageCard key={item.package_id} item={item} copy={copy} />
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-[#0A84FF]" />
              <h3 className="text-sm font-semibold text-white md:text-base">{copy.protocolSection}</h3>
            </div>
            {protocols.length === 0 ? (
              <div className="glass-card p-4 text-sm text-white/40">{copy.noProtocols}</div>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {protocols.map((item) => (
                  <ProtocolCard key={item.protocol} item={item} copy={copy} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

function PackageCard({ item, copy }) {
  const seedOnly = Boolean(item.seed_only)
  const statusLabel = seedOnly
    ? copy.packageStatusSeed
    : item.exhaustive_species_content
      ? copy.packageStatusReady
      : copy.packageStatusUnknown

  return (
    <article className="glass-card space-y-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white md:text-base">{item.label_zh || item.label || item.package_id}</p>
          <p className="mt-1 break-all text-xs text-white/25">{item.package_id}</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${seedOnly ? 'border-white/[0.06] bg-[#FF9F0A]/10 text-[#FF9F0A]' : 'border-white/[0.06] bg-[#30D158]/10 text-[#30D158]'}`}>
          {statusLabel}
        </span>
      </div>
      <MetaRow label={copy.assetPackage} value={`${item.asset_package_id || '--'} / ${item.asset_package_version || '--'}`} />
      <MetaRow label={copy.backbone} value={item.backbone || '--'} />
      <MetaRow label={copy.catalogStatus} value={`${item.catalog_status || '--'} (${item.catalog_count || 0})`} />
      <MetaRow label={copy.localSeedAssets} value={String(item.local_seed_asset_count || 0)} />
      <TagRow label={copy.taxonGroups} values={item.taxa_groups || []} />
      <TagRow label={copy.languages} values={item.languages || []} />
      <TagRow label={copy.protocolsLabel} values={item.protocols || []} />
    </article>
  )
}

function ProtocolCard({ item, copy }) {
  return (
    <article className="glass-card space-y-3 p-4">
      <div>
        <p className="text-sm font-semibold text-white md:text-base">{item.label || item.display_name || item.protocol}</p>
        <p className="mt-1 break-all text-xs text-white/25">{item.protocol}</p>
      </div>
      {item.description ? (
        <p className="text-sm leading-6 text-white/50">{item.description}</p>
      ) : null}
      <MetaRow label={copy.trackPolicy} value={item.track_policy || '--'} />
      <MetaRow label={copy.requiredEventFields} value={String((item.required_event_fields || []).length)} />
      <MetaRow label={copy.requiredRecordFields} value={String((item.required_record_fields || []).length)} />
      <TagRow label={copy.designAssets} values={item.design_asset_types || []} />
      <TagRow label={copy.jurisdiction} values={item.jurisdictions || []} />
    </article>
  )
}

function MetaRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 text-sm">
      <span className="shrink-0 text-white/30">{label}</span>
      <span className="text-right text-white/60">{value || '--'}</span>
    </div>
  )
}

function TagRow({ label, values }) {
  const list = values.length > 0 ? values : ['--']
  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-[0.2em] text-white/25">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {list.map((value) => (
          <span
            key={`${label}-${value}`}
            className="rounded-full border border-white/[0.06] bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/50"
          >
            {value}
          </span>
        ))}
      </div>
    </div>
  )
}
