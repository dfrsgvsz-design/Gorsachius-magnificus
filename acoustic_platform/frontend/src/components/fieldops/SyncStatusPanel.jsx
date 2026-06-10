import React from 'react'
import { AlertTriangle } from 'lucide-react'
import MetricCard from './MetricCard'

export default function SyncStatusPanel({ copy, surveyState }) {
  return (
    <div className="section-shell space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{copy.sync}</h3>
        <span className="text-xs text-gray-400">{surveyState.syncQueue.length} queued</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard title="Queued" value={surveyState.syncQueue.length} note={surveyState.syncMeta?.lastStatus || 'idle'} />
        <MetricCard title="Pulled" value={surveyState.syncMeta?.lastPulledAt ? 'yes' : 'no'} note={surveyState.syncMeta?.lastPulledAt || '--'} />
        <MetricCard title={copy.conflicts} value={surveyState.conflicts.length} note={surveyState.syncMeta?.lastError || '--'} />
      </div>
      {surveyState.syncQueue.length === 0 ? (
        <p className="text-xs text-gray-500">{copy.queueEmpty}</p>
      ) : (
        <div className="max-h-48 space-y-2 overflow-y-auto">
          {surveyState.syncQueue.slice(-10).reverse().map((item) => (
            <div key={item.op_id} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-300">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-white">{item.entity_type}</span>
                <span>{item.operation}</span>
              </div>
              <p className="mt-1 text-gray-500">{item.queued_at}</p>
            </div>
          ))}
        </div>
      )}
      {surveyState.conflicts.length > 0 && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-100">
          <div className="mb-2 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-300" />
            {copy.conflicts}
          </div>
          {surveyState.conflicts.slice(0, 3).map((item) => (
            <p key={item.conflict_id} className="text-xs text-amber-200/90">
              {item.entity_type}:{' '}
              {Array.isArray(item.fields) ? item.fields.join(', ') : ''}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
