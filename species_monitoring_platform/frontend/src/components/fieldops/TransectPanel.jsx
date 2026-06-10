import React, { useState } from 'react'
import { ChevronDown, ChevronRight, Route } from 'lucide-react'
import MetricCard from './MetricCard'
import { lineDistanceMeters } from '../../lib/surveyOffline'
import { localizeProtocol } from './protocolEngine'
import ComboField from './ComboField'

/**
 * Route/transect selector — row-list style matching ProjectManagementPanel.
 * Routes shown as clickable rows. Selecting a route expands observer/weather inputs.
 */
export default function TransectPanel({
  copy,
  protocolDefinition: rawProtocolDefinition,
  locale = 'zh',
  siteRoutes,
  currentRouteId,
  selectedRoute,
  routeObservations,
  protocolTracks,
  protocolObservations,
  transectEffortMinutes,
  trackStatus,
  transectForm,
  transectSession,
  protocolState,
  onSelectRoute,
  onChangeTransectForm,
  onEventFieldChange,
}) {
  const isZh = locale === 'zh'
  const protocolDefinition = localizeProtocol(rawProtocolDefinition, locale)
  const [showDetails, setShowDetails] = useState(false)

  const fieldCls = 'w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white placeholder:text-white/25 focus:border-[#0A84FF]/40 focus:outline-none'
  return (
    <div className="space-y-3">
      {/* 标题 */}
      <div className="flex items-center gap-2 px-1">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#30D158]/15">
          <Route className="h-4 w-4 text-[#30D158]" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold text-white">{protocolDefinition.shellLabel}</h3>
          <p className="text-[12px] text-white/30">{protocolDefinition.assetHint}</p>
        </div>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">
          {siteRoutes.length}
        </span>
      </div>

      {/* iOS Grouped Inset 路线列表 */}
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        {siteRoutes.length === 0 && (
          <p className="px-4 py-5 text-center text-[14px] text-white/25">
            {isZh ? '该站点暂无路线' : 'No routes in this site'}
          </p>
        )}
        {siteRoutes.map((route, idx) => {
          const isActive = route.route_id === currentRouteId
          const lengthM = Math.round(route.length_m || lineDistanceMeters(route.geometry?.coordinates || []))
          return (
            <button
              key={route.route_id}
              onClick={() => onSelectRoute(route.route_id)}
              className={`flex w-full items-center gap-3 px-4 py-[13px] text-left transition-colors active:bg-white/[0.04] ${
                idx < siteRoutes.length - 1 ? 'border-b border-white/[0.04]' : ''
              }`}
            >
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-[#30D158]/15' : 'bg-white/[0.06]'}`}>
                <Route className={`h-4 w-4 ${isActive ? 'text-[#30D158]' : 'text-white/30'}`} />
              </div>
              <div className="min-w-0 flex-1">
                <span className={`block truncate text-[15px] ${isActive ? 'font-medium text-white' : 'text-white/80'}`}>
                  {route.name}
                </span>
                <span className="text-[12px] text-white/25">
                  {lengthM > 0 ? `${lengthM}m` : ''}{route.route_type ? ` · ${route.route_type}` : ''}
                </span>
              </div>
              {isActive && (
                <span className="shrink-0 rounded-full bg-[#30D158]/15 px-2.5 py-1 text-[11px] font-medium text-[#30D158]">
                  {isZh ? '当前' : 'Active'}
                </span>
              )}
              <ChevronRight className={`h-4 w-4 shrink-0 ${isActive ? 'text-[#30D158]' : 'text-white/15'}`} />
            </button>
          )
        })}
      </div>

      {/* 调查参数 — 可展开 */}
      {selectedRoute && (
        <div className="space-y-3">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1.5 px-1 text-[13px] text-[#0A84FF] active:text-[#0A84FF]/60"
          >
            {showDetails ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            {isZh ? '调查参数' : 'Survey parameters'}
          </button>

          {showDetails && (
            <div className="space-y-2 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  value={transectForm.observer}
                  onChange={(e) => onChangeTransectForm({ ...transectForm, observer: e.target.value })}
                  placeholder={copy.observer}
                  className={fieldCls}
                />
                <input
                  value={transectForm.weather}
                  onChange={(e) => onChangeTransectForm({ ...transectForm, weather: e.target.value })}
                  placeholder={copy.weather || 'Weather'}
                  className={fieldCls}
                />
              </div>
              <textarea
                value={transectForm.notes}
                onChange={(e) => onChangeTransectForm({ ...transectForm, notes: e.target.value })}
                placeholder={copy.transectNotes || 'Transect notes'}
                rows={2}
                className={fieldCls}
              />
              {protocolDefinition.eventFields.length > 0 && (
                <div className="grid gap-2 sm:grid-cols-2">
                  {protocolDefinition.eventFields.map((field) => (
                    <label key={field.key} className="space-y-1">
                      <span className="block text-[12px] text-white/30">{field.label}</span>
                      {field.options ? (
                        <ComboField
                          value={protocolState.event[field.key] || ''}
                          onChange={(val) => onEventFieldChange(field.key, val)}
                          options={field.options}
                          placeholder={field.placeholder || field.label}
                        />
                      ) : (
                        <input
                          type={field.type || 'text'}
                          value={protocolState.event[field.key] || ''}
                          onChange={(e) => onEventFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder || field.label}
                          className={fieldCls}
                        />
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 指标 */}
          <div className="grid grid-cols-3 gap-3">
            <MetricCard title={copy.track || 'Track recorder'} value={protocolTracks.length} note={copy.walks || 'walks'} />
            <MetricCard title={copy.effort || 'Effort'} value={`${transectEffortMinutes} min`} note={trackStatus} />
            <MetricCard title={copy.observation || 'Observation'} value={protocolObservations.length} note={copy.routeSummary || 'protocol records'} />
          </div>
        </div>
      )}
    </div>
  )
}
