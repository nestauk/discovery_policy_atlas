'use client'

import React, { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { getEvidenceCategoryRank } from '@/lib/evidenceCategories'
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

const normaliseValue = (value?: string | null) => {
  if (!value) return ''
  const trimmed = value.trim()
  if (!trimmed || trimmed.toLowerCase() === 'null' || trimmed.toLowerCase() === 'none') {
    return ''
  }
  return trimmed
}

const classifyContribution = (result: ContributionResult) => {
  const direction = (result.effect_direction || '').toLowerCase().trim()
  if (direction === 'no effect' || direction === 'null' || direction === 'none') {
    return 'neutral'
  }
  if (typeof result.is_beneficial === 'boolean') {
    return result.is_beneficial ? 'positive' : 'negative'
  }
  if (direction === 'increase') return 'positive'
  if (direction === 'decrease') return 'negative'
  return 'neutral'
}

interface ImpactProfileCardProps {
  outcome: OutcomeTheme
}

interface ContributionResult {
  extraction_id?: string
  outcome_variable?: string
  effect_direction?: string
  magnitude_estimate?: string
  calibrated_magnitude?: string
  effect_size?: string
  effect_size_type?: string
  uncertainty?: string
  p_value?: string
  population_measured?: string
  subgroup_or_dose?: string
  causality_claim?: string
  is_primary?: boolean
  is_beneficial?: boolean
  result_text?: string
  supporting_quote?: string
}

interface ContributionDocument {
  analysis_document_id: string
  doc_id?: string
  title?: string
  source?: string
  landing_page_url?: string
  doi?: string
  year?: number
  evidence_category?: string
  evidence_score?: number | null
  results: ContributionResult[]
}

interface ContributionPayload {
  documents: ContributionDocument[]
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
  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth } = useAPI()
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [contributions, setContributions] = useState<ContributionPayload | null>(null)

  const canLoadContributions = Boolean(activeProject?.id && outcome.id)
  const consensusTotal =
    (outcome.positive_count ?? 0) +
    (outcome.negative_count ?? 0) +
    (outcome.null_count ?? 0)
  const totalContributions = useMemo(
    () =>
      contributions?.documents?.reduce(
        (sum, doc) => sum + (doc.results?.length || 0),
        0
      ) ?? 0,
    [contributions]
  )
  const orderedDocuments = useMemo(() => {
    if (!contributions?.documents) return []
    return [...contributions.documents].sort((a, b) => {
      const aScore = a.evidence_score ?? -1
      const bScore = b.evidence_score ?? -1
      if (aScore !== bScore) {
        return bScore - aScore
      }
      const aRank = a.evidence_category ? getEvidenceCategoryRank(a.evidence_category) : 999
      const bRank = b.evidence_category ? getEvidenceCategoryRank(b.evidence_category) : 999
      if (aRank !== bRank) {
        return aRank - bRank
      }
      return (a.title || '').localeCompare(b.title || '')
    })
  }, [contributions])
  const groupedDocuments = useMemo(() => {
    const buckets: Record<'positive' | 'neutral' | 'negative', ContributionDocument[]> = {
      positive: [],
      neutral: [],
      negative: [],
    }
    orderedDocuments.forEach((doc) => {
      const bucketedResults: Record<'positive' | 'neutral' | 'negative', ContributionResult[]> = {
        positive: [],
        neutral: [],
        negative: [],
      }
      doc.results.forEach((result) => {
        const bucket = classifyContribution(result)
        bucketedResults[bucket].push(result)
      })
      ;(['positive', 'neutral', 'negative'] as const).forEach((bucket) => {
        if (bucketedResults[bucket].length) {
          buckets[bucket].push({ ...doc, results: bucketedResults[bucket] })
        }
      })
    })
    return buckets
  }, [orderedDocuments])
  const bucketCounts = useMemo(() => {
    return {
      positive: groupedDocuments.positive.reduce((sum, doc) => sum + doc.results.length, 0),
      neutral: groupedDocuments.neutral.reduce((sum, doc) => sum + doc.results.length, 0),
      negative: groupedDocuments.negative.reduce((sum, doc) => sum + doc.results.length, 0),
    }
  }, [groupedDocuments])

  const toggleContributions = async () => {
    const next = !expanded
    setExpanded(next)
    setError(null)
    if (!next || contributions || loading || !canLoadContributions) {
      return
    }
    setLoading(true)
    try {
      const response = await fetchWithAuth(
        `/api/analysis-projects/${activeProject?.id}/synthesis/outcome-themes/${outcome.id}/contributions`
      )
      setContributions(response as ContributionPayload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load contributions')
    } finally {
      setLoading(false)
    }
  }

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
            className={`shrink-0 text-sm ${verdictStyles[verdictKey] || 'bg-slate-50 text-slate-700 border-slate-200'}`}
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

      <div className="pt-1">
        <button
          type="button"
          className="text-sm font-medium text-blue-600 hover:text-blue-700"
          onClick={toggleContributions}
          disabled={!canLoadContributions}
        >
          {expanded
            ? 'Hide contributing outcomes'
            : 'Show contributing outcomes'}
        </button>
      </div>

      {expanded && (
        <div className="space-y-4 border-t border-gray-100 pt-4">
          {!canLoadContributions && (
            <p className="text-sm text-gray-500">Outcome details unavailable for this item.</p>
          )}
          {canLoadContributions && loading && (
            <p className="text-sm text-gray-500">Loading contributing outcomes...</p>
          )}
          {canLoadContributions && error && (
            <p className="text-sm text-rose-600">{error}</p>
          )}
          {canLoadContributions && !loading && !error && (
            <>
              {consensusTotal > 0 && (
                <p className="text-xs text-gray-500">
                  Consensus meter uses evidence-strength-weighted counts ({outcome.positive_count ?? 0}↑ {outcome.negative_count ?? 0}↓ {outcome.null_count ?? 0}—).
                  The list shows raw extractions ({totalContributions}).
                </p>
              )}
              {contributions?.documents?.length ? (
                <div className="space-y-6">
                  {[
                    {
                      key: 'positive',
                      label: 'Positive outcomes',
                      className: 'text-emerald-700',
                      documents: groupedDocuments.positive,
                      count: bucketCounts.positive,
                    },
                    {
                      key: 'neutral',
                      label: 'Neutral outcomes',
                      className: 'text-amber-700',
                      documents: groupedDocuments.neutral,
                      count: bucketCounts.neutral,
                    },
                    {
                      key: 'negative',
                      label: 'Negative outcomes',
                      className: 'text-rose-700',
                      documents: groupedDocuments.negative,
                      count: bucketCounts.negative,
                    },
                  ].map((section) =>
                    section.documents.length ? (
                      <div key={section.key} className="space-y-3">
                        <div className={`text-sm font-semibold ${section.className}`}>
                          {section.label} ({section.count})
                        </div>
                        <div className="space-y-4">
                          {section.documents.map((doc) => (
                            <div key={`${section.key}-${doc.analysis_document_id}`} className="rounded-lg border border-gray-100 p-4">
                              <div className="space-y-1">
                                {doc.title ? (
                                  doc.landing_page_url ? (
                                    <a
                                      className="text-sm font-semibold text-blue-700 hover:text-blue-800"
                                      href={doc.landing_page_url}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      {doc.title}
                                    </a>
                                  ) : (
                                    <p className="text-sm font-semibold text-gray-900">{doc.title}</p>
                                  )
                                ) : (
                                  <p className="text-sm font-semibold text-gray-900">Untitled document</p>
                                )}
                                <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                                  {doc.source && <span>{doc.source}</span>}
                                  {doc.year && <span>{doc.year}</span>}
                                  {doc.evidence_category && <span>{doc.evidence_category}</span>}
                                  {doc.doc_id && <span>Doc ID: {doc.doc_id}</span>}
                                </div>
                              </div>

                              <div className="mt-3 space-y-3">
                                {doc.results.map((result, idx) => {
                                  const effectSize = normaliseValue(result.effect_size)
                                  const effectSizeType = normaliseValue(result.effect_size_type)
                                  const magnitudeValue =
                                    result.calibrated_magnitude || result.magnitude_estimate
                                  return (
                                    <div key={`${section.key}-${doc.analysis_document_id}-${idx}`} className="rounded-md bg-gray-50 p-3">
                                      <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-gray-900">
                                        <span>{result.outcome_variable || 'Outcome'}</span>
                                        {result.effect_direction && (
                                          <Badge variant="outline" className="text-xs">
                                            {toLabel(result.effect_direction)}
                                          </Badge>
                                        )}
                                        {magnitudeValue && (
                                          <Badge variant="outline" className="text-xs">
                                            Magnitude: {toLabel(magnitudeValue)}
                                          </Badge>
                                        )}
                                        {effectSize && (
                                          <span className="text-xs text-gray-600">
                                            {effectSize}{effectSizeType ? ` (${effectSizeType})` : ''}
                                          </span>
                                        )}
                                      </div>
                                      <div className="mt-2 space-y-1 text-xs text-gray-600">
                                        {result.causality_claim && (
                                          <p>
                                            <span className="font-medium text-gray-700">Causality:</span>{' '}
                                            {toLabel(result.causality_claim)}
                                          </p>
                                        )}
                                        {typeof result.is_primary === 'boolean' && (
                                          <p>
                                            <span className="font-medium text-gray-700">Primary outcome:</span>{' '}
                                            {result.is_primary ? 'Yes' : 'No'}
                                          </p>
                                        )}
                                        {normaliseValue(result.population_measured) && (
                                          <p>
                                            <span className="font-medium text-gray-700">Population:</span>{' '}
                                            {normaliseValue(result.population_measured)}
                                          </p>
                                        )}
                                        {normaliseValue(result.subgroup_or_dose) && (
                                          <p>
                                            <span className="font-medium text-gray-700">Subgroup/dose:</span>{' '}
                                            {normaliseValue(result.subgroup_or_dose)}
                                          </p>
                                        )}
                                        {normaliseValue(result.uncertainty) && (
                                          <p>
                                            <span className="font-medium text-gray-700">Uncertainty:</span>{' '}
                                            {normaliseValue(result.uncertainty)}
                                          </p>
                                        )}
                                        {normaliseValue(result.p_value) && (
                                          <p>
                                            <span className="font-medium text-gray-700">P-value:</span>{' '}
                                            {normaliseValue(result.p_value)}
                                          </p>
                                        )}
                                      </div>
                                      {result.supporting_quote && (
                                        <blockquote className="mt-2 border-l-2 border-gray-200 pl-3 text-xs italic text-gray-500">
                                          {result.supporting_quote}
                                        </blockquote>
                                      )}
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-500">No contributing outcomes available.</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
