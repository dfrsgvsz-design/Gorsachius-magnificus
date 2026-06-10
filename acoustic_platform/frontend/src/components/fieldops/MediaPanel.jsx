import React from 'react'
import { formatBytes } from '../../lib/surveyOffline'

export default function MediaPanel({ copy, mediaInbox }) {
  return (
    <div className="section-shell space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{copy.media}</h3>
        <span className="text-xs text-gray-400">{mediaInbox.length}</span>
      </div>
      <div className="max-h-52 space-y-2 overflow-y-auto">
        {mediaInbox.length === 0 && <p className="text-xs text-gray-500">{copy.queueEmpty}</p>}
        {mediaInbox.slice(-8).reverse().map((item) => (
          <div key={item.media_id} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-300">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-white">{item.name}</span>
              <span>{formatBytes(item.size)}</span>
            </div>
            <p className="mt-1 text-gray-500">{item.type}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
