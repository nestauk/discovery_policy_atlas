'use client'

import React from 'react'
import { Badge } from '@/components/ui/badge'
import type { OutcomeTheme } from '@/types/search'

const verdictStyles: Record<string, string> = {
  well_evidenced_positive: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  well_evidenced_negative: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  evidenced_positive: 'bg-green-50 text-green-700 border-green-200',
  evidenced_negative: 'bg-green-50 text-green-700 border-green-200',
  suggested_positive: 'bg-lime-50 text-lime-700 border-lime-200',
  suggested_negative: 'bg-lime-50 text-lime-700 border-lime-200',
  contested: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  no_effect: 'bg-slate-50 text-slate-700 border-slate-200',
  insufficient_evidence: 'bg-slate-50 text-slate-700 border-slate-200',
  probable_contribution: 'bg-blue-50 text-blue-700 border-blue-200',
}

const toLabel = (value?: string) =>
  value ? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''

const causalityExplanations: Record<string, string> = {
  attribution: 'evidence supports a causal claim attributable to the intervention',
  contribution: 'evidence suggests the intervention contributed but was not solely causal',
  correlation: 'evidence shows association without a causal claim'
}

const magnitudeExplanations: Record<string, string> = {
  transformational: 'very large, potentially paradigm-shifting effect size',
  substantial: 'large effect size with meaningful practical impact',
  moderate: 'moderate effect size with practical significance',
  marginal: 'small effect size with limited practical impact',
  unknown: 'insufficient data to estimate magnitude'
}

interface ImpactProfileCardProps {
  outcome: OutcomeTheme
}

function DirectionBar({
  positiveCount,
  negativeCount,
  nullCount,
}: {
  positiveCount: number
  negativeCount: number
  nullCount: number
}) {
  const total = positiveCount + negativeCount + nullCount
  if (total <= 0) {
    return null
  }

  const positivePct = (positiveCount / total) * 100
  const negativePct = (negativeCount / total) * 100
  const nullPct = Math.max(0, 100 - positivePct - negativePct)

  return (
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
  )
}

export function ImpactProfileCard({ outcome }: ImpactProfileCardProps) {
  const verdictLabel = outcome.verdict_label
  const verdictKey = verdictLabel
    ? verdictLabel.replace('_increase', '_positive').replace('_decrease', '_negative')
    : undefined
  const magnitudeLabel = outcome.predicted_magnitude
  const causalLabel = outcome.primary_causal_mechanism

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-6 space-y-4">
      {/* Header with outcome name and verdict badge */}
      <div className="flex items-start justify-between gap-4">
        <h4 className="text-lg font-semibold text-gray-900">
          {outcome.outcome_name}
        </h4>
        {verdictKey && (
          <Badge
            variant="outline"
            className={`shrink-0 ${verdictStyles[verdictKey] || 'bg-slate-50 text-slate-700 border-slate-200'}`}
          >
            {toLabel(verdictKey)}
          </Badge>
        )}
      </div>

      {/* Outcome description */}
      {outcome.outcome_description && (
        <p className="text-gray-700 leading-relaxed">
          {outcome.outcome_description}
        </p>
      )}

      {/* Causality, Magnitude, Contested - each on its own line */}
      <div className="space-y-2">
        {causalLabel && (
          <p className="text-gray-700">
            <span className="font-medium">Causality:</span>{' '}
            {toLabel(causalLabel)}{' '}
            ({causalityExplanations[causalLabel] || 'causal strength of the evidence'})
          </p>
        )}
        {magnitudeLabel && (
          <p className="text-gray-700">
            <span className="font-medium">Magnitude:</span>{' '}
            {toLabel(magnitudeLabel)}{' '}
            ({magnitudeExplanations[magnitudeLabel] || 'estimated effect size category'})
          </p>
        )}
        {/* Direction - show for contested or when there's directional evidence */}
        {((outcome.positive_count ?? 0) > 0 || (outcome.negative_count ?? 0) > 0) && (
          <p className="text-gray-700">
            <span className="font-medium">Direction:</span>{' '}
            {outcome.verdict_description || outcome.discord_reason || 'Evidence on effect direction.'}
            {' '}({outcome.positive_count ?? 0}↑ vs {outcome.negative_count ?? 0}↓)
          </p>
        )}
      </div>

      {/* Direction bar (green/yellow/red) */}
      <DirectionBar
        positiveCount={outcome.positive_count ?? 0}
        negativeCount={outcome.negative_count ?? 0}
        nullCount={outcome.null_count ?? 0}
      />

      {/* Verdict description - only show if no directional evidence (Direction line handles it otherwise) */}
      {outcome.verdict_description && (outcome.positive_count ?? 0) === 0 && (outcome.negative_count ?? 0) === 0 && (
        <p className="text-gray-600">
          {outcome.verdict_description}
        </p>
      )}
    </div>
  )
}
