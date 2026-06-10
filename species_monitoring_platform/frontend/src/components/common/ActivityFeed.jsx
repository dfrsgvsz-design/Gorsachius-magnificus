import React from 'react'
import {
  Bird,
  Camera,
  CheckCircle2,
  Eye,
  FileAudio,
  MapPin,
  Plus,
  RefreshCw,
  Route,
  Upload,
} from 'lucide-react'

const ACTIVITY_ICONS = {
  observation: Bird,
  detection: FileAudio,
  verification: CheckCircle2,
  survey_start: MapPin,
  survey_end: CheckCircle2,
  sync: RefreshCw,
  photo: Camera,
  route_import: Route,
  species_add: Plus,
  review: Eye,
  upload: Upload,
}

const ACTIVITY_COLORS = {
  observation: 'bg-emerald-500/10 text-emerald-400',
  detection: 'bg-cyan-500/10 text-cyan-400',
  verification: 'bg-violet-500/10 text-violet-400',
  survey_start: 'bg-amber-500/10 text-amber-400',
  survey_end: 'bg-emerald-500/10 text-emerald-400',
  sync: 'bg-cyan-500/10 text-cyan-400',
  photo: 'bg-amber-500/10 text-amber-400',
  route_import: 'bg-violet-500/10 text-violet-400',
  species_add: 'bg-emerald-500/10 text-emerald-400',
  review: 'bg-cyan-500/10 text-cyan-400',
  upload: 'bg-amber-500/10 text-amber-400',
}

function formatRelativeTime(timestamp, isZh) {
  if (!timestamp) return '--'
  const diff = Date.now() - new Date(timestamp).getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return isZh ? '刚刚' : 'Just now'
  if (minutes < 60) return isZh ? `${minutes}分钟前` : `${minutes}m ago`
  if (hours < 24) return isZh ? `${hours}小时前` : `${hours}h ago`
  if (days < 7) return isZh ? `${days}天前` : `${days}d ago`
  return new Date(timestamp).toLocaleDateString()
}

export default function ActivityFeed({ activities = [], locale = 'en', maxItems = 10 }) {
  const isZh = locale === 'zh'
  const displayed = activities.slice(0, maxItems)

  if (displayed.length === 0) {
    return (
      <div className="card-padded">
        <h3 className="text-sm font-semibold text-white mb-3">
          {isZh ? '最近活动' : 'Recent Activity'}
        </h3>
        <p className="text-xs text-white/25 text-center py-6">
          {isZh ? '暂无活动记录' : 'No recent activity'}
        </p>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <div className="border-b border-white/[0.06] px-4 py-3">
        <h3 className="text-sm font-semibold text-white">
          {isZh ? '最近活动' : 'Recent Activity'}
        </h3>
      </div>
      <div className="divide-y divide-white/[0.04]">
        {displayed.map((activity, i) => {
          const Icon = ACTIVITY_ICONS[activity.type] || Bird
          const colorClass = ACTIVITY_COLORS[activity.type] || 'bg-white/[0.06] text-white/40'

          return (
            <div key={activity.id || i} className="flex items-start gap-3 px-4 py-3">
              <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${colorClass}`}>
                <Icon className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-white/70">{activity.message || activity.description}</p>
                {activity.detail && (
                  <p className="mt-0.5 text-xs text-white/30 truncate">{activity.detail}</p>
                )}
              </div>
              <span className="shrink-0 text-xs text-white/20">
                {formatRelativeTime(activity.timestamp, isZh)}
              </span>
            </div>
          )
        })}
      </div>
      {activities.length > maxItems && (
        <div className="border-t border-white/[0.06] px-4 py-2 text-center">
          <span className="text-xs text-white/25">
            +{activities.length - maxItems} {isZh ? '更多' : 'more'}
          </span>
        </div>
      )}
    </div>
  )
}
