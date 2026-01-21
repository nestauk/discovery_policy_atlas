'use client'

import React from 'react'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { ConsensusMeter } from '@/components/synthesis/ConsensusMeter'
import type { OutcomeTheme } from '@/types/search'

const verdictStyles: Record<string, string> = {
  high_confidence_positive: 'bg-green-50 text-green-700 border-green-200',
  high_confidence_negative: 'bg-red-50 text-red-700 border-red-200',
  lean_positive: 'bg-green-50 text-green-700 border-green-200',
  lean_negative: 'bg-red-50 text-red-700 border-red-200',
  contested: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  ineffective: 'bg-slate-50 text-slate-700 border-slate-200',
  insufficient_evidence: 'bg-slate-50 text-slate-700 border-slate-200',
  probable_contribution: 'bg-blue-50 text-blue-700 border-blue-200',
}

const magnitudeStyles: Record<string, string> = {
  transformational: 'bg-purple-50 text-purple-700 border-purple-200',
  substantial: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  moderate: 'bg-blue-50 text-blue-700 border-blue-200',
  marginal: 'bg-slate-50 text-slate-700 border-slate-200',
  unknown: 'bg-slate-50 text-slate-600 border-slate-200',
}

const toLabel = (value?: string) =>
  value ? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''

interface ImpactProfileCardProps {
  outcome: OutcomeTheme
}

export function ImpactProfileCard({ outcome }: ImpactProfileCardProps) {
  const verdictLabel = outcome.verdict_label
  const magnitudeLabel = outcome.predicted_magnitude
  const causalLabel = outcome.primary_causal_mechanism

  const verdictTooltips: Record<string, string> = {
    high_confidence_positive: 'Strong, consistent evidence supports a positive impact.',
    high_confidence_negative: 'Strong, consistent evidence supports a negative impact.',
    lean_positive: 'Evidence trends positive but is not definitive.',
    lean_negative: 'Evidence trends negative but is not definitive.',
    contested: 'Evidence is split between positive and negative findings.',
    ineffective: 'Evidence suggests no consistent effect.',
    insufficient_evidence: 'Too little evidence to determine impact direction.',
    probable_contribution: 'Evidence suggests contribution without strong attribution.'
  }

  const causalityTooltips: Record<string, string> = {
    attribution: 'Evidence supports a causal claim attributable to the intervention.',
    contribution: 'Evidence suggests the intervention contributed but was not solely causal.',
    correlation: 'Evidence shows association without a causal claim.'
  }

  const magnitudeTooltips: Record<string, string> = {
    transformational: 'Very large, potentially paradigm-shifting effect size.',
    substantial: 'Large effect size with meaningful practical impact.',
    moderate: 'Moderate effect size with practical significance.',
    marginal: 'Small effect size with limited practical impact.',
    unknown: 'Insufficient data to estimate magnitude.'
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-slate-900">
            {outcome.outcome_name}
          </div>
          {outcome.outcome_description && (
            <div className="text-xs text-slate-600 mt-1">
              {outcome.outcome_description}
            </div>
          )}
        </div>
        {verdictLabel && (
          <Tooltip content={verdictTooltips[verdictLabel] || 'Impact verdict label'}>
            <Badge
              variant="outline"
              className={`text-xs ${verdictStyles[verdictLabel] || 'bg-slate-50 text-slate-700 border-slate-200'}`}
            >
              {toLabel(verdictLabel)}
            </Badge>
          </Tooltip>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {causalLabel && (
          <Tooltip content={causalityTooltips[causalLabel] || 'Causal strength of the evidence'}>
            <Badge variant="outline" className="text-xs bg-white">
              Causality: {toLabel(causalLabel)}
            </Badge>
          </Tooltip>
        )}
        {magnitudeLabel && (
          <Tooltip content={magnitudeTooltips[magnitudeLabel] || 'Estimated effect size category'}>
            <Badge
              variant="outline"
              className={`text-xs ${magnitudeStyles[magnitudeLabel] || 'bg-slate-50 text-slate-600 border-slate-200'}`}
            >
              Magnitude: {toLabel(magnitudeLabel)}
            </Badge>
          </Tooltip>
        )}
        {outcome.discord_flag && outcome.discord_reason && (
          <Tooltip content={outcome.discord_reason}>
            <Badge variant="outline" className="text-xs bg-yellow-50 text-yellow-700 border-yellow-200">
              Contested
            </Badge>
          </Tooltip>
        )}
      </div>

      <ConsensusMeter
        positiveCount={outcome.positive_count ?? 0}
        negativeCount={outcome.negative_count ?? 0}
        nullCount={outcome.null_count ?? 0}
      />

      {outcome.magnitude_confidence && (
        <div className="text-xs text-slate-500">
          {outcome.magnitude_confidence}
        </div>
      )}

      {outcome.verdict_description && (
        <div className="text-xs text-slate-600">
          {outcome.verdict_description}
        </div>
      )}
    </div>
  )
}
