import React from 'react'
import { AlertTriangle } from 'lucide-react'
import MetricCard from './MetricCard'

/**
 * Sync queue and conflict display panel.
 * Extracted from FieldOpsTab.jsx lines 3613-3652.
 */
export default function SyncPanel({ copy, surveyState, locale = 'zh' }) {
  const isZh = locale === 'zh'
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-white">{copy.sync}</h3>
        <span
          data-testid="sync-pending-count"
          data-count={surveyState.syncQueue.length}
          className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40"
        >
          {surveyState.syncQueue.length} {isZh ? '待同步' : 'queued'}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <MetricCard title={isZh ? '排队中' : 'Queued'} value={surveyState.syncQueue.length} note={surveyState.syncMeta?.lastStatus || (isZh ? '空闲' : 'idle')} />
        <MetricCard title={isZh ? '已拉取' : 'Pulled'} value={surveyState.syncMeta?.lastPulledAt ? (isZh ? '是' : 'yes') : (isZh ? '否' : 'no')} note={surveyState.syncMeta?.lastPulledAt || '--'} />
        <div data-testid="sync-conflict-count" data-count={surveyState.conflicts.length}>
          <MetricCard title={copy.conflicts} value={surveyState.conflicts.length} note={surveyState.syncMeta?.lastError || '--'} />
        </div>
      </div>
      {surveyState.syncQueue.length === 0 ? (
        <p className="text-[13px] text-white/25">{copy.queueEmpty}</p>
      ) : (
        <div className="max-h-48 overflow-y-auto rounded-2xl border border-white/[0.06] bg-white/[0.02]">
          {surveyState.syncQueue.slice(-10).reverse().map((item, idx) => (
            <div key={item.op_id} className={`px-4 py-[10px] ${idx < Math.min(surveyState.syncQueue.length, 10) - 1 ? 'border-b border-white/[0.04]' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[14px] font-medium text-white">{item.entity_type}</span>
                <span className="text-[12px] text-white/30">{item.operation}</span>
              </div>
              <p className="mt-0.5 text-[11px] text-white/20">{item.queued_at}</p>
            </div>
          ))}
        </div>
      )}
      {surveyState.conflicts.length > 0 && (
        <div className="rounded-[14px] bg-[#FF9F0A]/10 px-4 py-3">
          <div className="mb-2 flex items-center gap-2 text-[14px] font-medium text-[#FF9F0A]">
            <AlertTriangle className="h-4 w-4" />
            {copy.conflicts}
          </div>
          {surveyState.conflicts.slice(0, 3).map((item) => (
            <p key={item.conflict_id} className="text-[12px] text-[#FF9F0A]/70">
              {item.entity_type}:{' '}
              {Array.isArray(item.fields) ? item.fields.join(', ') : ''}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
