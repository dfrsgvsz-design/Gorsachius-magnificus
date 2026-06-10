import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  AlertCircle, CheckCircle2, ExternalLink, Globe2, Loader2, RefreshCw, Search,
} from 'lucide-react'
import {
  getApiErrorMessage, getXCKeyStatus, searchXenoCanto, setXCKey,
} from '../../lib/api'
import { StatusBanner } from '../common'

export default function XenoCantoTab() {
  const { t } = useTranslation()

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return t('xenoCantoPage.timePlaceholder')
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(timestamp))
  }
  const [query, setQuery] = useState('')
  const [country, setCountry] = useState('China')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [keyInput, setKeyInput] = useState('')
  const [keyStatus, setKeyStatus] = useState(null)
  const [savingKey, setSavingKey] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const loadKeyStatus = async () => {
    setRefreshing(true)
    try {
      const status = await getXCKeyStatus()
      setKeyStatus(status)
      setLastUpdated(Date.now())
    } catch (err) {
      setError(getApiErrorMessage(err, t('xenoCantoPage.loadKeyStatusFailed')))
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadKeyStatus()
  }, [])

  const handleSaveKey = async () => {
    if (!keyInput.trim()) return
    setSavingKey(true)
    setError(null)
    try {
      await setXCKey(keyInput.trim())
      setKeyStatus({
        configured: true,
        key_preview: `${keyInput.trim().slice(0, 4)}...`,
      })
      setKeyInput('')
      setLastUpdated(Date.now())
    } catch (err) {
      setError(getApiErrorMessage(err, t('xenoCantoPage.saveKeyFailed')))
    } finally {
      setSavingKey(false)
    }
  }

  const handleSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    setError(null)
    try {
      const data = await searchXenoCanto(query, country)
      setResults(data)
      setLastUpdated(Date.now())
    } catch (err) {
      const message = getApiErrorMessage(err, t('xenoCantoPage.searchFailed'))
      setResults({ error: message })
      setError(message)
    } finally {
      setSearching(false)
    }
  }

  const lastUpdatedLabel = formatTimestamp(lastUpdated)

  return (
    <div className="space-y-5">
      <section className="glass-card space-y-4 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs font-medium text-violet-300">
              <Globe2 className="h-3.5 w-3.5" />
              {t('xenoCantoPage.badge')}
            </div>
            <h2 className="mt-3 text-2xl font-bold text-white">{t('xenoCantoPage.title')}</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-300">
              {t('xenoCantoPage.body')}
            </p>
          </div>

          <a
            href="https://xeno-canto.org/account"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200"
          >
            {t('xenoCantoPage.getKey')}
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-white">{t('xenoCantoPage.apiKeyStatus')}</h3>
            {keyStatus?.configured ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 px-2.5 py-1 text-xs text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {t('xenoCantoPage.configured')}
                {keyStatus.key_preview ? ` (${keyStatus.key_preview})` : ''}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 px-2.5 py-1 text-xs text-amber-300">
                <AlertCircle className="h-3.5 w-3.5" />
                {t('xenoCantoPage.notConfigured')}
              </span>
            )}
          </div>
          <p className="mb-3 text-xs leading-5 text-gray-500">
            {t('xenoCantoPage.keyHelp')}
          </p>
          <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-gray-400">
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">{t('xenoCantoPage.lastSync', { time: lastUpdatedLabel })}</span>
            <button
              onClick={loadKeyStatus}
              disabled={refreshing}
              className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-gray-300 hover:bg-white/10 disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? t('xenoCantoPage.refreshing') : t('xenoCantoPage.refreshStatus')}
            </button>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="password"
              placeholder={t('xenoCantoPage.keyPlaceholder')}
              value={keyInput}
              onChange={(event) => setKeyInput(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && handleSaveKey()}
              className="flex-1 rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-violet-500/50 focus:outline-none"
            />
            <button
              onClick={handleSaveKey}
              disabled={!keyInput.trim() || savingKey}
              className="rounded-lg bg-violet-500/70 px-4 py-2 text-xs font-medium text-white transition-all hover:bg-violet-500 disabled:opacity-40"
            >
              {savingKey ? t('xenoCantoPage.saving') : t('xenoCantoPage.saveKey')}
            </button>
          </div>
        </div>
      </section>

      <section className="glass-card p-6">
        <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
          <Search className="h-5 w-5 text-violet-400" />
          {t('xenoCantoPage.searchRecordings')}
        </h3>
        <div className="flex flex-col gap-3 lg:flex-row">
          <input
            type="text"
            placeholder={t('xenoCantoPage.queryPlaceholder')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && handleSearch()}
            className="flex-1 rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-violet-500/50 focus:outline-none"
          />
          <select
            value={country}
            onChange={(event) => setCountry(event.target.value)}
            className="rounded-xl border border-white/20 bg-white/10 px-3 py-2.5 text-sm lg:w-[140px]"
          >
            <option value="China">{t('xenoCantoPage.countryChina')}</option>
            <option value="">{t('xenoCantoPage.countryGlobal')}</option>
            <option value="Taiwan">{t('xenoCantoPage.countryTaiwan')}</option>
            <option value="Vietnam">{t('xenoCantoPage.countryVietnam')}</option>
          </select>
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="flex items-center justify-center gap-2 rounded-xl bg-violet-500/80 px-5 py-2.5 text-sm font-medium transition-all hover:bg-violet-500 disabled:opacity-40 lg:min-w-[120px]"
          >
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {t('xenoCantoPage.search')}
          </button>
        </div>
      </section>

      {!results?.error && <StatusBanner tone="warning" message={error} />}

      <StatusBanner tone="warning" message={results?.error} />

      {results && !results.error && results.total_results > 0 && (
        <section className="glass-card p-4">
          <h3 className="mb-3 text-sm font-medium text-gray-300">
            {t('xenoCantoPage.foundRecordings', { count: results.total_results })}
          </h3>
          <div className="max-h-[500px] space-y-2 overflow-y-auto">
            {results.recordings?.map((recording, index) => (
              <div key={`${recording.file_url || recording.id || index}`} className="flex items-center gap-4 rounded-xl bg-white/5 p-3 transition-all hover:bg-white/10">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20 text-xs font-bold text-violet-300">
                  {recording.quality}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-white">
                    {recording.species}
                    {' '}
                    <span className="italic text-gray-500">({recording.scientific_name})</span>
                  </p>
                  <p className="text-xs text-gray-500">
                    {recording.locality} · {recording.date} · {recording.duration} · {recording.recordist}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded bg-white/10 px-2 py-0.5 text-xs text-gray-400">{recording.type}</span>
                  {recording.file_url && (
                    <a
                      href={recording.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-violet-400 hover:text-violet-300"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {results && !results.error && results.total_results === 0 && (
        <section className="glass-card p-4 text-center text-sm text-gray-400">
          {t('xenoCantoPage.noResults')}
        </section>
      )}
    </div>
  )
}
