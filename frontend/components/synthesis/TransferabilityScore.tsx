'use client'

import React, { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import type { TransferabilityBreakdown } from '@/types/search'

const ratingStyles: Record<string, string> = {
  'Excellent Fit': 'bg-green-50 text-green-700 border-green-200',
  'Good Fit': 'bg-green-50 text-green-700 border-green-200',
  'Moderate Fit': 'bg-yellow-50 text-yellow-700 border-yellow-200',
  'Limited Fit': 'bg-orange-50 text-orange-700 border-orange-200',
  'Poor Fit': 'bg-red-50 text-red-700 border-red-200',
  Unknown: 'bg-slate-50 text-slate-600 border-slate-200',
}

const requirementsStyles: Record<string, string> = {
  Low: 'bg-green-50 text-green-700 border-green-200',
  Medium: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  High: 'bg-red-50 text-red-700 border-red-200',
  Unknown: 'bg-slate-50 text-slate-600 border-slate-200',
}

const contextDimensions = ['inner_setting', 'population', 'geography'] as const
const implementationDimensions = [
  'cost',
  'staffing',
  'implementation_complexity',
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
  const contextRating = breakdown?.context_fit_rating || rating || 'Unknown'
  const requirementsRating =
    breakdown?.implementation_requirements_rating || 'Unknown'
  const hasAnyToleranceExceeded = Object.values(
    breakdown?.implementation_exceeds_tolerance || {},
  ).some(Boolean)

  if (!rating && !breakdown) {
    return null
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={`text-xs ${ratingStyles[contextRating] || ratingStyles.Unknown}`}
          >
            Context Fit: {contextRating}
          </Badge>
          <Badge
            variant="outline"
            className={`text-xs ${requirementsStyles[requirementsRating] || requirementsStyles.Unknown}`}
          >
            Implementation requirements: {requirementsRating}
            {hasAnyToleranceExceeded ? ' ⚠️' : ''}
          </Badge>
        </div>
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
        <div className="grid gap-3 text-xs text-slate-600">
          <div className="text-[11px] uppercase tracking-wide text-slate-400">
            Context fit
          </div>
          {contextDimensions.map((key) => {
            const value = breakdown?.[key]
            const note = breakdown?.notes?.[key]
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
          <div className="text-[11px] uppercase tracking-wide text-slate-400 pt-2">
            Implementation fit
          </div>
          {implementationDimensions.map((key) => {
            const evidenceValue = breakdown?.implementation_evidence?.[key]
            const exceedsTolerance =
              breakdown?.implementation_exceeds_tolerance?.[key]
            const note = breakdown?.notes?.[key]
            return (
              <div key={key} className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-500">{toLabel(key)}</span>
                  <span>
                    {toLabel(evidenceValue)}
                    {exceedsTolerance ? ' ⚠️' : ''}
                  </span>
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
