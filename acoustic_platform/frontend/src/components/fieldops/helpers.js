import { PROTOCOL_OPTIONS, VERTEBRATE_SUBMODULES } from './constants'

export function pickLocale(i18n) {
  return i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
}

export function humanizeFieldKey(key = '') {
  return String(key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (token) => token.toUpperCase())
}

export function uniqueNormalizedStrings(values = []) {
  return Array.from(new Set(
    values
      .flatMap((value) => (Array.isArray(value) ? value : [value]))
      .map((value) => String(value || '').trim())
      .filter(Boolean),
  ))
}

export function inferProtocolDefaultTaxonGroup(protocolId = '', fallback = '') {
  if (fallback) return fallback
  if (protocolId.startsWith('bird_')) return 'birds'
  if (protocolId === 'mammal_trap_net') return 'mammals'
  if (protocolId === 'herp_infrared_camera') return 'amphibians'
  if (protocolId.startsWith('plant_')) return 'plants'
  if (protocolId === 'insect_transect') return 'insects'
  return ''
}

export function inferProtocolDefaultEvidenceType(protocolId = '', fallback = 'visual') {
  if (fallback) return fallback
  if (protocolId === 'bird_point_count') return 'audio'
  if (protocolId === 'mammal_trap_net') return 'trace'
  return 'visual'
}

export function getVertebrateSubmoduleById(submoduleId = '') {
  return VERTEBRATE_SUBMODULES.find((item) => item.id === submoduleId) || VERTEBRATE_SUBMODULES[0]
}

export function resolveVertebrateSubmodule(submoduleId = '', taxonGroup = '', protocolId = '') {
  if (VERTEBRATE_SUBMODULES.some((item) => item.id === submoduleId)) return submoduleId
  if (VERTEBRATE_SUBMODULES.some((item) => item.id === taxonGroup)) return taxonGroup
  if (protocolId.startsWith('bird_')) return 'birds'
  if (protocolId === 'mammal_trap_net') return 'mammals'
  if (protocolId === 'herp_infrared_camera') {
    if (taxonGroup === 'reptiles') return 'reptiles'
    if (taxonGroup === 'amphibians') return 'amphibians'
  }
  return ''
}

export function deriveVertebrateSubmoduleId(submoduleId = '', taxonGroup = '', protocolId = '') {
  return resolveVertebrateSubmodule(submoduleId, taxonGroup, protocolId) || 'birds'
}

export function inferFieldType(fieldKey = '', fallbackField = null) {
  if (fallbackField?.type) return fallbackField.type
  if (/(^|_)(count|index|percent|radius|distance|length|duration|width|height|mass|area|days|nights|min|hour|hours|h|m|cm|mm|g|kg|c|s)$/.test(fieldKey)) {
    return 'number'
  }
  return 'text'
}

export function toArray(value) {
  return Array.isArray(value) ? value : []
}

export function getRemoteFieldKeys(fieldGroups = {}) {
  return [
    ...toArray(fieldGroups.required),
    ...toArray(fieldGroups.optional),
    ...toArray(fieldGroups.effort),
  ]
}

export function buildProtocolFieldDefinitions(fieldGroups = {}, fallbackFields = [], { includeFallbackExtras = true } = {}) {
  const fallbackByKey = new Map(toArray(fallbackFields).map((field) => [field.key, field]))
  const requiredKeys = new Set(toArray(fieldGroups.required))
  const orderedKeys = includeFallbackExtras
    ? [
        ...toArray(fallbackFields).map((field) => field.key),
        ...getRemoteFieldKeys(fieldGroups),
      ]
    : getRemoteFieldKeys(fieldGroups)

  const seenKeys = new Set()
  const fields = []

  orderedKeys.forEach((fieldKey) => {
    if (!fieldKey || seenKeys.has(fieldKey)) return
    const fallbackField = fallbackByKey.get(fieldKey) || null
    fields.push({
      key: fieldKey,
      label: fallbackField?.label || humanizeFieldKey(fieldKey),
      type: inferFieldType(fieldKey, fallbackField),
      placeholder: fallbackField?.placeholder || humanizeFieldKey(fieldKey),
      required: requiredKeys.has(fieldKey) || Boolean(fallbackField?.required && !requiredKeys.size),
    })
    seenKeys.add(fieldKey)
  })

  if (fields.length === 0) {
    return toArray(fallbackFields).map((field) => ({ ...field }))
  }

  return fields
}

export function normalizeProtocolDefinition(protocolDefinition = {}, fallbackDefinition = null) {
  const protocolId = protocolDefinition.protocol_id || protocolDefinition.protocol || fallbackDefinition?.id || ''
  const program = protocolDefinition.program || fallbackDefinition?.program || ''
  const label = protocolDefinition.display_name || protocolDefinition.label || fallbackDefinition?.label || protocolId
  const designAssetTypes = toArray(protocolDefinition.design_asset_types)
  const trackPolicy = String(protocolDefinition.track_policy || '').trim().toLowerCase()
  const inferredSupportsTrack = trackPolicy
    ? !['none', 'disabled', 'unsupported', 'not_supported'].includes(trackPolicy)
    : undefined
  const fallbackVertebrateSubmodules = toArray(fallbackDefinition?.vertebrateSubmodules)
  const fallbackAllowedTaxonGroups = toArray(fallbackDefinition?.allowedTaxonGroups)
  const defaultTaxonGroup = inferProtocolDefaultTaxonGroup(protocolId, fallbackDefinition?.defaultTaxonGroup || '')

  return {
    ...fallbackDefinition,
    ...protocolDefinition,
    id: protocolId,
    protocol: protocolId,
    protocol_id: protocolId,
    program,
    label,
    display_name: label,
    shellLabel: fallbackDefinition?.shellLabel || label,
    description: protocolDefinition.description || fallbackDefinition?.description || '',
    assetLabel: fallbackDefinition?.assetLabel || 'Design asset',
    assetHint: fallbackDefinition?.assetHint || 'Select the matching design asset for this protocol.',
    requiresAsset: typeof protocolDefinition.requires_asset === 'boolean'
      ? protocolDefinition.requires_asset
      : (fallbackDefinition?.requiresAsset ?? designAssetTypes.length > 0),
    supportsTrack: typeof protocolDefinition.supports_track === 'boolean'
      ? protocolDefinition.supports_track
      : (typeof inferredSupportsTrack === 'boolean' ? inferredSupportsTrack : Boolean(fallbackDefinition?.supportsTrack)),
    defaultTaxonGroup,
    allowedTaxonGroups: fallbackAllowedTaxonGroups.length > 0 ? fallbackAllowedTaxonGroups : [defaultTaxonGroup].filter(Boolean),
    defaultEvidenceType: inferProtocolDefaultEvidenceType(protocolId, fallbackDefinition?.defaultEvidenceType || ''),
    vertebrateSubmodules: fallbackVertebrateSubmodules.length > 0 ? fallbackVertebrateSubmodules : [],
    jurisdictions: toArray(protocolDefinition.jurisdictions),
    design_asset_types: designAssetTypes,
    eventFieldGroups: protocolDefinition.event_fields || { required: toArray(protocolDefinition.required_event_fields) },
    recordFieldGroups: protocolDefinition.record_fields || { required: toArray(protocolDefinition.required_record_fields) },
    eventFields: buildProtocolFieldDefinitions(
      protocolDefinition.event_fields || { required: toArray(protocolDefinition.required_event_fields) },
      fallbackDefinition?.eventFields,
      { includeFallbackExtras: !protocolDefinition.has_structured_event_fields },
    ),
    recordFields: buildProtocolFieldDefinitions(
      protocolDefinition.record_fields || { required: toArray(protocolDefinition.required_record_fields) },
      fallbackDefinition?.recordFields,
      { includeFallbackExtras: !protocolDefinition.has_structured_record_fields },
    ),
  }
}

export function buildProtocolCatalog(protocolDefinitions = []) {
  const remoteDefinitions = toArray(protocolDefinitions)
  const remoteById = new Map(
    remoteDefinitions
      .map((definition) => [definition.protocol_id || definition.protocol || '', definition])
      .filter(([protocolId]) => Boolean(protocolId)),
  )

  return PROTOCOL_OPTIONS.map((fallbackDefinition) => (
    normalizeProtocolDefinition(remoteById.get(fallbackDefinition.id) || {}, fallbackDefinition)
  ))
}

export function mergeTaxonomyCatalogEntries(...catalogs) {
  const merged = new Map()
  catalogs.forEach((catalog) => {
    toArray(catalog).forEach((item) => {
      if (!item) return
      const key = item.internal_taxon_id || item.taxon_id || item.species_id || item.scientific_name || item.display_name
      if (!key) return
      merged.set(key, { ...(merged.get(key) || {}), ...item })
    })
  })
  return Array.from(merged.values())
}

export function findSpeciesMatch(speciesCatalog, rawValue) {
  const query = String(rawValue || '').trim().toLowerCase()
  if (!query) return null
  return (speciesCatalog || []).find((item) => {
    const names = uniqueNormalizedStrings([
      item?.scientific,
      item?.scientific_name,
      item?.english,
      item?.english_name,
      item?.chinese,
      item?.chinese_name,
      item?.display_name,
      item?.chinese_names,
      item?.english_names,
      item?.scientific_names,
      item?.synonyms,
      item?.names?.zh_cn,
      item?.names?.zh_tw,
      item?.names?.en,
      item?.names?.scientific,
      item?.names?.synonyms,
    ])
    return names.some((name) => String(name || '').trim().toLowerCase() === query)
  }) || null
}

export function createEmptyTransectSession(observer = '') {
  return {
    route_id: '',
    observer,
    weather: '',
    notes: '',
    started_at: '',
    ended_at: '',
  }
}

export function buildProtocolFieldState(fields = []) {
  return fields.reduce((accumulator, field) => {
    accumulator[field.key] = ''
    return accumulator
  }, {})
}

export function getProtocolDefinition(protocolId, protocolCatalog = PROTOCOL_OPTIONS) {
  return toArray(protocolCatalog).find((item) => item.id === protocolId) || toArray(protocolCatalog)[0] || PROTOCOL_OPTIONS[0]
}

export function createProtocolState(protocolId = PROTOCOL_OPTIONS[0].id, protocolCatalog = PROTOCOL_OPTIONS) {
  const definition = getProtocolDefinition(protocolId, protocolCatalog)
  return {
    program: definition.program,
    protocol: definition.id,
    event: buildProtocolFieldState(definition.eventFields),
    record: buildProtocolFieldState(definition.recordFields),
  }
}

export function resolveProtocolSelection(programId, protocolId = '', protocolCatalog = PROTOCOL_OPTIONS) {
  const catalog = toArray(protocolCatalog).length > 0 ? protocolCatalog : PROTOCOL_OPTIONS
  const preferred = catalog.find((item) => item.id === protocolId && item.program === programId)
  if (preferred) return preferred
  return catalog.find((item) => item.program === programId) || catalog[0] || PROTOCOL_OPTIONS[0]
}

export function normalizeProtocolFieldValues(fields = [], values = {}) {
  return fields.reduce((accumulator, field) => {
    const rawValue = values[field.key]
    if (rawValue == null || rawValue === '') return accumulator
    if (field.type === 'number') {
      const numeric = Number(rawValue)
      accumulator[field.key] = Number.isFinite(numeric) ? numeric : rawValue
      return accumulator
    }
    accumulator[field.key] = rawValue
    return accumulator
  }, {})
}

export function matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId = '') {
  if (protocolDefinition?.program !== 'terrestrial_vertebrates' || !activeSubmoduleId) return true
  const supportedSubmodules = toArray(record?.submodules)
  if (supportedSubmodules.length > 0) {
    return supportedSubmodules.includes(activeSubmoduleId)
  }
  const recordProtocol = record?.extra?.protocol || record?.protocol || ''
  const recordSubmodule = resolveVertebrateSubmodule(
    record?.extra?.submodule || record?.filters?.submodule || record?.submodule || '',
    record?.taxon_group || '',
    recordProtocol,
  )
  return !recordSubmodule || recordSubmodule === activeSubmoduleId
}

export function matchesProtocolObservation(record, protocolDefinition, activeSubmoduleId = '') {
  if (!record || !protocolDefinition) return false
  const recordProtocol = record?.extra?.protocol || record?.protocol || ''
  if (recordProtocol) {
    if (recordProtocol !== protocolDefinition.id) return false
    return matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
  }
  if (protocolDefinition.defaultTaxonGroup === 'insects') return record.taxon_group === 'insects'
  if (protocolDefinition.program === 'plants') return record.taxon_group === 'plants'
  if (protocolDefinition.id.startsWith('bird_')) return record.taxon_group === 'birds'
  if (protocolDefinition.id === 'mammal_trap_net') return record.taxon_group === 'mammals'
  if (protocolDefinition.id === 'herp_infrared_camera') {
    return ['amphibians', 'reptiles'].includes(record.taxon_group) && matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
  }
  return true
}

export function matchesProtocolTrack(record, protocolDefinition, activeSubmoduleId = '') {
  if (!record || !protocolDefinition) return false
  const recordProtocol = record?.extra?.protocol || record?.protocol || ''
  if (recordProtocol) {
    if (recordProtocol !== protocolDefinition.id) return false
    return matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
  }
  return matchesActiveSubmodule(record, protocolDefinition, activeSubmoduleId)
}

export function getMatchingTaxonomyPackages(packages, protocolDefinition, jurisdiction, activeSubmoduleId = '') {
  return toArray(packages)
    .filter((item) => (item.program || '') === protocolDefinition.program)
    .filter((item) => (item.jurisdiction || '') === jurisdiction)
    .filter((item) => {
      const supportedProtocols = toArray(item.protocols)
      return supportedProtocols.length === 0 || supportedProtocols.includes(protocolDefinition.id)
    })
    .filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeSubmoduleId))
}

export function downloadBlobFile(blob, filename = 'download.bin') {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function formatReportDescriptor(value, fallback = '--') {
  if (value == null || value === '') return fallback
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    const items = value
      .map((item) => {
        if (typeof item === 'string') return item
        return item?.name || item?.observer || item?.observer_name || item?.full_name || ''
      })
      .filter(Boolean)
    return items.length > 0 ? items.join(', ') : fallback
  }
  if (typeof value === 'object') {
    const summary = Object.entries(value)
      .filter(([, entryValue]) => entryValue != null && entryValue !== '')
      .slice(0, 3)
      .map(([key, entryValue]) => `${key.replace(/_/g, ' ')}: ${entryValue}`)
      .join(' | ')
    return summary || fallback
  }
  return String(value)
}

export function getSpeciesDisplayName(record = {}) {
  return (
    record.chinese_name
    || record.chinese
    || record.common_name
    || record.english_name
    || record.english
    || record.scientific_name
    || record.scientific
    || record.species_name
    || 'Unknown species'
  )
}

export function getSpeciesSecondaryName(record = {}) {
  const primary = getSpeciesDisplayName(record)
  const candidates = [
    record.scientific_name,
    record.scientific,
    record.english_name,
    record.english,
    record.common_name,
  ].filter(Boolean)
  return candidates.find((item) => item !== primary) || ''
}

export function splitObserverNames(...values) {
  return Array.from(new Set(values
    .flatMap((value) => String(value || '').split(/[;,]/))
    .map((item) => item.trim())
    .filter(Boolean)))
}

export function getRequiredFieldLabels(fields = [], values = {}) {
  return fields
    .filter((field) => field.required)
    .filter((field) => values[field.key] == null || values[field.key] === '')
    .map((field) => field.label)
}

export function buildPreviewEntries(record = {}) {
  return Object.entries(record || {})
    .filter(([, value]) => value != null && value !== '' && !(Array.isArray(value) && value.length === 0))
}

export function formatPreviewValue(value) {
  if (value == null || value === '') return '--'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function normalizeSensitivityValue(value) {
  const raw = String(value || '').trim().toLowerCase()
  if (!raw) return ''
  if (['public', 'open', 'none', 'normal', 'no'].includes(raw)) return 'public'
  if (['masked', 'mask', 'sensitive', 'restricted', 'private', 'protected', 'high'].includes(raw)) return 'masked'
  return raw
}

export function buildMaskPreview(record = {}, matchedTaxon = null, jurisdiction = 'mainland_china') {
  const jurisdictionEntry = matchedTaxon?.jurisdictions?.[jurisdiction] || {}
  const flags = [
    record?.sensitivity,
    record?.extra?.sensitivity,
    record?.extra?.export_mask,
    record?.extra?.masking,
    jurisdictionEntry?.sensitivity,
    jurisdictionEntry?.coordinate_masking,
    jurisdictionEntry?.protected_status,
    jurisdictionEntry?.red_list_status,
  ].filter((value) => value != null && value !== '')

  const normalized = flags.map(normalizeSensitivityValue).find(Boolean) || ''
  const masked = normalized === 'masked'
    || Boolean(jurisdictionEntry?.coordinate_masking)
    || Boolean(jurisdictionEntry?.sensitive)
    || Boolean(jurisdictionEntry?.protected)
    || Boolean(jurisdictionEntry?.national_protection)

  if (masked) {
    return {
      masked: true,
      label: 'Masked in export',
      note: flags.map(formatPreviewValue).join(' | ') || 'Protected or sensitive taxon',
    }
  }
  if (normalized === 'public') {
    return {
      masked: false,
      label: 'Public coordinates',
      note: 'No masking flag found in the local record or taxonomy seed.',
    }
  }
  return {
    masked: false,
    label: flags.length > 0 ? 'Review masking' : 'No local masking flag',
    note: flags.length > 0
      ? flags.map(formatPreviewValue).join(' | ')
      : 'The current frontend preview can only use locally available sensitivity fields.',
  }
}

export function formatPreviewKey(key = '') {
  return String(key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (token) => token.toUpperCase())
}

export function sortByRecent(left, right) {
  const leftTime = Date.parse(left?.updated_at || left?.created_at || left?.started_at || left?.observed_at || '') || 0
  const rightTime = Date.parse(right?.updated_at || right?.created_at || right?.started_at || right?.observed_at || '') || 0
  return rightTime - leftTime
}

export function getTaxonomyGateIssueLabels(status) {
  const issues = []
  if (!status?.activePackage) issues.push('no taxonomy package is pinned')
  if (status?.activePackage && status.hasRequiredGateMetadata === false) issues.push('release metadata is incomplete')
  if (status?.hasCurrentReleaseIssue) issues.push('release metadata is not current')
  if (status?.hasChecksumMismatch) issues.push('checksum metadata does not match')
  if (status?.hasParityIssue) issues.push('count parity failed')
  if (status?.hasReviewIssue) issues.push('review status is not approved')
  return issues
}

export function buildTaxonomyGateWarningMessage(status) {
  if (!status?.isBlocked) return ''
  const packageLabel = status.activePackage?.label
    || status.activePackage?.package_id
    || status.activePackage?.taxonomy_release_id
    || 'The active taxonomy package'
  const issues = getTaxonomyGateIssueLabels(status)
  if (issues.length === 0) return ''
  return `${packageLabel} is blocked for release export because ${issues.join(', ')}. Pull the latest metadata or refresh the cached package before exporting.`
}

export function buildTaxonomyMetricNote(status) {
  if (!status?.activePackage) return 'Pull survey metadata to pin an offline package'
  const issues = getTaxonomyGateIssueLabels(status)
  if (issues.length > 0) return issues.join(' | ')
  return status.activePackage.package_id || status.activePackage.taxonomy_release_id || 'Cached package ready'
}

export function buildTaxonomyGateBlockingMessage(status, protocolDefinition, jurisdictionLabel) {
  const issues = getTaxonomyGateIssueLabels(status)
  if (issues.length === 0) return ''
  const packageLabel = status.activePackage?.label
    || status.activePackage?.package_id
    || status.activePackage?.taxonomy_release_id
    || 'active taxonomy package'
  return `The ${jurisdictionLabel} ${protocolDefinition.label.toLowerCase()} export is blocked because ${packageLabel} has release-gating issues: ${issues.join(', ')}.`
}
