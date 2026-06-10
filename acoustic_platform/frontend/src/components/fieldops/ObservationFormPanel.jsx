import React from 'react'
import { Camera, Mic, Save, Square, Upload } from 'lucide-react'
import { formatBytes } from '../../lib/surveyOffline'

export default function ObservationFormPanel({
  copy,
  protocolDefinition,
  protocolState,
  observationForm,
  attachments,
  speciesSuggestions,
  taxonomyCatalog,
  availableTaxaOptions,
  selectedRoute,
  routeObservations,
  currentProjectId,
  nativeMobile,
  serializingMedia,
  audioCaptureStatus,
  onSetObservationForm,
  onProtocolRecordFieldChange,
  onSaveObservation,
  onAddAttachments,
  onStartAudioCapture,
  onStopAudioCapture,
  onCapturePhoto,
}) {
  return (
    <div className="section-shell space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{copy.observation}</h3>
        <span className="text-xs text-gray-400">{routeObservations.length}</span>
      </div>
      <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-xs text-cyan-100">
        {selectedRoute
          ? `${protocolDefinition.assetLabel}: ${selectedRoute.name}`
          : protocolDefinition.assetHint}
      </div>
      <input
        list="field-species-options"
        value={observationForm.species_text}
        onChange={(event) => onSetObservationForm((current) => ({ ...current, species_text: event.target.value }))}
        placeholder={copy.speciesPlaceholder}
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
      />
      <datalist id="field-species-options">
        {(speciesSuggestions.length > 0 ? speciesSuggestions : taxonomyCatalog).slice(0, 400).map((item, index) => (
          <option
            key={`${item.scientific || item.scientific_name || index}`}
            value={item.chinese || item.chinese_name || item.scientific || item.scientific_name || ''}
          >
            {item.scientific || item.scientific_name || ''}
          </option>
        ))}
      </datalist>
      <div className="grid gap-2 sm:grid-cols-2">
        <select
          value={observationForm.taxon_group}
          onChange={(event) => onSetObservationForm((current) => ({ ...current, taxon_group: event.target.value }))}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          {availableTaxaOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <select
          value={observationForm.evidence_type}
          onChange={(event) => onSetObservationForm((current) => ({ ...current, evidence_type: event.target.value }))}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
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
          onChange={(event) => onSetObservationForm((current) => ({ ...current, count: event.target.value }))}
          placeholder={copy.count}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <input
          value={observationForm.observer}
          onChange={(event) => onSetObservationForm((current) => ({ ...current, observer: event.target.value }))}
          placeholder={copy.observer}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={observationForm.confidence}
          onChange={(event) => onSetObservationForm((current) => ({ ...current, confidence: event.target.value }))}
          placeholder={copy.confidence}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
      </div>
      <textarea
        value={observationForm.behavior}
        onChange={(event) => onSetObservationForm((current) => ({ ...current, behavior: event.target.value }))}
        placeholder={copy.behavior}
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
      />
      <textarea
        value={observationForm.habitat_notes}
        onChange={(event) => onSetObservationForm((current) => ({ ...current, habitat_notes: event.target.value }))}
        placeholder="Habitat"
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
      />
      <div className="grid gap-2 sm:grid-cols-2">
        {protocolDefinition.recordFields.map((field) => (
          <label key={field.key} className="space-y-1 text-xs text-gray-400">
            <span className="block">{field.label}</span>
            <input
              type={field.type || 'text'}
              value={protocolState.record[field.key] || ''}
              onChange={(event) => onProtocolRecordFieldChange(field.key, event.target.value)}
              placeholder={field.placeholder || field.label}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
            />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-300">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={observationForm.unknown_taxon} onChange={(event) => onSetObservationForm((current) => ({ ...current, unknown_taxon: event.target.checked }))} />
          {copy.unknownTaxon}
        </label>
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={observationForm.trace_only} onChange={(event) => onSetObservationForm((current) => ({ ...current, trace_only: event.target.checked }))} />
          {copy.traceOnly}
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
          <Upload className="h-4 w-4" />
          {serializingMedia ? `${copy.attachments}...` : copy.attachments}
          <input type="file" accept="image/*,audio/*,.pdf,.txt" multiple className="hidden" onChange={onAddAttachments} />
        </label>
        <button
          onClick={audioCaptureStatus === 'recording' ? onStopAudioCapture : onStartAudioCapture}
          disabled={serializingMedia && audioCaptureStatus !== 'recording'}
          className={`inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-white disabled:opacity-50 ${audioCaptureStatus === 'recording' ? 'bg-red-500/20' : 'bg-white/5'}`}
        >
          {audioCaptureStatus === 'recording' ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          {audioCaptureStatus === 'recording' ? (copy.captureAudioStop || 'Stop audio') : (copy.captureAudioStart || 'Record audio')}
        </button>
        {nativeMobile && (
          <button onClick={onCapturePhoto} disabled={serializingMedia} className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white disabled:opacity-50">
            <Camera className="h-4 w-4" />
            {copy.capturePhoto || copy.attachments}
          </button>
        )}
      </div>
      {attachments.length > 0 && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-gray-300">
          {attachments.map((item) => (
            <div key={item.media_id} className="flex items-center justify-between gap-2 py-1">
              <span className="truncate">{item.name}</span>
              <span className="text-gray-500">{formatBytes(item.size)}</span>
            </div>
          ))}
        </div>
      )}
      <button
        onClick={onSaveObservation}
        disabled={!currentProjectId || (protocolDefinition.requiresAsset && !selectedRoute)}
        className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        <Save className="h-4 w-4" />
        {copy.saveObservation}
      </button>
    </div>
  )
}
