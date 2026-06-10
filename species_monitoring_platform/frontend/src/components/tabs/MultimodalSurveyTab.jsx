import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart3, Camera, Download, FolderOpen, Loader2, MapPin,
  Mic, Plus, RefreshCw, Trash2, Upload, Users,
} from 'lucide-react'
import { StatCard, StatusBanner } from '../common'

const api = {
  listSessions: () => fetch('/api/multimodal/sessions').then(r => r.json()),
  createSession: (data) => fetch('/api/multimodal/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  getSession: (id) => fetch(`/api/multimodal/sessions/${id}`).then(r => r.json()),
  deleteSession: (id) => fetch(`/api/multimodal/sessions/${id}`, { method: 'DELETE' }).then(r => r.json()),
  importImages: (id, dir) => fetch(`/api/multimodal/sessions/${id}/import-images`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ directory: dir }) }).then(r => r.json()),
  importAudio: (id, dir) => fetch(`/api/multimodal/sessions/${id}/import-audio`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ directory: dir }) }).then(r => r.json()),
  addManualRecord: (id, data) => fetch(`/api/multimodal/sessions/${id}/manual`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  getSummary: (id) => fetch(`/api/multimodal/sessions/${id}/summary`).then(r => r.json()),
  exportCSV: (id) => fetch(`/api/multimodal/sessions/${id}/export/csv`).then(r => r.text()),
  exportDwC: (id) => fetch(`/api/multimodal/sessions/${id}/export/darwin-core`).then(r => r.blob()),
}

export default function MultimodalSurveyTab() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [importing, setImporting] = useState(null)

  const L = locale === 'zh' ? {
    badge: '多模态调查', title: '野生动物多样性调查', body: '整合红外相机、声学录音和人工观察数据，生成综合物种清单和多样性评估报告。',
    newSession: '新建调查', sessions: '调查列表', noSessions: '暂无调查记录', noSessionsHint: '点击"新建调查"开始。',
    siteName: '站点名称', latitude: '纬度', longitude: '经度', habitat: '生境类型', observer: '观察者',
    create: '创建', creating: '创建中...', cancel: '取消', forest: '森林', wetland: '湿地', grassland: '草地', montane: '山地',
    images: '照片', audio: '录音', manual: '手动记录', species: '物种数', shannon: 'Shannon指数',
    importImages: '导入红外照片', importAudio: '导入音频', addRecord: '添加记录', export: '导出',
    exportCSV: '导出 CSV', exportDwC: 'Darwin Core', dirPath: '目录路径', import: '导入', importing: '导入中...',
    speciesName: '物种名', count: '数量', evidenceType: '证据类型', add: '添加',
    visual: '目视', call: '叫声', track: '痕迹', evidence: '证据类型', multimodal: '多模态',
    richness: '物种丰富度', simpson: 'Simpson指数', evenness: '均匀度',
    totalDetections: '总检出', imgDet: '图像检出', audioDet: '声学检出', manualObs: '人工观察', confidence: '置信度',
    summaryTitle: '调查摘要', speciesList: '物种清单', diversityTitle: '多样性指数',
    blank: '空拍', delete: '删除', confirmDelete: '确认删除此调查？',
  } : {
    badge: 'Multimodal Survey', title: 'Wildlife Diversity Survey', body: 'Integrate infrared camera traps, acoustic recordings, and manual observations into comprehensive species inventories and diversity assessments.',
    newSession: 'New Survey', sessions: 'Survey Sessions', noSessions: 'No survey sessions yet', noSessionsHint: 'Click "New Survey" to start.',
    siteName: 'Site name', latitude: 'Latitude', longitude: 'Longitude', habitat: 'Habitat type', observer: 'Observer',
    create: 'Create', creating: 'Creating...', cancel: 'Cancel', forest: 'Forest', wetland: 'Wetland', grassland: 'Grassland', montane: 'Montane',
    images: 'Images', audio: 'Audio', manual: 'Manual', species: 'Species', shannon: 'Shannon H\'',
    importImages: 'Import Camera Trap Photos', importAudio: 'Import Audio', addRecord: 'Add Record', export: 'Export',
    exportCSV: 'Export CSV', exportDwC: 'Darwin Core', dirPath: 'Directory path', import: 'Import', importing: 'Importing...',
    speciesName: 'Species name', count: 'Count', evidenceType: 'Evidence type', add: 'Add',
    visual: 'Visual', call: 'Call/Song', track: 'Track/Sign', evidence: 'Evidence type', multimodal: 'Multimodal',
    richness: 'Species Richness', simpson: 'Simpson Index', evenness: 'Evenness',
    totalDetections: 'Total', imgDet: 'Image', audioDet: 'Acoustic', manualObs: 'Manual', confidence: 'Confidence',
    summaryTitle: 'Survey Summary', speciesList: 'Species Inventory', diversityTitle: 'Diversity Indices',
    blank: 'Blank', delete: 'Delete', confirmDelete: 'Delete this survey session?',
  }

  const loadSessions = useCallback(async () => {
    try {
      const data = await api.listSessions()
      setSessions(Array.isArray(data) ? data : data.sessions || [])
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

  const loadSummary = async (sessionId) => {
    try {
      const data = await api.getSummary(sessionId)
      setSummary(data)
      setSelectedSession(sessionId)
    } catch (err) {
      setError(String(err))
    }
  }

  const handleExportCSV = async () => {
    if (!selectedSession) return
    try {
      const csv = await api.exportCSV(selectedSession)
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `survey_${selectedSession}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(String(err))
    }
  }

  const handleExportDwC = async () => {
    if (!selectedSession) return
    try {
      const blob = await api.exportDwC(selectedSession)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `survey_${selectedSession}_dwc.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(String(err))
    }
  }

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="card-elevated p-5 md:p-8">
        <div className="section-kicker"><Camera className="h-3.5 w-3.5" />{L.badge}</div>
        <h2 className="mt-3 text-xl font-bold md:text-2xl" style={{ color: 'var(--text-primary)' }}>{L.title}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>{L.body}</p>
        <div className="mt-4 flex gap-2">
          <button onClick={() => setShowCreate(v => !v)} className="btn-primary">
            <Plus className="h-4 w-4" />{showCreate ? L.cancel : L.newSession}
          </button>
          <button onClick={loadSessions} className="btn-ghost"><RefreshCw className="h-4 w-4" /></button>
        </div>
      </section>

      {error && <StatusBanner tone="error" message={error} />}

      {showCreate && <CreateSessionForm L={L} onCreated={() => { setShowCreate(false); loadSessions() }} onError={setError} />}

      {/* Session List + Detail */}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.5fr]">
        {/* Sessions */}
        <section className="card p-5">
          <h3 className="mb-3 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{L.sessions}</h3>
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin" style={{ color: 'var(--text-tertiary)' }} /></div>
          ) : sessions.length === 0 ? (
            <div className="py-8 text-center">
              <FolderOpen className="mx-auto mb-2 h-8 w-8" style={{ color: 'var(--text-tertiary)', opacity: 0.4 }} />
              <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{L.noSessions}</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{L.noSessionsHint}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map(s => (
                <button
                  key={s.session_id}
                  onClick={() => loadSummary(s.session_id)}
                  className="card-interactive w-full p-3 text-left"
                  style={selectedSession === s.session_id ? { borderColor: 'var(--cornell-carnelian)', borderWidth: 2 } : {}}
                >
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{s.site_name || s.session_id}</p>
                  <div className="mt-1 flex gap-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    <span><Camera className="inline h-3 w-3" /> {s.total_images || 0}</span>
                    <span><Mic className="inline h-3 w-3" /> {s.total_audio || 0}</span>
                    <span><Users className="inline h-3 w-3" /> {s.total_manual || 0}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Detail Panel */}
        {summary ? (
          <div className="space-y-4">
            {/* Stats */}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard label={L.species} value={summary.total_species || 0} icon={BarChart3} color="teal" />
              <StatCard label={L.images} value={summary.total_images || 0} icon={Camera} color="blue" subtitle={summary.blank_images ? `${summary.blank_images} ${L.blank}` : undefined} />
              <StatCard label={L.audio} value={summary.total_audio || 0} icon={Mic} color="forest" />
              <StatCard label={L.manual} value={summary.total_manual || 0} icon={Users} color="amber" />
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-2">
              <ImportButton L={L} type="images" sessionId={selectedSession} importing={importing} setImporting={setImporting} onDone={() => loadSummary(selectedSession)} setError={setError} />
              <ImportButton L={L} type="audio" sessionId={selectedSession} importing={importing} setImporting={setImporting} onDone={() => loadSummary(selectedSession)} setError={setError} />
              <button onClick={handleExportCSV} className="btn-secondary text-xs"><Download className="h-3.5 w-3.5" />{L.exportCSV}</button>
              <button onClick={handleExportDwC} className="btn-secondary text-xs"><Download className="h-3.5 w-3.5" />{L.exportDwC}</button>
            </div>

            {/* Diversity */}
            {summary.diversity && (
              <section className="card p-4">
                <h4 className="mb-3 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{L.diversityTitle}</h4>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  <DiversityStat label={L.richness} value={summary.diversity.richness} />
                  <DiversityStat label={L.shannon} value={summary.diversity.shannon} />
                  <DiversityStat label={L.simpson} value={summary.diversity.simpson} />
                  <DiversityStat label={L.evenness} value={summary.diversity.evenness} />
                </div>
              </section>
            )}

            {/* Species Table */}
            {summary.species_list?.length > 0 && (
              <section className="card p-4">
                <h4 className="mb-3 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{L.speciesList}</h4>
                <div className="data-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{L.speciesName}</th>
                        <th>{L.totalDetections}</th>
                        <th>{L.imgDet}</th>
                        <th>{L.audioDet}</th>
                        <th>{L.manualObs}</th>
                        <th>{L.confidence}</th>
                        <th>{L.evidence}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.species_list.map((sp, i) => (
                        <tr key={i}>
                          <td className="font-medium">{sp.species}</td>
                          <td>{sp.total_detections}</td>
                          <td>{sp.image_detections}</td>
                          <td>{sp.audio_detections}</td>
                          <td>{sp.manual_observations}</td>
                          <td>{(sp.max_confidence * 100).toFixed(0)}%</td>
                          <td>
                            <div className="flex gap-1">
                              {sp.evidence_types?.map(t => (
                                <span key={t} className="rounded-full px-2 py-0.5 text-[10px]" style={{
                                  background: t === 'camera_trap' ? 'rgba(0,102,153,0.1)' : t === 'acoustic' ? 'rgba(45,106,79,0.1)' : 'rgba(179,27,27,0.08)',
                                  color: t === 'camera_trap' ? 'var(--cornell-blue)' : t === 'acoustic' ? 'var(--cornell-forest)' : 'var(--cornell-carnelian)',
                                }}>{t}</span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Manual Record */}
            <ManualRecordForm L={L} sessionId={selectedSession} onAdded={() => loadSummary(selectedSession)} setError={setError} />
          </div>
        ) : (
          <div className="card flex items-center justify-center p-12" style={{ color: 'var(--text-tertiary)' }}>
            <p className="text-sm">{locale === 'zh' ? '选择一个调查查看详情' : 'Select a survey to view details'}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function CreateSessionForm({ L, onCreated, onError }) {
  const [form, setForm] = useState({ site_name: '', latitude: '', longitude: '', habitat_type: 'forest', observer: '' })
  const [saving, setSaving] = useState(false)

  const handleCreate = async () => {
    if (!form.site_name) return
    setSaving(true)
    try {
      await api.createSession({
        ...form,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
      })
      onCreated()
    } catch (err) {
      onError(String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card p-5">
      <div className="grid gap-3 md:grid-cols-2">
        <input value={form.site_name} onChange={e => setForm({ ...form, site_name: e.target.value })} placeholder={L.siteName + ' *'} className="input-field" />
        <input value={form.observer} onChange={e => setForm({ ...form, observer: e.target.value })} placeholder={L.observer} className="input-field" />
        <input value={form.latitude} onChange={e => setForm({ ...form, latitude: e.target.value })} placeholder={L.latitude} type="number" step="0.0001" className="input-field" />
        <input value={form.longitude} onChange={e => setForm({ ...form, longitude: e.target.value })} placeholder={L.longitude} type="number" step="0.0001" className="input-field" />
        <select value={form.habitat_type} onChange={e => setForm({ ...form, habitat_type: e.target.value })} className="input-field">
          <option value="forest">{L.forest}</option>
          <option value="wetland">{L.wetland}</option>
          <option value="grassland">{L.grassland}</option>
          <option value="montane">{L.montane}</option>
        </select>
        <button onClick={handleCreate} disabled={saving || !form.site_name} className="btn-primary disabled:opacity-50">
          {saving ? L.creating : L.create}
        </button>
      </div>
    </section>
  )
}

function ImportButton({ L, type, sessionId, importing, setImporting, onDone, setError }) {
  const [dir, setDir] = useState('')
  const [showInput, setShowInput] = useState(false)

  const handleImport = async () => {
    if (!dir.trim()) return
    setImporting(type)
    try {
      const fn = type === 'images' ? api.importImages : api.importAudio
      await fn(sessionId, dir.trim())
      setDir('')
      setShowInput(false)
      onDone()
    } catch (err) {
      setError(String(err))
    } finally {
      setImporting(null)
    }
  }

  if (!showInput) {
    return (
      <button onClick={() => setShowInput(true)} className="btn-secondary text-xs">
        <Upload className="h-3.5 w-3.5" />{type === 'images' ? L.importImages : L.importAudio}
      </button>
    )
  }

  return (
    <div className="flex gap-2">
      <input value={dir} onChange={e => setDir(e.target.value)} placeholder={L.dirPath} className="input-field text-xs" style={{ minWidth: 200 }} />
      <button onClick={handleImport} disabled={importing === type} className="btn-primary text-xs disabled:opacity-50">
        {importing === type ? L.importing : L.import}
      </button>
      <button onClick={() => setShowInput(false)} className="btn-ghost text-xs">{L.cancel}</button>
    </div>
  )
}

function ManualRecordForm({ L, sessionId, onAdded, setError }) {
  const [form, setForm] = useState({ species: '', count: 1, evidence_type: 'visual' })
  const [saving, setSaving] = useState(false)

  const handleAdd = async () => {
    if (!form.species.trim()) return
    setSaving(true)
    try {
      await api.addManualRecord(sessionId, form)
      setForm({ species: '', count: 1, evidence_type: 'visual' })
      onAdded()
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card p-4">
      <h4 className="mb-3 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{L.addRecord}</h4>
      <div className="flex flex-wrap gap-2">
        <input value={form.species} onChange={e => setForm({ ...form, species: e.target.value })} placeholder={L.speciesName} className="input-field flex-1" style={{ minWidth: 160 }} />
        <input value={form.count} onChange={e => setForm({ ...form, count: Number(e.target.value) || 1 })} type="number" min="1" className="input-field w-20" />
        <select value={form.evidence_type} onChange={e => setForm({ ...form, evidence_type: e.target.value })} className="input-field w-32">
          <option value="visual">{L.visual}</option>
          <option value="call">{L.call}</option>
          <option value="track">{L.track}</option>
        </select>
        <button onClick={handleAdd} disabled={saving || !form.species.trim()} className="btn-primary disabled:opacity-50">
          {L.add}
        </button>
      </div>
    </section>
  )
}

function DiversityStat({ label, value }) {
  return (
    <div className="rounded-lg border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface-secondary)' }}>
      <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
      <p className="mt-1 text-lg font-bold" style={{ color: 'var(--text-primary)' }}>{typeof value === 'number' ? value.toFixed(4) : value ?? '--'}</p>
    </div>
  )
}
