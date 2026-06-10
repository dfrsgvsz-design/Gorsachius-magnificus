import React from 'react'
import { formatBytes } from '../../lib/surveyOffline'

/**
 * Media inbox list showing recently captured attachments.
 * Extracted from FieldOpsTab.jsx lines 3594-3611.
 */
export default function MediaInboxPanel({ copy, mediaInbox }) {
  return (
    <div className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-white">{copy.media}</h3>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">{mediaInbox.length}</span>
      </div>
      {mediaInbox.length === 0 ? (
        <p className="text-[13px] text-white/25">{copy.queueEmpty}</p>
      ) : (
        <div className="max-h-52 overflow-y-auto rounded-2xl border border-white/[0.06] bg-white/[0.02]">
          {mediaInbox.slice(-8).reverse().map((item, idx) => (
            <div key={item.media_id} className={`px-4 py-[10px] ${idx < Math.min(mediaInbox.length, 8) - 1 ? 'border-b border-white/[0.04]' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[14px] text-white">{item.name}</span>
                <span className="shrink-0 text-[12px] text-white/30">{formatBytes(item.size)}</span>
              </div>
              <p className="mt-0.5 text-[11px] text-white/20">{item.type}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
