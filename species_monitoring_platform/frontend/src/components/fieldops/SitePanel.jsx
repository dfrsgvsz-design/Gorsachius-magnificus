import React from 'react'
import { ChevronRight, MapPin } from 'lucide-react'

/**
 * Site selector — row-list style matching ProjectManagementPanel.
 * Field workers select from pre-created sites (admin creates in SettingsTab).
 */
export default function SitePanel({
  copy,
  locale = 'zh',
  projectSites,
  currentProjectId,
  currentSiteId,
  siteForm,
  onSelectSite,
  onChangeSiteForm,
  onUseGps,
  onSaveSite,
}) {
  const isZh = locale === 'zh'
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#BF5AF2]/15">
          <MapPin className="h-4 w-4 text-[#BF5AF2]" />
        </div>
        <h3 className="flex-1 text-[15px] font-semibold text-white">{copy.site}</h3>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">
          {projectSites.length}
        </span>
      </div>
      {!currentProjectId && (
        <p className="px-1 text-[13px] text-white/25">
          {isZh ? '请先选择项目' : 'Select a project first'}
        </p>
      )}
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        {currentProjectId && projectSites.length === 0 && (
          <p className="px-4 py-5 text-center text-[14px] text-white/25">
            {isZh ? '该项目暂无站点' : 'No sites in this project'}
          </p>
        )}
        {projectSites.map((site, idx) => {
          const isActive = site.site_id === currentSiteId
          const hasCoords = site.latitude && site.longitude
          return (
            <button
              key={site.site_id}
              onClick={() => onSelectSite(site.site_id)}
              className={`flex w-full items-center gap-3 px-4 py-[13px] text-left transition-colors active:bg-white/[0.04] ${
                idx < projectSites.length - 1 ? 'border-b border-white/[0.04]' : ''
              }`}
            >
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-[#BF5AF2]/15' : 'bg-white/[0.06]'}`}>
                <MapPin className={`h-4 w-4 ${isActive ? 'text-[#BF5AF2]' : 'text-white/30'}`} />
              </div>
              <div className="min-w-0 flex-1">
                <span className={`block truncate text-[15px] ${isActive ? 'font-medium text-white' : 'text-white/80'}`}>
                  {site.name}
                </span>
                <span className="text-[12px] text-white/25">
                  {site.habitat_type || ''}{hasCoords ? ` · ${Number(site.latitude).toFixed(2)}, ${Number(site.longitude).toFixed(2)}` : ''}
                </span>
              </div>
              {isActive && (
                <span className="shrink-0 rounded-full bg-[#BF5AF2]/15 px-2.5 py-1 text-[11px] font-medium text-[#BF5AF2]">
                  {isZh ? '当前' : 'Active'}
                </span>
              )}
              <ChevronRight className={`h-4 w-4 shrink-0 ${isActive ? 'text-[#BF5AF2]' : 'text-white/15'}`} />
            </button>
          )
        })}
      </div>
    </div>
  )
}
