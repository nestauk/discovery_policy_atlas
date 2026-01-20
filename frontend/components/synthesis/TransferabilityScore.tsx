'use client'

import React, { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import type { TransferabilityBreakdown } from '@/types/search'

const ratingStyles: Record<string, string> = {
  'High Fit': 'bg-green-50 text-green-700 border-green-200',
  'Medium Fit': 'bg-yellow-50 text-yellow-700 border-yellow-200',
  'Low Fit': 'bg-red-50 text-red-700 border-red-200',
  Unknown: 'bg-slate-50 text-slate-600 border-slate-200',
}

const dimensionOrder = [
  'inner_setting',
  'population',
  'geography',
  'resource_intensity',
  'delivery_complexity',
] as const

const toLabel = (value?: string) =>
  value ? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''

interface TransferabilityScoreProps {
  rating?: string | null
  note?: string | null
  breakdown?: TransferabilityBreakdown | null
}

export function TransferabilityScore({
  rating,
  note,
  breakdown,
}: TransferabilityScoreProps) {
  const [expanded, setExpanded] = useState(false)

  if (!rating && !breakdown) {
    return null
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Badge
          variant="outline"
          className={`text-xs ${ratingStyles[rating || 'Unknown'] || ratingStyles.Unknown}`}
        >
          Transferability: {rating || 'Unknown'}
        </Badge>
        <button
          type="button"
          className="text-xs text-slate-500 hover:text-slate-700"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? 'Hide details' : 'Show details'}
        </button>
      </div>

      {note && <div className="text-xs text-slate-600">{note}</div>}

      {expanded && breakdown && (
        <div className="grid gap-2 text-xs text-slate-600">
          {dimensionOrder.map((key) => {
            const value = (breakdown as Record<string, string | undefined>)[key]
            const note = breakdown.notes?.[key]
            return (
              <div key={key} className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-500">{toLabel(key)}</span>
                  <span>{toLabel(value)}</span>
                </div>
                {note && <div className="text-[11px] text-slate-400">{note}</div>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
