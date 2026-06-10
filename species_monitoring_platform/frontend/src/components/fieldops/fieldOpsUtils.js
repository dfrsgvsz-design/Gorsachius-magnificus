/**
 * Shared utility functions for FieldOps sub-components.
 *
 * Extracted from FieldOpsTab.jsx lines 816-965.
 * These are pure functions with no React dependencies.
 */

export function toArray(value) {
  return Array.isArray(value) ? value : []
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

export const EXPORT_JURISDICTIONS = [
  { id: 'mainland_china', label: 'Mainland China', label_zh: '中国大陆' },
  { id: 'taiwan', label: 'Taiwan', label_zh: '台湾' },
]
