import React, { useCallback, useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronUp, Minus, Plus, Search, X } from 'lucide-react'

export default function ChecklistMode({
  locale = 'en',
  species = [],
  onSave,
  onClose,
}) {
  const isZh = locale === 'zh'
  const [counts, setCounts] = useState({})
  const [query, setQuery] = useState('')
  const [expandedGroup, setExpandedGroup] = useState(null)

  const filteredSpecies = useMemo(() => {
    if (!query.trim()) return species
    const q = query.toLowerCase()
    return species.filter((sp) =>
      (sp.scientific_name || '').toLowerCase().includes(q) ||
      (sp.chinese_name || sp.simplified_chinese_name || '').includes(q) ||
      (sp.english_name || sp.english_common_name || '').toLowerCase().includes(q)
    )
  }, [species, query])

  const groupedSpecies = useMemo(() => {
    const groups = {}
    for (const sp of filteredSpecies) {
      const group = sp.taxon_group || sp.order || 'other'
      if (!groups[group]) groups[group] = []
      groups[group].push(sp)
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
  }, [filteredSpecies])

  const handleIncrement = useCallback((id) => {
    setCounts((prev) => ({ ...prev, [id]: (prev[id] || 0) + 1 }))
  }, [])

  const handleDecrement = useCallback((id) => {
    setCounts((prev) => {
      const next = (prev[id] || 0) - 1
      if (next <= 0) {
        const { [id]: _, ...rest } = prev
        return rest
      }
      return { ...prev, [id]: next }
    })
  }, [])

  const handleToggle = useCallback((id) => {
    setCounts((prev) => {
      if (prev[id]) {
        const { [id]: _, ...rest } = prev
        return rest
      }
      return { ...prev, [id]: 1 }
    })
  }, [])

  const totalSpecies = Object.keys(counts).length
  const totalIndividuals = Object.values(counts).reduce((sum, c) => sum + c, 0)

  const handleSave = () => {
    const records = Object.entries(counts).map(([id, count]) => {
      const sp = species.find((s) => (s.internal_taxon_id || s.scientific_name) === id)
      return {
        species_id: id,
        scientific_name: sp?.scientific_name || id,
        chinese_name: sp?.chinese_name || sp?.simplified_chinese_name || '',
        english_name: sp?.english_name || sp?.english_common_name || '',
        count,
      }
    })
    onSave?.(records)
  }

  return (
    <div className="card space-y-0 overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] bg-emerald-500/5 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-white">
            {isZh ? '清单模式' : 'Checklist Mode'}
          </h3>
          <p className="mt-0.5 text-xs text-white/30">
            {isZh
              ? `${totalSpecies} 种 · ${totalIndividuals} 只`
              : `${totalSpecies} species · ${totalIndividuals} individuals`
            }
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleSave} disabled={totalSpecies === 0} className="btn-primary btn-sm disabled:opacity-40">
            <Check className="h-3.5 w-3.5" />
            {isZh ? '保存' : 'Save'}
          </button>
          {onClose && (
            <button onClick={onClose} className="btn-ghost btn-icon">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="border-b border-white/[0.06] px-4 py-2">
        <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2">
          <Search className="h-4 w-4 text-white/25" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={isZh ? '搜索物种...' : 'Search species...'}
            className="flex-1 bg-transparent text-sm text-white placeholder-white/25 outline-none"
          />
          {query && (
            <button onClick={() => setQuery('')} className="text-white/25 hover:text-white/50">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Species list */}
      <div className="max-h-[60vh] overflow-y-auto">
        {groupedSpecies.map(([group, items]) => (
          <div key={group}>
            <button
              onClick={() => setExpandedGroup(expandedGroup === group ? null : group)}
              className="sticky top-0 z-10 flex w-full items-center justify-between border-b border-white/[0.04] bg-[#161b22] px-4 py-2 text-left"
            >
              <span className="text-xs font-semibold uppercase tracking-wider text-white/30">
                {group} ({items.length})
              </span>
              {expandedGroup === group
                ? <ChevronUp className="h-3.5 w-3.5 text-white/20" />
                : <ChevronDown className="h-3.5 w-3.5 text-white/20" />
              }
            </button>
            {(expandedGroup === group || expandedGroup === null) && items.map((sp) => {
              const id = sp.internal_taxon_id || sp.scientific_name
              const count = counts[id] || 0
              const isPresent = count > 0

              return (
                <div
                  key={id}
                  className={`flex items-center gap-3 border-b border-white/[0.04] px-4 py-2.5 transition ${
                    isPresent ? 'bg-emerald-500/5' : ''
                  }`}
                >
                  {/* Check toggle */}
                  <button
                    onClick={() => handleToggle(id)}
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition ${
                      isPresent
                        ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-400'
                        : 'border-white/[0.08] text-white/15'
                    }`}
                  >
                    {isPresent && <Check className="h-3.5 w-3.5" />}
                  </button>

                  {/* Species info */}
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm ${isPresent ? 'text-white' : 'text-white/50'}`}>
                      {sp.chinese_name || sp.simplified_chinese_name || sp.english_name || sp.english_common_name}
                    </p>
                    <p className="text-xs text-white/25 italic truncate">{sp.scientific_name}</p>
                  </div>

                  {/* Count controls */}
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleDecrement(id)}
                      disabled={!isPresent}
                      className="flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.06] bg-white/[0.03] text-white/40 disabled:opacity-20"
                    >
                      <Minus className="h-3 w-3" />
                    </button>
                    <span className={`w-8 text-center text-sm font-medium ${isPresent ? 'text-emerald-400' : 'text-white/20'}`}>
                      {count}
                    </span>
                    <button
                      onClick={() => handleIncrement(id)}
                      className="flex h-7 w-7 items-center justify-center rounded-md border border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        ))}

        {filteredSpecies.length === 0 && (
          <div className="py-12 text-center text-sm text-white/25">
            {isZh ? '未找到匹配的物种' : 'No matching species found'}
          </div>
        )}
      </div>

      {/* Summary bar */}
      {totalSpecies > 0 && (
        <div className="border-t border-white/[0.06] bg-emerald-500/5 px-4 py-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-white/40">
              {isZh ? '已记录' : 'Recorded'}: <strong className="text-emerald-400">{totalSpecies}</strong> {isZh ? '种' : 'spp.'}
            </span>
            <span className="text-white/40">
              {isZh ? '总计' : 'Total'}: <strong className="text-emerald-400">{totalIndividuals}</strong> {isZh ? '只' : 'ind.'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
