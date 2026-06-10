import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { ChevronDown, Search, X } from 'lucide-react'

/**
 * iOS-style combobox / filterable dropdown.
 *
 * Props:
 *  - value        current value (string)
 *  - onChange      (newValue: string) => void
 *  - options       [{ value, label }] or string[]
 *  - placeholder   input placeholder
 *  - className     extra wrapper class
 *  - allowFreeText if true, user can type values not in options (default: true)
 *  - maxVisible    max dropdown items (default: 8)
 *  - icon          optional leading icon component
 *  - disabled      boolean
 */
export default function ComboField({
  value = '',
  onChange,
  options: rawOptions = [],
  placeholder = '',
  className = '',
  allowFreeText = true,
  maxVisible = 8,
  icon: Icon,
  disabled = false,
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const wrapperRef = useRef(null)
  const inputRef = useRef(null)

  const options = useMemo(() =>
    rawOptions.map((o) => (typeof o === 'string' ? { value: o, label: o } : o)),
    [rawOptions],
  )

  const filtered = useMemo(() => {
    if (!query) return options.slice(0, maxVisible)
    const q = query.toLowerCase()
    return options
      .filter((o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
      .slice(0, maxVisible)
  }, [options, query, maxVisible])

  const displayLabel = useMemo(() => {
    const match = options.find((o) => o.value === value)
    return match ? match.label : value
  }, [options, value])

  const handleSelect = useCallback((val) => {
    onChange(val)
    setOpen(false)
    setQuery('')
  }, [onChange])

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
        setQuery('')
      }
    }
    if (open) document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus()
  }, [open])

  if (options.length === 0) {
    return (
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={`w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white placeholder:text-white/25 focus:border-[#0A84FF]/40 focus:outline-none ${className}`}
      />
    )
  }

  return (
    <div ref={wrapperRef} className={`relative ${className}`}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        className={`flex w-full items-center gap-2 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-left text-[15px] transition-colors focus:border-[#0A84FF]/40 focus:outline-none ${
          open ? 'border-[#0A84FF]/40' : ''
        } ${disabled ? 'opacity-40' : ''}`}
      >
        {Icon && <Icon className="h-4 w-4 shrink-0 text-white/25" />}
        <span className={`min-w-0 flex-1 truncate ${value ? 'text-white' : 'text-white/25'}`}>
          {displayLabel || placeholder}
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-white/25 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-[14px] border border-white/[0.08] bg-[#1c1c1e] shadow-xl shadow-black/40">
          {/* Search input */}
          {options.length > 4 && (
            <div className="flex items-center gap-2 border-b border-white/[0.06] px-3 py-2">
              <Search className="h-3.5 w-3.5 shrink-0 text-white/25" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={placeholder}
                className="min-w-0 flex-1 bg-transparent text-[14px] text-white placeholder:text-white/25 focus:outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && filtered.length > 0) {
                    handleSelect(filtered[0].value)
                  } else if (e.key === 'Enter' && allowFreeText && query) {
                    handleSelect(query)
                  } else if (e.key === 'Escape') {
                    setOpen(false)
                    setQuery('')
                  }
                }}
              />
              {query && (
                <button type="button" onClick={() => setQuery('')} className="text-white/25 hover:text-white/50">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Options list */}
          <div className="max-h-[240px] overflow-y-auto overscroll-contain">
            {filtered.length === 0 && (
              <p className="px-4 py-3 text-center text-[13px] text-white/25">
                {allowFreeText ? '' : '无匹配项'}
              </p>
            )}
            {filtered.map((option, idx) => {
              const isActive = option.value === value
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => handleSelect(option.value)}
                  className={`flex w-full items-center gap-3 px-4 py-[10px] text-left text-[14px] transition-colors active:bg-white/[0.06] ${
                    idx < filtered.length - 1 ? 'border-b border-white/[0.04]' : ''
                  } ${isActive ? 'text-[#0A84FF]' : 'text-white/80'}`}
                >
                  <span className="min-w-0 flex-1 truncate">{option.label}</span>
                  {option.hint && (
                    <span className="shrink-0 text-[12px] text-white/25">{option.hint}</span>
                  )}
                  {isActive && (
                    <span className="shrink-0 text-[12px] text-[#0A84FF]">✓</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Free text entry hint */}
          {allowFreeText && query && !filtered.some((o) => o.value === query) && (
            <button
              type="button"
              onClick={() => handleSelect(query)}
              className="flex w-full items-center gap-2 border-t border-white/[0.06] px-4 py-[10px] text-left text-[13px] text-[#0A84FF] active:bg-white/[0.06]"
            >
              <span>"{query}"</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Species autocomplete — specialized ComboField for taxonomy search.
 *
 * Props:
 *  - value            current species_text
 *  - onChange          (newValue: string) => void
 *  - taxonomyCatalog   full catalog array [{ chinese, chinese_name, scientific, scientific_name, ... }]
 *  - speciesSuggestions filtered suggestions array (same shape)
 *  - placeholder
 *  - locale           'zh' | 'en'
 */
export function SpeciesAutocomplete({
  value = '',
  onChange,
  taxonomyCatalog = [],
  speciesSuggestions = [],
  placeholder = '',
  locale = 'zh',
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const wrapperRef = useRef(null)
  const inputRef = useRef(null)

  const catalog = speciesSuggestions.length > 0 ? speciesSuggestions : taxonomyCatalog

  const filtered = useMemo(() => {
    const q = (query || value || '').toLowerCase().trim()
    if (!q) return catalog.slice(0, 12)
    return catalog
      .filter((sp) => {
        const cn = (sp.chinese || sp.chinese_name || '').toLowerCase()
        const sci = (sp.scientific || sp.scientific_name || '').toLowerCase()
        const en = (sp.english || sp.english_name || '').toLowerCase()
        return cn.includes(q) || sci.includes(q) || en.includes(q)
      })
      .slice(0, 12)
  }, [catalog, query, value])

  const getDisplayName = useCallback((sp) => {
    const cn = sp.chinese || sp.chinese_name || ''
    const sci = sp.scientific || sp.scientific_name || ''
    return locale === 'zh' ? (cn || sci) : (sci || cn)
  }, [locale])

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  return (
    <div ref={wrapperRef} className="relative">
      {/* Input */}
      <div className={`flex items-center gap-2 rounded-[12px] border bg-white/[0.04] px-4 py-[11px] transition-colors ${
        open ? 'border-[#0A84FF]/40' : 'border-white/[0.06]'
      }`}>
        <Search className="h-4 w-4 shrink-0 text-white/25" />
        <input
          data-testid="obs-species-input"
          ref={inputRef}
          value={open ? query : (value || '')}
          onChange={(e) => {
            setQuery(e.target.value)
            if (!open) setOpen(true)
            onChange(e.target.value)
          }}
          onFocus={() => {
            setOpen(true)
            setQuery(value || '')
          }}
          placeholder={placeholder}
          className="min-w-0 flex-1 bg-transparent text-[15px] text-white placeholder:text-white/25 focus:outline-none"
        />
        {value && (
          <button
            type="button"
            onClick={() => {
              onChange('')
              setQuery('')
              inputRef.current?.focus()
            }}
            className="text-white/25 active:text-white/50"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Dropdown */}
      {open && filtered.length > 0 && (
        <div className="absolute left-0 right-0 z-50 mt-1 max-h-[300px] overflow-y-auto overscroll-contain rounded-[14px] border border-white/[0.08] bg-[#1c1c1e] shadow-xl shadow-black/40">
          {filtered.map((sp, idx) => {
            const cn = sp.chinese || sp.chinese_name || ''
            const sci = sp.scientific || sp.scientific_name || ''
            const displayValue = getDisplayName(sp)
            return (
              <button
                key={`${sci}-${idx}`}
                type="button"
                onClick={() => {
                  onChange(displayValue)
                  setQuery('')
                  setOpen(false)
                }}
                className={`flex w-full items-center gap-3 px-4 py-[10px] text-left transition-colors active:bg-white/[0.06] ${
                  idx < filtered.length - 1 ? 'border-b border-white/[0.04]' : ''
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] text-white/90">{cn || sci}</p>
                  {cn && sci && (
                    <p className="truncate text-[12px] italic text-white/30">{sci}</p>
                  )}
                </div>
                {sp.order && (
                  <span className="shrink-0 rounded-full bg-white/[0.04] px-2 py-0.5 text-[11px] text-white/20">
                    {sp.order}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
