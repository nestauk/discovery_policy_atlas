'use client'

import React from 'react'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { ConsensusMeter } from '@/components/synthesis/ConsensusMeter'
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

const magnitudeStyles: Record<string, string> = {
  transformational: 'bg-purple-50 text-purple-700 border-purple-200',
  substantial: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  moderate: 'bg-blue-50 text-blue-700 border-blue-200',
  marginal: 'bg-slate-50 text-slate-700 border-slate-200',
  unknown: 'bg-slate-50 text-slate-600 border-slate-200',
}

const toLabel = (value?: string) =>
  value ? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''

const scaleLabelMap: Record<string, string> = {
  cohens_d: "Cohen's d",
  smd: 'SMD',
  or: 'Odds ratio',
  rr: 'Risk ratio',
  percentage: 'Percentage points',
  percent: 'Percent',
}

interface ImpactProfileCardProps {
  outcome: OutcomeTheme
}

export function ImpactProfileCard({ outcome }: ImpactProfileCardProps) {
  const verdictLabel = outcome.verdict_label
  const verdictKey = verdictLabel
    ? verdictLabel.replace('_increase', '_positive').replace('_decrease', '_negative')
    : undefined
  const magnitudeLabel = outcome.predicted_magnitude
  const causalLabel = outcome.primary_causal_mechanism
  const magnitudeDetail = outcome.magnitude_detail
  const causalityDetail = outcome.causal_mechanism_detail
  const sourceCount =
    outcome.source_doc_ids?.length ?? outcome.frequency ?? undefined

  const verdictTooltips: Record<string, string> = {
    well_evidenced_positive: 'Strong, consistent evidence supports a beneficial effect.',
    well_evidenced_negative: 'Strong, consistent evidence supports a harmful effect.',
    evidenced_positive: 'Moderate evidence supports a beneficial effect.',
    evidenced_negative: 'Moderate evidence supports a harmful effect.',
    suggested_positive: 'Limited evidence suggests a beneficial effect.',
    suggested_negative: 'Limited evidence suggests a harmful effect.',
    contested: 'Evidence is split between beneficial and harmful effects.',
    no_effect: 'Evidence suggests no consistent effect.',
    insufficient_evidence: 'Too little evidence to determine effect direction.',
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

  const buildMagnitudeTooltip = () => {
    if (!magnitudeDetail) {
      return magnitudeTooltips[magnitudeLabel || 'unknown'] || 'Estimated effect size category'
    }
    const directionLabel = toLabel(magnitudeDetail.direction)
    const bucketText = Object.entries(magnitudeDetail.bucket_counts || {})
      .map(([bucket, count]) => `${toLabel(bucket)}: ${count}`)
      .join(', ')
    const sourcesText = `${magnitudeDetail.source_count} of ${magnitudeDetail.total_sources} studies had quantitative effect data`
    const measurementsText = `${magnitudeDetail.measurement_count} measurements`
    const thresholdsText = magnitudeDetail.thresholds
    const scaleLabel =
      scaleLabelMap[magnitudeDetail.dominant_scale] ||
      toLabel(magnitudeDetail.dominant_scale)
    const parts = [
      directionLabel ? `Direction: ${directionLabel}.` : '',
      bucketText ? `Buckets: ${bucketText}.` : '',
      sourcesText ? `${sourcesText}.` : '',
      measurementsText ? `${measurementsText}.` : '',
      thresholdsText
        ? `Thresholds${scaleLabel ? ` (${scaleLabel})` : ''}: ${thresholdsText}.`
        : ''
    ].filter(Boolean)
    return parts.join(' ')
  }

  const buildCausalityTooltip = () => {
    if (!causalityDetail) {
      return causalityTooltips[causalLabel || 'correlation'] || 'Causal strength of the evidence'
    }
    const parts = [
      causalityDetail.attribution
        ? `${causalityDetail.attribution} source${causalityDetail.attribution === 1 ? '' : 's'} support attribution`
        : '',
      causalityDetail.contribution
        ? `${causalityDetail.contribution} source${causalityDetail.contribution === 1 ? '' : 's'} support contribution`
        : '',
      causalityDetail.correlation
        ? `${causalityDetail.correlation} source${causalityDetail.correlation === 1 ? '' : 's'} support correlation`
        : ''
    ].filter(Boolean)
    return parts.length ? parts.join(', ') : 'No causal claims reported.'
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
        {verdictKey && (
          <Tooltip content={verdictTooltips[verdictKey] || 'Impact verdict label'}>
            <Badge
              variant="outline"
              className={`text-xs ${verdictStyles[verdictKey] || 'bg-slate-50 text-slate-700 border-slate-200'}`}
            >
              {toLabel(verdictKey)}
            </Badge>
          </Tooltip>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {causalLabel && (
          <Tooltip content={buildCausalityTooltip()}>
            <Badge variant="outline" className="text-xs bg-white">
              Causality: {toLabel(causalLabel)}
            </Badge>
          </Tooltip>
        )}
        {magnitudeLabel && (
          <Tooltip content={buildMagnitudeTooltip()}>
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
        sourceCount={sourceCount}
      />

      {outcome.verdict_description && (
        <div className="text-xs text-slate-600">
          {outcome.verdict_description}
        </div>
      )}
    </div>
  )
}
