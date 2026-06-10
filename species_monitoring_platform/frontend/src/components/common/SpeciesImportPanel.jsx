import React, { useCallback, useState } from 'react'
import { AlertTriangle, CheckCircle2, Database, FileSpreadsheet, Loader2, Upload } from 'lucide-react'
import axios from 'axios'

export default function SpeciesImportPanel({ locale = 'en', onImportComplete }) {
  const isZh = locale === 'zh'
  const [file, setFile] = useState(null)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [dragActive, setDragActive] = useState(false)

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragActive(false)
    const dropped = e.dataTransfer?.files?.[0]
    if (dropped) {
      setFile(dropped)
      setResult(null)
      setError(null)
    }
  }, [])

  const handleFileSelect = (e) => {
    const selected = e.target.files?.[0]
    if (selected) {
      setFile(selected)
      setResult(null)
      setError(null)
    }
  }

  const handleImport = async () => {
    if (!file) return
    setImporting(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const resp = await axios.post('/api/admin/taxonomy/bulk-import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      })

      setResult(resp.data)
      onImportComplete?.()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : (isZh ? '导入失败' : 'Import failed'))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="card-padded space-y-4">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-violet-500/10 p-2">
          <Database className="h-4 w-4 text-violet-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">
            {isZh ? '物种数据批量导入' : 'Bulk Species Import'}
          </h3>
          <p className="text-xs text-white/30">
            {isZh ? '上传 CSV 或 JSON 文件批量导入物种数据' : 'Upload CSV or JSON to bulk-import species data'}
          </p>
        </div>
      </div>

      {/* Format guide */}
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-white/40">
        <p className="font-medium text-white/60 mb-1.5">
          {isZh ? 'CSV 格式要求' : 'CSV Format Requirements'}:
        </p>
        <p className="font-mono text-[11px] text-white/30">
          scientific_name, chinese_name, english_name, taxon_group, order, family, protection, iucn
        </p>
        <p className="mt-1.5 text-[11px] text-white/25">
          {isZh
            ? '中文列名也支持：学名, 中文名, 英文名, 类群, 目, 科, 保护等级, 红色名录'
            : 'Chinese column names also supported: 学名, 中文名, 英文名, 类群, 目, 科, 保护等级, 红色名录'
          }
        </p>
      </div>

      {/* Drop zone */}
      <div
        className={`upload-zone-enhanced cursor-pointer ${dragActive ? 'active' : ''}`}
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onClick={() => document.getElementById('species-import-input')?.click()}
      >
        <div className="upload-icon">
          <FileSpreadsheet className="h-6 w-6 text-emerald-400" />
        </div>
        <div className="text-center">
          <p className="text-sm text-white/50">
            {file
              ? file.name
              : (isZh ? '点击或拖拽文件到此处' : 'Click or drag file here')
            }
          </p>
          <p className="mt-1 text-xs text-white/25">
            {isZh ? '支持 .csv, .json 格式' : 'Supports .csv, .json formats'}
          </p>
          {file && (
            <p className="mt-1 text-xs text-emerald-400/60">
              {(file.size / 1024).toFixed(1)} KB
            </p>
          )}
        </div>
        <input
          id="species-import-input"
          type="file"
          accept=".csv,.json"
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>

      {/* Import button */}
      <button
        onClick={handleImport}
        disabled={!file || importing}
        className="btn-primary w-full disabled:opacity-40"
      >
        {importing
          ? <><Loader2 className="h-4 w-4 animate-spin" /> {isZh ? '导入中…' : 'Importing…'}</>
          : <><Upload className="h-4 w-4" /> {isZh ? '开始导入' : 'Start Import'}</>
        }
      </button>

      {/* Result */}
      {result && (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-emerald-400">{result.message}</p>
            <p className="mt-1 text-xs text-white/40">
              {isZh
                ? `解析 ${result.total_parsed} 条，成功导入 ${result.imported} 条`
                : `Parsed ${result.total_parsed}, imported ${result.imported}`
              }
            </p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-red-500/20 bg-red-500/10 p-3">
          <AlertTriangle className="h-4 w-4 text-red-400 mt-0.5 shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Data sources */}
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-xs">
        <p className="font-medium text-white/50 mb-2">
          {isZh ? '推荐数据来源' : 'Recommended Data Sources'}:
        </p>
        <ul className="space-y-1.5 text-white/30">
          <li>
            <a href="http://www.sp2000.org.cn" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
              sp2000.org.cn
            </a>
            {' — '}{isZh ? '中国生物物种名录（年度更新，免费下载）' : 'Catalogue of Life China (annual, free download)'}
          </li>
          <li>
            <a href="http://zoology.especies.cn" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
              zoology.especies.cn
            </a>
            {' — '}{isZh ? '中国动物主题数据库' : 'China Animal Thematic Database'}
          </li>
          <li>
            <a href="https://www.gbif.org" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
              gbif.org
            </a>
            {' — '}{isZh ? '全球生物多样性信息网络' : 'Global Biodiversity Information Facility'}
          </li>
        </ul>
        <p className="mt-2 text-[11px] text-white/20">
          {isZh
            ? '也可使用命令行工具: python scripts/fetch_species_data.py --source gbif --taxon-group mammals'
            : 'CLI tool: python scripts/fetch_species_data.py --source gbif --taxon-group mammals'
          }
        </p>
      </div>
    </div>
  )
}
