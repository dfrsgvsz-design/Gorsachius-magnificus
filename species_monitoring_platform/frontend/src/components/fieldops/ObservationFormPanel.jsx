import React from 'react'
import { Camera, Mic, Save, Square, Upload } from 'lucide-react'
import { formatBytes } from '../../lib/surveyOffline'
import { localizeProtocol } from './protocolEngine'
import ComboField, { SpeciesAutocomplete } from './ComboField'

/**
 * Observation / species record form with taxonomy, evidence, attachments, and audio capture.
 * Extracted from FieldOpsTab.jsx lines 3283-3430.
 */
export default function ObservationFormPanel({
  copy,
  protocolDefinition: rawProtocolDefinition,
  locale = 'zh',
  selectedRoute,
  currentProjectId,
  observationForm,
  onChangeObservationForm,
  speciesSuggestions,
  taxonomyCatalog,
  availableTaxaOptions,
  protocolState,
  onRecordFieldChange,
  attachments,
  serializingMedia,
  audioCaptureStatus,
  nativeMobile,
  routeObservations,
  onAddAttachments,
  onStartAudioCapture,
  onStopAudioCapture,
  onCapturePhoto,
  validationMissing = [],
  onSaveObservation,
}) {
  const isZh = locale === 'zh'
  const protocolDefinition = localizeProtocol(rawProtocolDefinition, locale)
  const fieldCls = 'w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white placeholder:text-white/25 focus:border-[#0A84FF]/40 focus:outline-none'
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-white">{copy.observation}</h3>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">{routeObservations.length}</span>
      </div>
      <div className="rounded-[12px] bg-[#0A84FF]/10 px-4 py-2.5 text-[13px] text-[#0A84FF]">
        {selectedRoute
          ? `${protocolDefinition.assetLabel}: ${selectedRoute.name}`
          : protocolDefinition.assetHint}
      </div>
      <SpeciesAutocomplete
        value={observationForm.species_text}
        onChange={(val) => onChangeObservationForm({ ...observationForm, species_text: val })}
        taxonomyCatalog={taxonomyCatalog}
        speciesSuggestions={speciesSuggestions}
        placeholder={copy.speciesPlaceholder}
        locale={locale}
      />
      <div className="grid gap-2 sm:grid-cols-2">
        <select
          value={observationForm.taxon_group}
          onChange={(event) => onChangeObservationForm({ ...observationForm, taxon_group: event.target.value })}
          className={fieldCls}
        >
          {availableTaxaOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <select
          value={observationForm.evidence_type}
          onChange={(event) => onChangeObservationForm({ ...observationForm, evidence_type: event.target.value })}
          className={fieldCls}
        >
          <option value="visual">{copy.evidenceVisual}</option>
          <option value="audio">{copy.evidenceAudio}</option>
          <option value="trace">{copy.evidenceTrace}</option>
        </select>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <input
          type="number"
          min="1"
          value={observationForm.count}
          onChange={(event) => onChangeObservationForm({ ...observationForm, count: event.target.value })}
          placeholder={copy.count}
          className={fieldCls}
        />
        <input
          value={observationForm.observer}
          onChange={(event) => onChangeObservationForm({ ...observationForm, observer: event.target.value })}
          placeholder={copy.observer}
          className={fieldCls}
        />
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={observationForm.confidence}
          onChange={(event) => onChangeObservationForm({ ...observationForm, confidence: event.target.value })}
          placeholder={copy.confidence}
          className={fieldCls}
        />
      </div>
      <textarea
        value={observationForm.behavior}
        onChange={(event) => onChangeObservationForm({ ...observationForm, behavior: event.target.value })}
        placeholder={copy.behavior}
        className={fieldCls}
      />
      <textarea
        value={observationForm.habitat_notes}
        onChange={(event) => onChangeObservationForm({ ...observationForm, habitat_notes: event.target.value })}
        placeholder={isZh ? '生境类型' : 'Habitat'}
        className={fieldCls}
      />
      {protocolDefinition.recordFields.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {protocolDefinition.recordFields.map((field) => (
            <label key={field.key} className="space-y-1">
              <span className="block text-[12px] text-white/30">{field.label}</span>
              {field.options ? (
                <ComboField
                  value={protocolState.record[field.key] || ''}
                  onChange={(val) => onRecordFieldChange(field.key, val)}
                  options={field.options}
                  placeholder={field.placeholder || field.label}
                />
              ) : (
                <input
                  type={field.type || 'text'}
                  value={protocolState.record[field.key] || ''}
                  onChange={(event) => onRecordFieldChange(field.key, event.target.value)}
                  placeholder={field.placeholder || field.label}
                  className={fieldCls}
                />
              )}
            </label>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4 px-1 text-[13px] text-white/50">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={observationForm.unknown_taxon} onChange={(event) => onChangeObservationForm({ ...observationForm, unknown_taxon: event.target.checked })} className="rounded" />
          {copy.unknownTaxon}
        </label>
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={observationForm.trace_only} onChange={(event) => onChangeObservationForm({ ...observationForm, trace_only: event.target.checked })} className="rounded" />
          {copy.traceOnly}
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 active:bg-white/[0.08]">
          <Upload className="h-4 w-4" />
          {serializingMedia ? `${copy.attachments}...` : copy.attachments}
          <input type="file" accept="image/*,audio/*,.pdf,.txt" multiple className="hidden" onChange={onAddAttachments} />
        </label>
        <button
          onClick={audioCaptureStatus === 'recording' ? onStopAudioCapture : onStartAudioCapture}
          disabled={serializingMedia && audioCaptureStatus !== 'recording'}
          className={`inline-flex items-center gap-2 rounded-[12px] px-4 py-[11px] text-[14px] font-medium transition-colors disabled:opacity-40 ${audioCaptureStatus === 'recording' ? 'bg-[#FF453A]/15 text-[#FF453A]' : 'border border-white/[0.06] bg-white/[0.04] text-white/60'}`}
        >
          {audioCaptureStatus === 'recording' ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          {audioCaptureStatus === 'recording' ? (copy.captureAudioStop || 'Stop audio') : (copy.captureAudioStart || 'Record audio')}
        </button>
        {nativeMobile && (
          <button onClick={onCapturePhoto} disabled={serializingMedia} className="inline-flex items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[14px] text-white/60 disabled:opacity-40">
            <Camera className="h-4 w-4" />
            {copy.capturePhoto || copy.attachments}
          </button>
        )}
      </div>
      {attachments.length > 0 && (
        <div className="rounded-[12px] border border-white/[0.06] bg-white/[0.03]">
          {attachments.map((item, idx) => (
            <div key={item.media_id} className={`flex items-center justify-between gap-2 px-4 py-[10px] text-[13px] ${idx < attachments.length - 1 ? 'border-b border-white/[0.04]' : ''}`}>
              <span className="truncate text-white/60">{item.name}</span>
              <span className="text-white/25">{formatBytes(item.size)}</span>
            </div>
          ))}
        </div>
      )}
      {validationMissing.length > 0 && (
        <div className="rounded-[12px] border border-[#FF9F0A]/20 bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FFD60A]">
          {isZh
            ? `请先完成：${validationMissing.join('、')}`
            : `Complete first: ${validationMissing.join(', ')}`}
        </div>
      )}
      <button
        data-testid="obs-submit"
        onClick={onSaveObservation}
        disabled={!currentProjectId || (protocolDefinition.requiresAsset && !selectedRoute) || validationMissing.length > 0}
        className="inline-flex w-full items-center justify-center gap-2 rounded-[14px] bg-[#30D158] px-4 py-[13px] text-[16px] font-semibold text-white transition-colors active:bg-[#30D158]/80 disabled:opacity-40"
      >
        <Save className="h-[18px] w-[18px]" />
        {copy.saveObservation}
      </button>
    </div>
  )
}
