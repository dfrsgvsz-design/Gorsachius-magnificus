import React from 'react'
import MetricCard from './MetricCard'
import { EXPORT_JURISDICTIONS, toArray } from './fieldOpsUtils'
import { localizeOption } from './protocolEngine'

/**
 * Protocol family selector with program, submodule, protocol, jurisdiction dropdowns,
 * protocol summary badge, metric cards, and module protocol chips.
 * Extracted from FieldOpsTab.jsx lines 2869-2975.
 */
export default function ProtocolSelectorPanel({
  currentProgram,
  protocolDefinition,
  exportJurisdiction,
  activeJurisdictionLabel,
  activeVertebrateSubmoduleId,
  activeVertebrateSubmodule,
  activeTaxonomyPackage,
  taxonomyPackageNote,
  activeDesignAssets,
  visibleProtocols,
  moduleProtocols,
  surveyProtocolsCount,
  PROGRAM_OPTIONS,
  VERTEBRATE_SUBMODULES,
  normalizeJurisdiction,
  onSelectProgram,
  onSelectVertebrateSubmodule,
  onSelectProtocol,
  onChangeJurisdiction,
  locale = 'zh',
}) {
  const isZh = locale === 'zh'
  const lp = localizeOption(protocolDefinition, locale)
  const selectCls = 'w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white focus:border-[#0A84FF]/40 focus:outline-none'
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div>
        <h3 className="text-[15px] font-semibold text-white">{isZh ? '协议族选择' : 'Protocol family'}</h3>
        <p className="mt-1 text-[12px] text-white/30">
          {isZh ? '按模块独立选择调查协议，项目、观测、轨迹和导出在后台统一汇聚。' : 'Shell selection stays isolated by module while projects, observations, tracks, and exports still converge behind the scenes.'}
        </p>
      </div>
      <div className={`grid gap-3 ${currentProgram === 'terrestrial_vertebrates' ? 'sm:grid-cols-4' : 'sm:grid-cols-3'}`}>
        <label className="space-y-1">
          <span className="block text-[12px] text-white/30">{isZh ? '调查项目' : 'Program'}</span>
          <select
            value={currentProgram}
            onChange={(event) => onSelectProgram(event.target.value)}
            className={selectCls}
          >
            {PROGRAM_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>{isZh ? (option.label_zh || option.label) : option.label}</option>
            ))}
          </select>
        </label>
        {currentProgram === 'terrestrial_vertebrates' && (
          <label className="space-y-1">
            <span className="block text-[12px] text-white/30">{isZh ? '类群子模块' : 'Vertebrate submodule'}</span>
            <select
              value={activeVertebrateSubmoduleId}
              onChange={(event) => onSelectVertebrateSubmodule(event.target.value)}
              className={selectCls}
            >
              {VERTEBRATE_SUBMODULES.map((option) => (
                <option key={option.id} value={option.id}>{isZh ? (option.label_zh || option.label) : option.label}</option>
              ))}
            </select>
          </label>
        )}
        <label className="space-y-1">
          <span className="block text-[12px] text-white/30">{isZh ? '调查协议' : 'Protocol'}</span>
          <select
            value={protocolDefinition.id}
            onChange={(event) => onSelectProtocol(event.target.value)}
            className={selectCls}
          >
            {visibleProtocols.map((option) => (
              <option key={option.id} value={option.id}>{isZh ? (option.label_zh || option.label) : option.label}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="block text-[12px] text-white/30">{isZh ? '管辖区' : 'Jurisdiction'}</span>
          <select
            value={exportJurisdiction}
            onChange={(event) => onChangeJurisdiction(normalizeJurisdiction(event.target.value, EXPORT_JURISDICTIONS[0].id))}
            className={selectCls}
          >
            {EXPORT_JURISDICTIONS.map((option) => (
              <option key={option.id} value={option.id}>{isZh ? (option.label_zh || option.label) : option.label}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="rounded-[14px] bg-[#30D158]/10 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[15px] font-medium text-white">{lp.label}</span>
          <span className="rounded-full bg-[#30D158]/20 px-2.5 py-1 text-[11px] font-medium text-[#30D158]">
            {protocolDefinition.supportsTrack ? (isZh ? '路线 + 记录' : 'route + records') : (isZh ? '站点/样方 + 记录' : 'station/plot + records')}
          </span>
        </div>
        <p className="mt-2 text-[13px] leading-5 text-white/50">{lp.description}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title={isZh ? '管辖区' : 'Jurisdiction'}
          value={activeJurisdictionLabel}
          note={protocolDefinition.id}
        />
        <MetricCard
          title={currentProgram === 'terrestrial_vertebrates' ? (isZh ? '类群子模块' : 'Submodule') : (isZh ? '协议模式' : 'Protocol mode')}
          value={currentProgram === 'terrestrial_vertebrates' ? (isZh ? (activeVertebrateSubmodule?.label_zh || activeVertebrateSubmodule?.label || '脊椎动物') : (activeVertebrateSubmodule?.label || 'Vertebrates')) : lp.shellLabel}
          note={currentProgram === 'terrestrial_vertebrates'
            ? `${isZh ? (activeVertebrateSubmodule?.label_zh || activeVertebrateSubmodule?.taxonGroup || protocolDefinition.defaultTaxonGroup) : (activeVertebrateSubmodule?.taxonGroup || protocolDefinition.defaultTaxonGroup)} ${isZh ? '记录' : 'records'}`
            : protocolDefinition.program}
        />
        <MetricCard
          title={isZh ? '分类包' : 'Taxonomy package'}
          value={activeTaxonomyPackage?.label || (isZh ? '等待同步' : 'Pending sync')}
          note={taxonomyPackageNote}
        />
        <MetricCard
          title={isZh ? '设计资料' : 'Design assets'}
          value={activeDesignAssets.length}
          note={isZh ? `${surveyProtocolsCount} 个后端协议已缓存` : `${surveyProtocolsCount} backend protocols cached`}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        {moduleProtocols.map((protocol) => (
          <span
            key={protocol}
            className={`rounded-full px-3 py-1 text-[12px] font-medium ${
              protocol === protocolDefinition.label || protocol === lp.label
                ? 'bg-[#0A84FF]/15 text-[#0A84FF]'
                : 'bg-white/[0.06] text-white/40'
            }`}
          >
            {protocol}
          </span>
        ))}
      </div>
    </div>
  )
}
