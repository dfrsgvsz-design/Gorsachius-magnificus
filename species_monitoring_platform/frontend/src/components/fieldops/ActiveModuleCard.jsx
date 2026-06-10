import React from 'react'

/**
 * Active module info card showing icon, label, description, and shell hint.
 * Extracted from FieldOpsTab.jsx lines 2848-2867.
 */
export default function ActiveModuleCard({
  ActiveModuleIcon,
  moduleLabel,
  moduleDescription,
  moduleShellHint,
  currentProgram,
  locale = 'zh',
}) {
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-[#0A84FF]/15">
            <ActiveModuleIcon className="h-5 w-5 text-[#0A84FF]" />
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#0A84FF]">{locale === 'zh' ? '当前模块' : 'Active module'}</p>
            <h3 className="mt-1 text-[18px] font-bold text-white">{moduleLabel}</h3>
            <p className="mt-1 text-[13px] leading-5 text-white/50">{moduleDescription}</p>
          </div>
        </div>
        <span className="shrink-0 rounded-full bg-white/[0.06] px-3 py-1 text-[12px] font-medium text-white/40">
          {currentProgram}
        </span>
      </div>
      <p className="rounded-[12px] bg-white/[0.04] px-4 py-3 text-[14px] leading-6 text-white/60">
        {moduleShellHint}
      </p>
    </div>
  )
}
