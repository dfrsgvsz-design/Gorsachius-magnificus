import React, { useMemo } from 'react'
import { BarChart3, Download, FileSpreadsheet, TreePine } from 'lucide-react'
import { calculateAllIndices, buildSpeciesTable } from '../../lib/diversityIndices'

export default function DiversityReport({
  observations = [],
  projectName = '',
  siteName = '',
  locale = 'en',
  onExportCSV,
}) {
  const isZh = locale === 'zh'

  const indices = useMemo(() => calculateAllIndices(observations), [observations])
  const speciesTable = useMemo(() => buildSpeciesTable(observations), [observations])

  if (observations.length === 0) {
    return (
      <div className="card-padded text-center py-12">
        <TreePine className="mx-auto mb-3 h-10 w-10 text-white/15" />
        <p className="text-sm text-white/40">
          {isZh ? '暂无观察数据，无法计算多样性指数' : 'No observation data to calculate diversity indices'}
        </p>
      </div>
    )
  }

  const handleExportCSV = () => {
    if (onExportCSV) {
      onExportCSV(indices, speciesTable)
      return
    }

    const indexRows = [
      ['Index', 'Symbol', 'Value'],
      ...Object.values(indices)
        .filter((v) => v.symbol)
        .map((v) => [isZh ? v.labelZh : v.label, v.symbol, v.value]),
    ]

    const speciesRows = [
      ['', '', '', '', ''],
      [isZh ? '物种名录' : 'Species List', '', '', '', ''],
      [isZh ? '学名' : 'Scientific Name', isZh ? '中文名' : 'Chinese Name', isZh ? '英文名' : 'English Name', isZh ? '个体数' : 'Count', isZh ? '相对丰度(%)' : 'Rel. Abundance (%)'],
      ...speciesTable.map((row) => [
        row.scientific_name,
        row.chinese_name,
        row.english_name,
        row.count,
        row.relative_abundance,
      ]),
    ]

    const allRows = [
      [isZh ? '生物多样性报告' : 'Biodiversity Report'],
      [isZh ? '项目' : 'Project', projectName || '-'],
      [isZh ? '站点' : 'Site', siteName || '-'],
      [isZh ? '日期' : 'Date', new Date().toISOString().slice(0, 10)],
      [''],
      [isZh ? '多样性指数' : 'Diversity Indices'],
      ...indexRows,
      ...speciesRows,
    ]

    const csv = allRows.map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
    const bom = '\uFEFF'
    const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `diversity_report_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const indexCards = Object.entries(indices)
    .filter(([, v]) => v.symbol)
    .map(([key, v]) => ({ key, ...v }))

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-emerald-500/10 p-2">
            <BarChart3 className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">
              {isZh ? '多样性指数报告' : 'Diversity Index Report'}
            </h3>
            <p className="text-xs text-white/30">
              {projectName && `${projectName}`}
              {siteName && ` · ${siteName}`}
              {` · ${indices.speciesRichness.value} ${isZh ? '种' : 'spp.'} · ${indices.totalAbundance.value} ${isZh ? '个体' : 'ind.'}`}
            </p>
          </div>
        </div>
        <button onClick={handleExportCSV} className="btn-secondary btn-sm">
          <Download className="h-3.5 w-3.5" />
          {isZh ? '导出CSV' : 'Export CSV'}
        </button>
      </div>

      {/* Index cards */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {indexCards.map((idx) => (
          <div key={idx.key} className="card-padded">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-white/30">{idx.symbol}</span>
            </div>
            <p className="mt-1 text-xl font-bold text-white">{idx.value}</p>
            <p className="mt-0.5 text-[11px] text-white/30">{isZh ? idx.labelZh : idx.label}</p>
          </div>
        ))}
      </div>

      {/* Species table */}
      <div className="data-table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{isZh ? '学名' : 'Scientific Name'}</th>
              <th>{isZh ? '中文名' : 'Chinese Name'}</th>
              <th className="text-right">{isZh ? '个体数' : 'Count'}</th>
              <th className="text-right">{isZh ? '相对丰度' : 'Rel. %'}</th>
            </tr>
          </thead>
          <tbody>
            {speciesTable.map((row, i) => (
              <tr key={row.scientific_name}>
                <td className="text-white/25">{i + 1}</td>
                <td className="italic text-white/70">{row.scientific_name}</td>
                <td>{row.chinese_name || row.english_name || '-'}</td>
                <td className="text-right font-medium text-white">{row.count}</td>
                <td className="text-right">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-1.5 rounded-full bg-emerald-400" style={{ width: `${Math.max(4, row.relative_abundance * 0.8)}px` }} />
                    <span className="text-white/40">{row.relative_abundance}%</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
