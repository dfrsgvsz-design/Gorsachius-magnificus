import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  CloudOff,
  HardDrive,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  Wifi,
  WifiOff,
} from 'lucide-react'

const SYNC_STATES = {
  idle: { label: 'Synced', labelZh: '已同步', icon: CheckCircle2, color: 'success' },
  syncing: { label: 'Syncing…', labelZh: '同步中…', icon: Loader2, color: 'info', spin: true },
  pending: { label: 'Changes pending', labelZh: '有待同步变更', icon: Cloud, color: 'warning' },
  offline: { label: 'Offline mode', labelZh: '离线模式', icon: CloudOff, color: 'warning' },
  error: { label: 'Sync error', labelZh: '同步错误', icon: AlertTriangle, color: 'danger' },
  conflict: { label: 'Conflicts detected', labelZh: '检测到冲突', icon: AlertTriangle, color: 'danger' },
}

const COLOR_MAP = {
  success: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  info: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
  warning: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  danger: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' },
}

export default function OfflineSyncPanel({
  locale = 'en',
  syncQueue = [],
  conflicts = [],
  lastPullAt,
  lastPushAt,
  isOnline = true,
  onPush,
  onPull,
  onResolveConflict,
  onClearQueue,
}) {
  const isZh = locale === 'zh'
  const [syncing, setSyncing] = useState(false)

  let syncState = 'idle'
  if (!isOnline) syncState = 'offline'
  else if (conflicts.length > 0) syncState = 'conflict'
  else if (syncing) syncState = 'syncing'
  else if (syncQueue.length > 0) syncState = 'pending'

  const state = SYNC_STATES[syncState]
  const colors = COLOR_MAP[state.color]
  const StateIcon = state.icon

  const handlePush = useCallback(async () => {
    if (!onPush || syncing) return
    setSyncing(true)
    try {
      await onPush()
    } finally {
      setSyncing(false)
    }
  }, [onPush, syncing])

  const handlePull = useCallback(async () => {
    if (!onPull || syncing) return
    setSyncing(true)
    try {
      await onPull()
    } finally {
      setSyncing(false)
    }
  }, [onPull, syncing])

  const formatTime = (ts) => {
    if (!ts) return '--:--'
    return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(ts))
  }

  return (
    <div className="card-padded space-y-4">
      {/* Status header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`rounded-lg p-2 ${colors.bg}`}>
            <StateIcon className={`h-4 w-4 ${colors.text} ${state.spin ? 'animate-spin' : ''}`} />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">
              {isZh ? state.labelZh : state.label}
            </p>
            <p className="text-xs text-white/30">
              {syncQueue.length > 0
                ? (isZh ? `${syncQueue.length} 项待同步` : `${syncQueue.length} pending`)
                : (isZh ? '所有数据已同步' : 'All data synced')
              }
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs ${
            isOnline ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
          }`}>
            {isOnline ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
            {isOnline ? (isZh ? '在线' : 'Online') : (isZh ? '离线' : 'Offline')}
          </div>
        </div>
      </div>

      {/* Sync info */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-white/25">
            {isZh ? '上次拉取' : 'Last Pull'}
          </p>
          <p className="mt-1 text-sm font-medium text-white/70">{formatTime(lastPullAt)}</p>
        </div>
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-white/25">
            {isZh ? '上次推送' : 'Last Push'}
          </p>
          <p className="mt-1 text-sm font-medium text-white/70">{formatTime(lastPushAt)}</p>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={handlePull}
          disabled={!isOnline || syncing}
          className="btn-secondary btn-sm flex-1 disabled:opacity-40"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
          {isZh ? '拉取更新' : 'Pull Updates'}
        </button>
        <button
          onClick={handlePush}
          disabled={!isOnline || syncing || syncQueue.length === 0}
          className="btn-primary btn-sm flex-1 disabled:opacity-40"
        >
          <Upload className="h-3.5 w-3.5" />
          {isZh ? '推送数据' : 'Push Data'}
          {syncQueue.length > 0 && (
            <span className="ml-1 rounded-full bg-white/20 px-1.5 text-[10px]">{syncQueue.length}</span>
          )}
        </button>
      </div>

      {/* Sync queue */}
      {syncQueue.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-white/40">
              {isZh ? '待同步队列' : 'Sync Queue'}
            </p>
            {onClearQueue && (
              <button onClick={onClearQueue} className="text-xs text-red-400 hover:text-red-300">
                <Trash2 className="inline h-3 w-3 mr-1" />
                {isZh ? '清空' : 'Clear'}
              </button>
            )}
          </div>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {syncQueue.slice(0, 10).map((item, i) => (
              <div key={i} className="sync-queue-item">
                <HardDrive className="h-3.5 w-3.5 text-white/25 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-white/60 truncate">{item.type || item.action || 'change'}</p>
                </div>
                <span className={`sync-type-badge ${
                  item.type === 'observation' ? 'bg-emerald-500/15 text-emerald-400'
                    : item.type === 'track' ? 'bg-cyan-500/15 text-cyan-400'
                    : 'bg-white/[0.06] text-white/40'
                }`}>
                  {item.type || 'data'}
                </span>
              </div>
            ))}
            {syncQueue.length > 10 && (
              <p className="text-center text-xs text-white/25">
                +{syncQueue.length - 10} {isZh ? '更多' : 'more'}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Conflicts */}
      {conflicts.length > 0 && (
        <div className={`rounded-lg border p-3 ${COLOR_MAP.danger.border} ${COLOR_MAP.danger.bg}`}>
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            <p className="text-sm font-medium text-red-400">
              {isZh ? `${conflicts.length} 个冲突需要解决` : `${conflicts.length} conflict(s) need resolution`}
            </p>
          </div>
          <div className="space-y-2">
            {conflicts.slice(0, 5).map((conflict, i) => (
              <div key={i} className="flex items-center justify-between rounded-md bg-red-500/10 p-2.5">
                <p className="text-xs text-red-300 truncate">{conflict.description || conflict.id}</p>
                {onResolveConflict && (
                  <button
                    onClick={() => onResolveConflict(conflict)}
                    className="btn-sm text-xs text-red-400 hover:text-red-300 shrink-0"
                  >
                    {isZh ? '解决' : 'Resolve'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Storage info */}
      <div className="flex items-center gap-2 text-xs text-white/20">
        <HardDrive className="h-3 w-3" />
        {isZh ? '数据存储在设备本地，联网后自动同步' : 'Data stored locally, syncs when online'}
      </div>
    </div>
  )
}
