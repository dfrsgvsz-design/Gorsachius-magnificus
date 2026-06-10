import React from 'react'
import MetricCard from './MetricCard'
import { lineDistanceMeters } from '../../lib/surveyOffline'

export default function SurveyEventPanel({
  copy,
  protocolDefinition,
  protocolState,
  siteRoutes,
  currentRouteId,
  selectedRoute,
  routeObservations,
  protocolTracks,
  protocolObservations,
  transectForm,
  transectSession,
  transectEffortMinutes,
  trackStatus,
  onSelectRoute,
  onSetTransectForm,
  onProtocolEventFieldChange,
}) {
  return (
    <div className="section-shell space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{protocolDefinition.shellLabel}</h3>
        <span className="text-xs text-gray-400">{siteRoutes.length}</span>
      </div>
      <p className="text-xs text-gray-500">{protocolDefinition.assetHint}</p>
      <select
        value={currentRouteId}
        onChange={(event) => onSelectRoute(event.target.value)}
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
      >
        <option value="">{protocolDefinition.assetLabel}</option>
        {siteRoutes.map((route) => (
          <option key={route.route_id} value={route.route_id}>{route.name}</option>
        ))}
      </select>
      <div className="grid gap-2 sm:grid-cols-2">
        <MetricCard
          title={copy.routeLength || 'Route length'}
          value={`${Math.round(selectedRoute?.length_m || lineDistanceMeters(selectedRoute?.geometry?.coordinates || []))} m`}
          note={selectedRoute?.route_type || protocolDefinition.assetLabel}
        />
        <MetricCard
          title={copy.recordsOnTransect || 'Records'}
          value={routeObservations.length}
          note={protocolDefinition.label}
        />
      </div>
      <input
        value={transectForm.observer}
        onChange={(event) => onSetTransectForm((current) => ({ ...current, observer: event.target.value }))}
        placeholder={copy.observer}
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
      />
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          value={transectForm.weather}
          onChange={(event) => onSetTransectForm((current) => ({ ...current, weather: event.target.value }))}
          placeholder={copy.weather || 'Weather'}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <input
          value={transectSession.started_at ? new Date(transectSession.started_at).toLocaleString() : ''}
          readOnly
          placeholder={copy.walkStart || 'Walk start'}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-300"
        />
      </div>
      <textarea
        value={transectForm.notes}
        onChange={(event) => onSetTransectForm((current) => ({ ...current, notes: event.target.value }))}
        placeholder={copy.transectNotes || 'Transect notes'}
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
      />
      <div className="grid gap-2 sm:grid-cols-2">
        {protocolDefinition.eventFields.map((field) => (
          <label key={field.key} className="space-y-1 text-xs text-gray-400">
            <span className="block">{field.label}</span>
            <input
              type={field.type || 'text'}
              value={protocolState.event[field.key] || ''}
              onChange={(event) => onProtocolEventFieldChange(field.key, event.target.value)}
              placeholder={field.placeholder || field.label}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
            />
          </label>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard title={copy.track || 'Track recorder'} value={protocolTracks.length} note={copy.walks || 'walks'} />
        <MetricCard title={copy.effort || 'Effort'} value={`${transectEffortMinutes} min`} note={trackStatus} />
        <MetricCard title={copy.observation || 'Observation'} value={protocolObservations.length} note={copy.routeSummary || 'protocol records'} />
      </div>
    </div>
  )
}
