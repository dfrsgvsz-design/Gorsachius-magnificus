import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Crosshair, Loader2, Plus, Trash2, Upload } from 'lucide-react'
import { getApiErrorMessage, listFewShotDetectors, createFewShotDetector, deleteFewShotDetector } from '../../lib/api'
import { EmptyPanel, LoadingState, PageHero, SectionHeader, StatusBanner } from '../common'

export default function FewShotTab() {
  const { t } = useTranslation()
  const [detectors, setDetectors] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [species, setSpecies] = useState('')
  const [files, setFiles] = useState([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  const loadDetectors = useCallback(async () => {
    try {
      const data = await listFewShotDetectors()
      setDetectors(data.detectors || [])
    } catch { /* silent */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadDetectors() }, [loadDetectors])

  const handleCreate = async () => {
    if (!name.trim() || !species.trim() || files.length === 0) return
    setCreating(true)
    setError(null)
    try {
      const result = await createFewShotDetector(name.trim(), species.trim(), files)
      if (result.error) {
        setError(result.error)
      } else {
        setName('')
        setSpecies('')
        setFiles([])
        setShowForm(false)
        await loadDetectors()
      }
    } catch (err) {
      setError(getApiErrorMessage(err, t('fewshotPage.createFailed', { defaultValue: 'Failed to create detector' })))
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteFewShotDetector(id)
      await loadDetectors()
    } catch { /* silent */ }
  }

  if (loading) return <LoadingState text={t('fewshotPage.loading', { defaultValue: 'Loading detectors...' })} />

  return (
    <div className="space-y-6">
      <PageHero
        kicker={<><Crosshair className="h-3.5 w-3.5" />{t('fewshotPage.badge', { defaultValue: 'Few-shot species detection' })}</>}
        title={t('fewshotPage.title', { defaultValue: 'Create custom detectors for rare species from minimal reference recordings' })}
        body={t('fewshotPage.body', { defaultValue: 'Upload 1-5 reference recordings of a target species. The system extracts acoustic embeddings and builds a prototype detector that can scan large audio collections using cosine similarity matching — no retraining needed.' })}
      />

      <StatusBanner tone="error" message={error} />

      <section className="section-shell space-y-4">
        <div className="flex items-start justify-between gap-3">
          <SectionHeader title={t('fewshotPage.detectorsTitle', { defaultValue: 'Saved detectors' })} />
          <button onClick={() => setShowForm((v) => !v)} className="touch-button flex shrink-0 items-center gap-1 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-300 active:scale-[0.97]">
            <Plus className="h-3 w-3" />
            {showForm ? t('common.cancel', { defaultValue: 'Cancel' }) : t('fewshotPage.newDetector', { defaultValue: 'New detector' })}
          </button>
        </div>

        {showForm && (
          <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.04] p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('fewshotPage.detectorName', { defaultValue: 'Detector name *' })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500" />
              <input value={species} onChange={(e) => setSpecies(e.target.value)} placeholder={t('fewshotPage.speciesName', { defaultValue: 'Target species (scientific name) *' })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500" />
            </div>
            <div className="rounded-lg border border-dashed border-white/20 p-4 text-center">
              <Upload className="mx-auto mb-2 h-6 w-6 text-gray-500" />
              <label className="cursor-pointer text-sm text-emerald-400 hover:underline">
                {t('fewshotPage.uploadRef', { defaultValue: 'Upload 1-5 reference audio files' })}
                <input type="file" accept="audio/*" multiple className="hidden" onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 5))} />
              </label>
              {files.length > 0 && <p className="mt-2 text-xs text-gray-400">{files.length} {t('fewshotPage.filesSelected', { defaultValue: 'file(s) selected' })}</p>}
            </div>
            <button onClick={handleCreate} disabled={creating || !name.trim() || !species.trim() || files.length === 0} className="touch-button w-full rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white active:scale-[0.97] disabled:opacity-50">
              {creating ? <><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t('fewshotPage.creating', { defaultValue: 'Creating...' })}</> : t('fewshotPage.createDetector', { defaultValue: 'Create detector' })}
            </button>
          </div>
        )}

        {detectors.length === 0 ? (
          <EmptyPanel icon={Crosshair} title={t('fewshotPage.noDetectors', { defaultValue: 'No detectors created yet' })} body={t('fewshotPage.noDetectorsBody', { defaultValue: 'Create your first few-shot detector by uploading reference recordings of your target species.' })} />
        ) : (
          <div className="space-y-2">
            {detectors.map((det) => (
              <div key={det.id} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-4">
                <Crosshair className="h-5 w-5 shrink-0 text-emerald-400" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white">{det.name}</p>
                  <p className="mt-0.5 text-xs text-gray-500">{det.species} · {det.n_references} {t('fewshotPage.references', { defaultValue: 'reference(s)' })} · {new Date(det.created_at).toLocaleDateString()}</p>
                </div>
                <button onClick={() => handleDelete(det.id)} className="touch-button shrink-0 rounded-lg border border-red-500/20 p-2 text-red-400/60 active:scale-[0.95]">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
