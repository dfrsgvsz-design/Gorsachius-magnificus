import React from 'react'
import { AlertTriangle, CheckCircle2, Clock, MapPin, TrendingUp } from 'lucide-react'

const FLAG_TYPES = {
  range_outlier: { icon: MapPin, color: 'amber', labelEn: 'Range outlier', labelZh: '分布异常' },
  temporal_anomaly: { icon: Clock, color: 'amber', labelEn: 'Unusual timing', labelZh: '时间异常' },
  count_anomaly: { icon: TrendingUp, color: 'amber', labelEn: 'Count anomaly', labelZh: '数量异常' },
  low_confidence: { icon: AlertTriangle, color: 'red', labelEn: 'Low confidence', labelZh: '低置信度' },
  verified: { icon: CheckCircle2, color: 'emerald', labelEn: 'Verified', labelZh: '已验证' },
}

const COLORS = {
  emerald: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  amber: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  red: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' },
}

export function flagObservation(observation, knownSpeciesRange = {}) {
  const flags = []

  if (observation.confidence != null && observation.confidence < 0.3) {
    flags.push({ type: 'low_confidence', detail: `Confidence: ${(observation.confidence * 100).toFixed(1)}%` })
  }

  if (observation.count != null && observation.count > 100) {
    flags.push({ type: 'count_anomaly', detail: `Count: ${observation.count} (unusually high)` })
  }

  const range = knownSpeciesRange[observation.scientific_name || observation.species_id]
  if (range && observation.latitude && observation.longitude) {
    const { min_lat, max_lat, min_lon, max_lon } = range
    if (
      observation.latitude < min_lat || observation.latitude > max_lat ||
      observation.longitude < min_lon || observation.longitude > max_lon
    ) {
      flags.push({ type: 'range_outlier', detail: 'Outside known distribution range' })
    }
  }

  const hour = observation.hour ?? (observation.timestamp ? new Date(observation.timestamp).getHours() : null)
  if (hour != null) {
    const isNocturnal = observation.taxon_group === 'birds' &&
      (observation.scientific_name || '').toLowerCase().includes('owl') ||
      (observation.scientific_name || '').toLowerCase().includes('gorsachius')

    if (isNocturnal && hour >= 8 && hour <= 17) {
      flags.push({ type: 'temporal_anomaly', detail: 'Nocturnal species recorded during daytime' })
    }
  }

  return flags
}

export default function DataQualityPanel({ observations = [], locale = 'en' }) {
  const isZh = locale === 'zh'

  const allFlags = observations.flatMap((obs) => {
    const flags = flagObservation(obs)
    return flags.map((f) => ({ ...f, observation: obs }))
  })

  const flagCounts = {}
  for (const f of allFlags) {
    flagCounts[f.type] = (flagCounts[f.type] || 0) + 1
  }

  const totalObs = observations.length
  const flaggedObs = new Set(allFlags.map((f) => f.observation)).size
  const qualityScore = totalObs > 0 ? Math.round(((totalObs - flaggedObs) / totalObs) * 100) : 100

  return (
    <div className="card-padded space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">
            {isZh ? '数据质量' : 'Data Quality'}
          </h3>
          <p className="mt-0.5 text-xs text-white/30">
            {isZh
              ? `${totalObs} 条记录中 ${flaggedObs} 条被标记`
              : `${flaggedObs} of ${totalObs} records flagged`
            }
          </p>
        </div>
        <div className={`rounded-lg px-3 py-1.5 text-sm font-bold ${
          qualityScore >= 90 ? 'bg-emerald-500/15 text-emerald-400'
            : qualityScore >= 70 ? 'bg-amber-500/15 text-amber-400'
            : 'bg-red-500/15 text-red-400'
        }`}>
          {qualityScore}%
        </div>
      </div>

      {/* Progress bar */}
      <div className="progress-bar">
        <div
          className="progress-bar-fill"
          style={{
            width: `${qualityScore}%`,
            background: qualityScore >= 90 ? '#34d399' : qualityScore >= 70 ? '#fbbf24' : '#f87171',
          }}
        />
      </div>

      {/* Flag summary */}
      {Object.entries(flagCounts).length > 0 && (
        <div className="space-y-2">
          {Object.entries(flagCounts).map(([type, count]) => {
            const cfg = FLAG_TYPES[type] || FLAG_TYPES.low_confidence
            const c = COLORS[cfg.color]
            const Icon = cfg.icon
            return (
              <div key={type} className={`flex items-center gap-3 rounded-lg border p-2.5 ${c.border} ${c.bg}`}>
                <Icon className={`h-4 w-4 ${c.text} shrink-0`} />
                <span className={`text-xs font-medium ${c.text}`}>
                  {isZh ? cfg.labelZh : cfg.labelEn}
                </span>
                <span className="ml-auto rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-white/40">
                  {count}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {allFlags.length === 0 && totalObs > 0 && (
        <div className="flex items-center gap-2 text-xs text-emerald-400">
          <CheckCircle2 className="h-4 w-4" />
          {isZh ? '所有记录通过质量检查' : 'All records pass quality checks'}
        </div>
      )}
    </div>
  )
}
