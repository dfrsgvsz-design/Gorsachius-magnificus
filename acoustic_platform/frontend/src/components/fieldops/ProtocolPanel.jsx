import React from 'react'
import MetricCard from './MetricCard'
import {
  PROGRAM_OPTIONS,
  VERTEBRATE_SUBMODULES,
  EXPORT_JURISDICTIONS,
} from './constants'
import { toArray } from './helpers'
import { normalizeJurisdiction } from '../../lib/surveyOffline'

export default function ProtocolPanel({
  copy,
  locale,
  currentProgram,
  activeModuleMeta,
  moduleLabel,
  moduleDescription,
  moduleShellHint,
  moduleProtocols,
  ActiveModuleIcon,
  protocolDefinition,
  visibleProtocols,
  activeVertebrateSubmoduleId,
  activeVertebrateSubmodule,
  activeJurisdictionLabel,
  exportJurisdiction,
  activeTaxonomyPackage,
  taxonomyPackageNote,
  activeDesignAssets,
  protocolCount,
  onSelectProgram,
  onSelectProtocol,
  onSelectVertebrateSubmodule,
  onChangeJurisdiction,
}) {
  return (
    <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <div className="section-shell space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 p-2 text-cyan-100">
              <ActiveModuleIcon className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-300">Active module</p>
              <h3 className="mt-1 text-lg font-semibold text-white">{moduleLabel}</h3>
              <p className="mt-1 text-sm text-gray-300">{moduleDescription}</p>
            </div>
          </div>
          <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-gray-300">
            {currentProgram}
          </div>
        </div>
        <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-gray-200">
          {moduleShellHint}
        </p>
      </div>

      <div className="section-shell space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-white">Protocol family</h3>
          <p className="mt-1 text-xs text-gray-400">
            Shell selection stays isolated by module while projects, observations, tracks, and exports still converge behind the scenes.
          </p>
        </div>
        <div className={`grid gap-3 ${currentProgram === 'terrestrial_vertebrates' ? 'sm:grid-cols-4' : 'sm:grid-cols-3'}`}>
          <label className="space-y-1 text-xs text-gray-400">
            <span className="block">Program</span>
            <select
              value={currentProgram}
              onChange={(event) => onSelectProgram(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
            >
              {PROGRAM_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>
          {currentProgram === 'terrestrial_vertebrates' && (
            <label className="space-y-1 text-xs text-gray-400">
              <span className="block">Vertebrate submodule</span>
              <select
                value={activeVertebrateSubmoduleId}
                onChange={(event) => onSelectVertebrateSubmodule(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              >
                {VERTEBRATE_SUBMODULES.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </label>
          )}
          <label className="space-y-1 text-xs text-gray-400">
            <span className="block">Protocol</span>
            <select
              value={protocolDefinition.id}
              onChange={(event) => onSelectProtocol(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
            >
              {visibleProtocols.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs text-gray-400">
            <span className="block">Jurisdiction</span>
            <select
              value={exportJurisdiction}
              onChange={(event) => onChangeJurisdiction(normalizeJurisdiction(event.target.value, EXPORT_JURISDICTIONS[0].id))}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
            >
              {EXPORT_JURISDICTIONS.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-3 text-sm text-emerald-100">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-white">{protocolDefinition.label}</span>
            <span className="rounded-full border border-white/10 bg-black/20 px-2 py-1 text-[11px] uppercase tracking-[0.18em] text-emerald-100/80">
              {protocolDefinition.supportsTrack ? 'route + records' : 'station or plot + records'}
            </span>
          </div>
          <p className="mt-2 text-xs text-emerald-50/90">{protocolDefinition.description}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <MetricCard
            title="Jurisdiction"
            value={activeJurisdictionLabel}
            note={protocolDefinition.id}
          />
          <MetricCard
            title={currentProgram === 'terrestrial_vertebrates' ? 'Submodule' : 'Protocol mode'}
            value={currentProgram === 'terrestrial_vertebrates' ? (activeVertebrateSubmodule?.label || 'Vertebrates') : protocolDefinition.shellLabel}
            note={currentProgram === 'terrestrial_vertebrates'
              ? `${activeVertebrateSubmodule?.taxonGroup || protocolDefinition.defaultTaxonGroup} records`
              : protocolDefinition.program}
          />
          <MetricCard
            title="Taxonomy package"
            value={activeTaxonomyPackage?.label || 'Pending sync'}
            note={taxonomyPackageNote}
          />
          <MetricCard
            title="Design assets"
            value={activeDesignAssets.length}
            note={`${protocolCount} backend protocols cached`}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {moduleProtocols.map((protocol) => (
            <span
              key={protocol}
              className={`rounded-full border px-3 py-1 text-xs ${
                protocol === protocolDefinition.label
                  ? 'border-cyan-400/30 bg-cyan-500/10 text-cyan-100'
                  : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'
              }`}
            >
              {protocol}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}
