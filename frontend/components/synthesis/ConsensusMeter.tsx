import React from 'react'

interface ConsensusMeterProps {
  positiveCount: number
  negativeCount: number
  nullCount: number
  sourceCount?: number
}

const formatPercent = (value: number): string => {
  if (!Number.isFinite(value)) {
    return '0%'
  }
  return `${Math.round(value)}%`
}

export function ConsensusMeter({
  positiveCount,
  negativeCount,
  nullCount,
  sourceCount
}: ConsensusMeterProps) {
  const total = positiveCount + negativeCount + nullCount
  if (total <= 0) {
    return (
      <div className="text-xs text-slate-500">No directional evidence</div>
    )
  }

  const positivePct = (positiveCount / total) * 100
  const negativePct = (negativeCount / total) * 100
  const nullPct = Math.max(0, 100 - positivePct - negativePct)

  return (
    <div className="space-y-1">
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="flex h-full w-full">
          <div
            className="h-full bg-emerald-400"
            style={{ width: `${positivePct}%` }}
          />
          <div
            className="h-full bg-amber-300"
            style={{ width: `${nullPct}%` }}
          />
          <div
            className="h-full bg-rose-400"
            style={{ width: `${negativePct}%` }}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        {sourceCount !== undefined && <span>Sources: {sourceCount}</span>}
        <span>Weight: {total}</span>
        <span>{positiveCount}↑ ({formatPercent(positivePct)})</span>
        <span>{nullCount}— ({formatPercent(nullPct)})</span>
        <span>{negativeCount}↓ ({formatPercent(negativePct)})</span>
      </div>
    </div>
  )
}
