import { useEffect, useMemo, useState } from 'react'
import {
  PROTOCOL_OPTIONS,
  createProtocolState,
  deriveVertebrateSubmoduleId,
  getProtocolDefinition,
  getVertebrateSubmoduleById,
  resolveProtocolSelection,
} from '../components/fieldops/protocolEngine'
import { EXPORT_JURISDICTIONS, toArray } from '../components/fieldops/fieldOpsUtils'
import { loadSurveyState, normalizeJurisdiction } from '../lib/surveyOffline'

/**
 * Protocol selection hook: owns protocolState, computes protocol-derived
 * values, manages protocol sync effects, and exposes selection handlers.
 *
 * Extracted from FieldOpsTab.jsx — protocol selection/switching logic,
 * 6 useEffects, 5 useMemos, 5 handler functions.
 */
export default function useProtocolSelection({
  surveyState,
  setSurveyState,
  observationForm,
  setObservationForm,
  protocolCatalog,
  activeModule,
  onSelectModule,
  exportJurisdiction,
  setExportJurisdiction,
}) {
  // ── Protocol state ──

  const [protocolState, setProtocolState] = useState(() => {
    const storedSurveyState = loadSurveyState()
    const seededSelection = resolveProtocolSelection(
      storedSurveyState.activeProgram || activeModule,
      storedSurveyState.activeProtocol || '',
    )
    return createProtocolState(seededSelection.id)
  })

  // ── Derived values ──

  const currentProgram = protocolState.program

  const activeVertebrateSubmoduleId = useMemo(
    () => (
      currentProgram === 'terrestrial_vertebrates'
        ? deriveVertebrateSubmoduleId(
            surveyState.activeVertebrateSubmodule,
            observationForm.taxon_group,
            protocolState.protocol,
          )
        : ''
    ),
    [currentProgram, observationForm.taxon_group, protocolState.protocol, surveyState.activeVertebrateSubmodule],
  )

  const activeVertebrateSubmodule = useMemo(
    () => (
      currentProgram === 'terrestrial_vertebrates'
        ? getVertebrateSubmoduleById(activeVertebrateSubmoduleId)
        : null
    ),
    [activeVertebrateSubmoduleId, currentProgram],
  )

  const visibleProtocols = useMemo(
    () => protocolCatalog.filter((item) => (
      item.program === currentProgram
      && (
        currentProgram !== 'terrestrial_vertebrates'
        || toArray(item.vertebrateSubmodules).length === 0
        || toArray(item.vertebrateSubmodules).includes(activeVertebrateSubmoduleId)
      )
    )),
    [activeVertebrateSubmoduleId, currentProgram, protocolCatalog],
  )

  const protocolDefinition = useMemo(
    () => getProtocolDefinition(protocolState.protocol, protocolCatalog),
    [protocolCatalog, protocolState.protocol],
  )

  const activeObservationTaxonGroups = useMemo(
    () => (
      currentProgram === 'terrestrial_vertebrates'
        ? [activeVertebrateSubmodule?.taxonGroup].filter(Boolean)
        : toArray(protocolDefinition.allowedTaxonGroups).filter(Boolean)
    ),
    [activeVertebrateSubmodule?.taxonGroup, currentProgram, protocolDefinition.allowedTaxonGroups],
  )

  const activeTaxonomySearchGroup = activeObservationTaxonGroups[0] || protocolDefinition.defaultTaxonGroup || ''

  // ── Sync effects ──

  // Restore stored protocol selection from surveyState on mount / change
  useEffect(() => {
    const storedSelection = resolveProtocolSelection(
      surveyState.activeProgram || activeModule,
      surveyState.activeProtocol || '',
      protocolCatalog,
    )
    if (storedSelection.id !== protocolDefinition.id || storedSelection.program !== protocolDefinition.program) {
      setProtocolState(createProtocolState(storedSelection.id, protocolCatalog))
      setObservationForm((current) => ({
        ...current,
        taxon_group: storedSelection.defaultTaxonGroup,
        evidence_type: storedSelection.defaultEvidenceType,
      }))
    }
    const normalizedStoredJurisdiction = normalizeJurisdiction(surveyState.activeJurisdiction, EXPORT_JURISDICTIONS[0].id)
    if (normalizedStoredJurisdiction !== exportJurisdiction) {
      setExportJurisdiction(normalizedStoredJurisdiction)
    }
    if (onSelectModule && storedSelection.program !== activeModule) {
      onSelectModule(storedSelection.program)
    }
  }, [
    surveyState.activeProgram,
    surveyState.activeProtocol,
    surveyState.activeJurisdiction,
    activeModule,
    protocolCatalog,
    protocolDefinition.id,
    protocolDefinition.program,
    exportJurisdiction,
    onSelectModule,
  ])

  // Seed protocol from activeModule prop
  useEffect(() => {
    const seededProtocol = protocolCatalog.find((item) => item.program === activeModule)?.id
    if (!seededProtocol) return
    if (protocolDefinition.program === activeModule) return
    const nextProtocol = getProtocolDefinition(seededProtocol, protocolCatalog)
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    setObservationForm((current) => ({
      ...current,
      taxon_group: nextProtocol.defaultTaxonGroup,
      evidence_type: nextProtocol.defaultEvidenceType,
    }))
  }, [activeModule, protocolCatalog, protocolDefinition.program])

  // Persist protocol/jurisdiction into surveyState
  useEffect(() => {
    setSurveyState((current) => {
      const normalizedCurrentJurisdiction = normalizeJurisdiction(current.activeJurisdiction, EXPORT_JURISDICTIONS[0].id)
      if (
        current.activeProgram === protocolDefinition.program
        && current.activeProtocol === protocolDefinition.id
        && normalizedCurrentJurisdiction === exportJurisdiction
      ) {
        return current
      }
      return {
        ...current,
        activeProgram: protocolDefinition.program,
        activeProtocol: protocolDefinition.id,
        activeJurisdiction: exportJurisdiction,
      }
    })
  }, [protocolDefinition.program, protocolDefinition.id, exportJurisdiction])

  // Sync taxon group / evidence type when protocol changes
  useEffect(() => {
    setObservationForm((current) => ({
      ...current,
      taxon_group: activeTaxonomySearchGroup || protocolDefinition.defaultTaxonGroup,
      evidence_type: current.evidence_type === '' ? protocolDefinition.defaultEvidenceType : current.evidence_type,
    }))
  }, [activeTaxonomySearchGroup, protocolDefinition.defaultEvidenceType, protocolDefinition.defaultTaxonGroup])

  // Sync vertebrate submodule into surveyState
  useEffect(() => {
    if (currentProgram !== 'terrestrial_vertebrates') return
    if (surveyState.activeVertebrateSubmodule === activeVertebrateSubmoduleId) return
    setSurveyState((current) => ({ ...current, activeVertebrateSubmodule: activeVertebrateSubmoduleId }))
  }, [activeVertebrateSubmoduleId, currentProgram, surveyState.activeVertebrateSubmodule])

  // Fallback when visible protocols no longer include current selection
  useEffect(() => {
    if (visibleProtocols.some((item) => item.id === protocolDefinition.id)) return
    const nextProtocol = visibleProtocols[0]
    if (!nextProtocol) return
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    setObservationForm((current) => ({
      ...current,
      taxon_group: activeTaxonomySearchGroup || nextProtocol.defaultTaxonGroup,
      evidence_type: nextProtocol.defaultEvidenceType,
    }))
  }, [activeTaxonomySearchGroup, protocolCatalog, protocolDefinition.id, visibleProtocols])

  // ── Selection handlers ──

  function handleSelectProgram(programId) {
    const nextSubmoduleId = programId === 'terrestrial_vertebrates'
      ? deriveVertebrateSubmoduleId(surveyState.activeVertebrateSubmodule, observationForm.taxon_group, protocolState.protocol)
      : ''
    const nextProtocol = (
      protocolCatalog.find((item) => (
        item.program === programId
        && (
          programId !== 'terrestrial_vertebrates'
          || toArray(item.vertebrateSubmodules).length === 0
          || toArray(item.vertebrateSubmodules).includes(nextSubmoduleId)
        )
      ))
      || protocolCatalog.find((item) => item.program === programId)
      || protocolCatalog[0]
      || PROTOCOL_OPTIONS[0]
    )
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    onSelectModule?.(programId)
    setObservationForm((current) => ({
      ...current,
      taxon_group: programId === 'terrestrial_vertebrates'
        ? (getVertebrateSubmoduleById(nextSubmoduleId).taxonGroup || nextProtocol.defaultTaxonGroup)
        : nextProtocol.defaultTaxonGroup,
      evidence_type: nextProtocol.defaultEvidenceType,
    }))
    setSurveyState((current) => ({
      ...current,
      activeVertebrateSubmodule: programId === 'terrestrial_vertebrates' ? nextSubmoduleId : current.activeVertebrateSubmodule,
    }))
  }

  function handleSelectProtocol(protocolId) {
    const nextProtocol = getProtocolDefinition(protocolId, protocolCatalog)
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    setObservationForm((current) => ({
      ...current,
      taxon_group: currentProgram === 'terrestrial_vertebrates'
        ? (activeVertebrateSubmodule?.taxonGroup || nextProtocol.defaultTaxonGroup)
        : nextProtocol.defaultTaxonGroup,
      evidence_type: nextProtocol.defaultEvidenceType,
    }))
  }

  function handleSelectVertebrateSubmodule(submoduleId) {
    const nextSubmodule = getVertebrateSubmoduleById(submoduleId)
    const nextProtocol = (
      protocolCatalog.find((item) => (
        item.program === 'terrestrial_vertebrates'
        && (
          toArray(item.vertebrateSubmodules).length === 0
          || toArray(item.vertebrateSubmodules).includes(nextSubmodule.id)
        )
      ))
      || protocolDefinition
    )

    setSurveyState((current) => ({ ...current, activeVertebrateSubmodule: nextSubmodule.id }))
    if (nextProtocol?.id && nextProtocol.id !== protocolDefinition.id) {
      setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    }
    setObservationForm((current) => ({
      ...current,
      taxon_group: nextSubmodule.taxonGroup,
      evidence_type: nextProtocol?.defaultEvidenceType || current.evidence_type,
    }))
  }

  function handleProtocolEventFieldChange(fieldKey, value) {
    setProtocolState((current) => ({
      ...current,
      event: {
        ...current.event,
        [fieldKey]: value,
      },
    }))
  }

  function handleProtocolRecordFieldChange(fieldKey, value) {
    setProtocolState((current) => ({
      ...current,
      record: {
        ...current.record,
        [fieldKey]: value,
      },
    }))
  }

  return {
    protocolState,
    setProtocolState,
    protocolDefinition,
    currentProgram,
    activeVertebrateSubmoduleId,
    activeVertebrateSubmodule,
    visibleProtocols,
    activeObservationTaxonGroups,
    activeTaxonomySearchGroup,
    handleSelectProgram,
    handleSelectProtocol,
    handleSelectVertebrateSubmodule,
    handleProtocolEventFieldChange,
    handleProtocolRecordFieldChange,
  }
}
