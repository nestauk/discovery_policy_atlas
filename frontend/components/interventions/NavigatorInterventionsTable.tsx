'use client'

import React, { useState, useMemo } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tooltip } from '@/components/ui/tooltip'
import {
  ChevronUp,
  ChevronDown,
  Target,
  AlertTriangle,
} from 'lucide-react'
import {
  getEvidenceCategoryColors,
  getEvidenceCategoryShortName,
  getEvidenceCategories,
} from '@/lib/evidenceCategories'
import { StarRating } from '@/components/ui/star-rating'

interface NavigatorInterventionData {
  name: string
  type: string
  country: string
  description: string
  evidence_category?: string
  evidence_categories?: string[]
  is_systematic_review?: boolean
  result_count: number
  results_summary: Array<{
    outcome: string
    direction: string
    effect_size?: string
    effect_size_type?: string
    p_value?: string
    uncertainty?: string
    result_text?: string
    supporting_quote?: string
    population_measured?: string
    subgroup_or_dose?: string
    // SR-specific fields for meta-analysis results
    heterogeneity_I2?: string
    tau2?: string
    summary_statistic?: string
    estimate_level?: string
    // Sample size fields
    n_studies?: number
    sample_size?: number
    // Stratum fields
    stratum_type?: string
    stratum_value?: string
    evidence_category?: string
    is_systematic_review?: boolean
  }>
  outcome_groups?: Array<{
    document: {
      doc_id: string
      title: string
      source: string
      landing_page_url?: string
      evidence_category?: string
      reported_sample_size?: number
    }
    results: NavigatorInterventionData['results_summary']
  }>
  total_sample_size: number | null
  documents: Array<{
    doc_id: string
    title: string
    source: string
    landing_page_url?: string
    evidence_category?: string
  }>
  impact_score?: number
  evidence_score?: number
  impact_justification?: string
  evidence_justification?: string
  has_harm_warning?: boolean
  harm_warning_reason?: string
}

interface NavigatorInterventionsTableProps {
  interventions: NavigatorInterventionData[]
  loading?: boolean
}

type SortField = 'name' | 'type' | 'country' | 'result_count' | 'sample_size' | 'impact_score' | 'evidence_score'
type SortDirection = 'asc' | 'desc'

export function NavigatorInterventionsTable({ interventions, loading = false }: NavigatorInterventionsTableProps) {
  const [sortField, setSortField] = useState<SortField>('evidence_score')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [showAllEvidence, setShowAllEvidence] = useState<Set<string>>(new Set())

  // Get evidence category scores for ranking
  const evidenceCategoryScores = useMemo(() => {
    const categories = getEvidenceCategories()
    return Object.fromEntries(categories.map(c => [c.name, c.score]))
  }, [])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection(field === 'impact_score' || field === 'evidence_score' ? 'desc' : 'asc')
    }
  }

  const sortedInterventions = useMemo(() => {
    return [...interventions].sort((a, b) => {
      let aValue: string | number | null
      let bValue: string | number | null

      if (sortField === 'evidence_score') {
        aValue = a.evidence_score ?? null
        bValue = b.evidence_score ?? null
      } else if (sortField === 'sample_size') {
        aValue = a.total_sample_size ?? null
        bValue = b.total_sample_size ?? null
      } else {
        aValue = a[sortField] ?? null
        bValue = b[sortField] ?? null
      }

      // Handle null values
      if (aValue === null || aValue === undefined) aValue = sortDirection === 'asc' ? Infinity : -Infinity
      if (bValue === null || bValue === undefined) bValue = sortDirection === 'asc' ? Infinity : -Infinity

      // Convert to lowercase for string comparison
      if (typeof aValue === 'string') aValue = aValue.toLowerCase()
      if (typeof bValue === 'string') bValue = bValue.toLowerCase()

      if (sortDirection === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0
      }
    })
  }, [interventions, sortField, sortDirection])

  const toggleRowExpansion = (interventionKey: string) => {
    const newExpanded = new Set(expandedRows)
    if (newExpanded.has(interventionKey)) {
      newExpanded.delete(interventionKey)
    } else {
      newExpanded.add(interventionKey)
    }
    setExpandedRows(newExpanded)
  }

  const toggleShowAllEvidence = (interventionKey: string) => {
    const newShowAll = new Set(showAllEvidence)
    if (newShowAll.has(interventionKey)) {
      newShowAll.delete(interventionKey)
    } else {
      newShowAll.add(interventionKey)
    }
    setShowAllEvidence(newShowAll)
  }

  // Split outcome groups into highest evidence and supporting evidence
  const splitOutcomeGroups = (outcomeGroups: NonNullable<NavigatorInterventionData['outcome_groups']>) => {
    if (outcomeGroups.length === 0) return { highestEvidence: [], supportingEvidence: [], supportingCategories: [] }

    // Calculate evidence score for each group based on its results' evidence categories
    const groupsWithScores = outcomeGroups.map(group => {
      // Get the highest evidence score from results in this group
      const maxScore = Math.max(
        ...group.results.map(r => evidenceCategoryScores[r.evidence_category || ''] ?? 0)
      )
      // Get the evidence category for this group (use highest scoring one)
      const category = group.results.find(r =>
        (evidenceCategoryScores[r.evidence_category || ''] ?? 0) === maxScore
      )?.evidence_category
      return { group, score: maxScore, category }
    })

    // Sort by score descending
    groupsWithScores.sort((a, b) => b.score - a.score)

    // Find the highest score
    const highestScore = groupsWithScores[0]?.score ?? 0

    // Split into highest evidence (all groups with the highest score) and supporting
    const highestEvidence = groupsWithScores
      .filter(g => g.score === highestScore)
      .map(g => g.group)
    const supportingEvidence = groupsWithScores
      .filter(g => g.score < highestScore)
      .map(g => g.group)

    // Get unique evidence categories in supporting evidence for display
    const supportingCategories = [...new Set(
      groupsWithScores
        .filter(g => g.score < highestScore && g.category)
        .map(g => getEvidenceCategoryShortName(g.category!))
    )]

    return { highestEvidence, supportingEvidence, supportingCategories }
  }

  // Format country list with truncation
  const formatCountryList = (countryStr: string | undefined | null) => {
    if (!countryStr || countryStr === 'Unknown' || countryStr === 'null') return null

    // Split by comma and filter out null/empty values
    const countries = countryStr
      .split(',')
      .map(c => c.trim())
      .filter(c => c && c !== 'null' && c !== 'Unknown')

    if (countries.length === 0) return null
    if (countries.length <= 2) return { display: countries.join(', '), full: null }

    const display = `${countries.slice(0, 2).join(', ')} +${countries.length - 2} more`
    return { display, full: countries.join(', ') }
  }

  const renderRating = (score?: number, justification?: string, defaultTooltip?: string) => {
    return (
      <StarRating
        stars={score != null ? Math.round(score) : null}
        mode="icons"
        size="sm"
        tooltip={justification || defaultTooltip}
        showGreyedStarsOnNull={true}
      />
    )
  }

  const renderHarmWarning = (hasWarning?: boolean, reason?: string) => {
    if (!hasWarning) return null
    const tooltipText = reason || 'Potential harms or adverse outcomes reported'
    return (
      <Tooltip content={tooltipText}>
        <AlertTriangle className="h-3 w-3 text-amber-600" />
      </Tooltip>
    )
  }

  const SortButton = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <Button
      variant="ghost"
      className="h-auto p-1 font-medium text-left justify-start"
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {children}
        {sortField === field && (
          sortDirection === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
        )}
      </span>
    </Button>
  )

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse">
            <div className="h-16 bg-gray-200 rounded-lg"></div>
          </div>
        ))}
      </div>
    )
  }

  if (interventions.length === 0) {
    return (
      <div className="text-center py-12">
        <Target className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">No Interventions Found</h3>
        <p className="text-gray-600">No intervention data available for this theme.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-gray-50 rounded-lg border text-sm font-medium text-gray-700">
        <div className="col-span-2">
          <SortButton field="name">Intervention</SortButton>
        </div>
        <div className="col-span-1">
          <SortButton field="country">Country</SortButton>
        </div>
        <div className="col-span-2">
          <SortButton field="type">Type</SortButton>
        </div>
        <div className="col-span-2">
          Evidence Category
        </div>
        <div className="col-span-2">
          <SortButton field="evidence_score">Evidence</SortButton>
        </div>
        <div className="col-span-1">
          <SortButton field="impact_score">Impact</SortButton>
        </div>
        <div className="col-span-2 text-center">
          <SortButton field="sample_size">Sample Size</SortButton>
        </div>
      </div>

      {/* Rows */}
      {sortedInterventions.map((intervention, index) => {
        const interventionKey = `${intervention.name}-${index}`
        const isExpanded = expandedRows.has(interventionKey)
        const outcomeGroups = intervention.outcome_groups && intervention.outcome_groups.length > 0
          ? intervention.outcome_groups
          : (intervention.results_summary && intervention.results_summary.length > 0
            ? [{
                document: intervention.documents?.[0] || {
                  doc_id: '',
                  title: 'Unknown',
                  source: 'Unknown',
                },
                results: intervention.results_summary,
              }]
            : [])
        const uniqueDocCategories = new Set(
          outcomeGroups
            .map(group => group.document.evidence_category)
            .filter((category): category is string => Boolean(category))
        )
        const showDocCategoryTag = uniqueDocCategories.size > 1
        
        return (
          <Card key={interventionKey} className="border-gray-200">
            <CardContent className="p-0">
              {/* Main Row */}
              <div
                className="grid grid-cols-12 gap-4 px-4 py-3 cursor-pointer hover:bg-gray-50"
                onClick={() => toggleRowExpansion(interventionKey)}
              >
                <div className="col-span-2">
                  <div>
                    <h3 className="font-medium text-gray-900 text-sm">{intervention.name}</h3>
                  </div>
                </div>

                <div className="col-span-1">
                  {(() => {
                    const countryInfo = formatCountryList(intervention.country)
                    if (!countryInfo) return <span className="text-sm text-gray-400">—</span>
                    if (countryInfo.full) {
                      return (
                        <Tooltip content={countryInfo.full}>
                          <span className="text-sm text-gray-700 cursor-help">{countryInfo.display}</span>
                        </Tooltip>
                      )
                    }
                    return <span className="text-sm text-gray-700">{countryInfo.display}</span>
                  })()}
                </div>

                <div className="col-span-2">
                  <span className="text-sm text-gray-700">
                    {intervention.type && intervention.type !== 'Unknown' ? intervention.type : '—'}
                  </span>
                </div>

                <div className="col-span-2">
                  {intervention.evidence_category ? (
                    <div className="flex items-center gap-2">
                      <Tooltip content={(intervention.evidence_categories || [intervention.evidence_category]).join(', ')}>
                        <span
                          className="inline-block px-2 py-1 rounded text-xs font-medium cursor-help whitespace-normal leading-tight"
                          style={{
                            backgroundColor: getEvidenceCategoryColors(intervention.evidence_category).bg,
                            color: getEvidenceCategoryColors(intervention.evidence_category).text,
                          }}
                        >
                          {getEvidenceCategoryShortName(intervention.evidence_category)}
                        </span>
                      </Tooltip>
                      {intervention.evidence_categories && intervention.evidence_categories.length > 1 && (
                        <Tooltip content={intervention.evidence_categories.slice(1).join(', ')}>
                          <span className="text-xs text-gray-500 cursor-help">
                            +{intervention.evidence_categories.length - 1}
                          </span>
                        </Tooltip>
                      )}
                    </div>
                  ) : (
                    <span className="text-gray-400 text-xs">—</span>
                  )}
                </div>

                <div className="col-span-2">
                  {renderRating(
                    intervention.evidence_score,
                    intervention.evidence_justification
                  )}
                </div>

                <div className="col-span-1">
                  <div className="flex items-center gap-1">
                  {renderRating(
                    intervention.impact_score,
                    intervention.impact_justification,
                    'Predicted impact of this intervention based on reported outcomes'
                  )}
                    {renderHarmWarning(
                      intervention.has_harm_warning,
                      intervention.harm_warning_reason
                    )}
                  </div>
                </div>

                <div className="col-span-2 text-center">
                  {/* Show N/A when multiple evidence categories since sample size source is ambiguous */}
                  {intervention.evidence_categories && intervention.evidence_categories.length > 1 ? (
                    <span className="text-xs text-gray-500">n/a</span>
                  ) : intervention.total_sample_size != null && intervention.total_sample_size > 0 ? (
                    <span className="text-sm text-gray-700">
                      {intervention.total_sample_size.toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-500">n/a</span>
                  )}
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-gray-100 bg-gray-50">
                  <div className="pt-4 space-y-3">
                    {/* Description */}
                    {intervention.description && (
                      <div>
                        <p className="text-sm text-gray-700">{intervention.description}</p>
                      </div>
                    )}

                    {/* Outcomes grouped by source document */}
                    {outcomeGroups.length > 0 && (() => {
                      const { highestEvidence, supportingEvidence, supportingCategories } = splitOutcomeGroups(outcomeGroups)
                      const showSupporting = showAllEvidence.has(interventionKey)
                      const groupsToShow = showSupporting ? [...highestEvidence, ...supportingEvidence] : highestEvidence
                      const supportingCount = supportingEvidence.length
                      const supportingLabel = showSupporting
                        ? `Hide supporting documents (${supportingCount})`
                        : `View ${supportingCount} supporting ${supportingCount === 1 ? 'document' : 'documents'}`
                      const supportingCategoriesText = supportingCategories.length > 0
                        ? (supportingCategories.length === 1
                            ? supportingCategories[0]
                            : supportingCategories.length === 2
                              ? `${supportingCategories[0]} and ${supportingCategories[1]}`
                              : `${supportingCategories.slice(0, -1).join(', ')} and ${supportingCategories[supportingCategories.length - 1]}`)
                        : null

                      return (
                        <div>
                          {/* Top accordion control for supporting evidence */}
                          {supportingEvidence.length > 0 && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleShowAllEvidence(interventionKey)
                              }}
                              className="w-full flex items-center justify-between px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md border border-gray-200 transition-colors mb-4"
                            >
                              <span className="flex items-center gap-2 text-sm text-gray-700">
                                {showSupporting ? (
                                  <ChevronUp className="h-4 w-4 text-gray-500" />
                                ) : (
                                  <ChevronDown className="h-4 w-4 text-gray-500" />
                                )}
                                <span>{supportingLabel}</span>
                                {supportingCategoriesText && (
                                  <span className="text-gray-500">
                                    ({supportingCategoriesText})
                                  </span>
                                )}
                              </span>
                            </button>
                          )}

                          <div className="space-y-6">
                            {groupsToShow.map((group, groupIdx) => (
                              <div key={group.document.doc_id || groupIdx} className="space-y-3">
                                {group.results.map((result, idx) => {
                                const isSystematicReview = result.is_systematic_review === true
                                  || result.evidence_category === 'Systematic Review and Meta-Analysis'
                                  || intervention.is_systematic_review === true
                                const outcomeTitle = result.stratum_value
                                  ? `${result.outcome} — ${result.stratum_value}`
                                  : result.outcome
                                const hasValue = (value?: string) => {
                                  if (!value) return false
                                  const cleaned = value.trim().toLowerCase()
                                  return cleaned !== 'null' && cleaned !== 'n/a'
                                }
                                const hasEffectSize = hasValue(result.effect_size)
                                const hasUncertainty = hasValue(result.uncertainty)
                                const hasPValue = hasValue(result.p_value)
                                const hasI2 = hasValue(result.heterogeneity_I2)
                                const hasTau2 = hasValue(result.tau2)

                                return (
                                  <div key={idx} className="bg-white rounded p-3 border">
                                    <div className="flex items-start justify-between mb-2">
                                      <div className="flex-1">
                                        <div className="flex flex-wrap items-center gap-2">
                                          {result.result_text ? (
                                            <Tooltip content={result.result_text}>
                                              <span className="text-sm font-medium text-gray-900 cursor-help">
                                                {outcomeTitle}
                                              </span>
                                            </Tooltip>
                                          ) : (
                                            <span className="text-sm font-medium text-gray-900">{outcomeTitle}</span>
                                          )}
                                          {result.stratum_type && (
                                            <span className="text-xs text-gray-500">
                                              ({result.stratum_type})
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                      <Badge
                                        variant="outline"
                                        className={`text-xs ${
                                          result.direction === 'increase' ? 'bg-green-50 text-green-700 border-green-200' :
                                          result.direction === 'decrease' ? 'bg-red-50 text-red-700 border-red-200' :
                                          'bg-gray-50 text-gray-700 border-gray-200'
                                        }`}
                                      >
                                        {result.direction}
                                      </Badge>
                                    </div>

                                    {isSystematicReview && ((result.n_studies && result.n_studies > 0) || (result.sample_size && result.sample_size > 0)) && (
                                      <div className="text-xs text-gray-600 mb-2">
                                        {result.n_studies && result.n_studies > 0 && (
                                          <span className="mr-3">k = {result.n_studies} studies</span>
                                        )}
                                        {result.sample_size && result.sample_size > 0 && (
                                          <span>N = {result.sample_size.toLocaleString()}</span>
                                        )}
                                      </div>
                                    )}

                                    {(hasEffectSize || hasUncertainty || hasPValue || (isSystematicReview && (hasI2 || hasTau2))) && (
                                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                                        {hasEffectSize && (
                                          <div>
                                            <span className="font-medium text-gray-600">
                                              {isSystematicReview ? 'Aggregate Effect Size' : 'Effect Size'}
                                              {result.effect_size_type && result.effect_size_type !== 'null' ? ` (${result.effect_size_type})` : ''}:{' '}
                                            </span>
                                            <span className="text-gray-600">{result.effect_size}</span>
                                          </div>
                                        )}
                                        {!isSystematicReview && hasPValue && (
                                          <div>
                                            <span className="font-medium text-gray-600">P-value: </span>
                                            <span className="text-gray-600">{result.p_value}</span>
                                          </div>
                                        )}
                                        {hasUncertainty && (
                                          <div>
                                            <span className="font-medium text-gray-600">
                                              {isSystematicReview ? 'Aggregate Uncertainty' : 'Uncertainty'}:{' '}
                                            </span>
                                            <span className="text-gray-600">±{result.uncertainty}</span>
                                          </div>
                                        )}
                                        {isSystematicReview && hasI2 && (
                                          <div>
                                            <span className="font-medium text-gray-600">I²: </span>
                                            <span className="text-gray-600">{result.heterogeneity_I2}</span>
                                          </div>
                                        )}
                                        {isSystematicReview && hasTau2 && (
                                          <div>
                                            <span className="font-medium text-gray-600">τ²: </span>
                                            <span className="text-gray-600">{result.tau2}</span>
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {result.population_measured && (
                                      <div className="mt-2 text-xs text-gray-600">
                                        <div><span className="font-medium">Population:</span> {result.population_measured}</div>
                                      </div>
                                    )}
                                  </div>
                                )
                              })}

                                {/* Footer: Source + Evidence Category + Title + Sample Size */}
                                <div className="pt-2 mt-2 border-t border-gray-100 mb-4 space-y-1">
                                  <div className="text-xs text-gray-600 flex items-center gap-2 flex-wrap">
                                    <Badge variant="outline" className="text-xs shrink-0">
                                      {group.document.source}
                                    </Badge>
                                  {showDocCategoryTag && group.document.evidence_category && (
                                    <Tooltip content={group.document.evidence_category}>
                                      <span
                                        className="inline-block px-2 py-0.5 rounded text-xs font-medium cursor-help whitespace-nowrap shrink-0"
                                        style={{
                                          backgroundColor: getEvidenceCategoryColors(group.document.evidence_category).bg,
                                          color: getEvidenceCategoryColors(group.document.evidence_category).text,
                                        }}
                                      >
                                        {getEvidenceCategoryShortName(group.document.evidence_category)}
                                      </span>
                                    </Tooltip>
                                  )}
                                    {group.document.landing_page_url ? (
                                      <a
                                        href={group.document.landing_page_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 hover:text-blue-800 hover:underline line-clamp-1"
                                      >
                                        {group.document.title}
                                      </a>
                                    ) : (
                                      <span className="line-clamp-1">{group.document.title}</span>
                                    )}
                                  </div>
                                  {/* Show reported sample size for non-SR documents when multiple evidence categories are present */}
                                  {(() => {
                                    const isDocSR = group.document.evidence_category === 'Systematic Review and Meta-Analysis'
                                    if (!showDocCategoryTag || isDocSR) return null
                                    const reportedSampleSize = group.document.reported_sample_size
                                    if (!reportedSampleSize) return null
                                    return (
                                      <Tooltip content="Reported sample size refers to the overall study cohort and may vary by outcome.">
                                        <span className="text-xs text-gray-500 inline-flex items-center cursor-help">
                                          Reported Sample Size = {reportedSampleSize.toLocaleString()}
                                        </span>
                                      </Tooltip>
                                    )
                                  })()}
                                </div>
                              </div>
                            ))}
                          </div>

                          {/* Accordion bar for supporting evidence */}
                          {supportingEvidence.length > 0 && showSupporting && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleShowAllEvidence(interventionKey)
                              }}
                              className="w-full flex items-center justify-between px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md border border-gray-200 transition-colors"
                            >
                              <span className="flex items-center gap-2 text-sm text-gray-700">
                                <ChevronUp className="h-4 w-4 text-gray-500" />
                                <span>{supportingLabel}</span>
                              </span>
                            </button>
                          )}
                        </div>
                      )
                    })()}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
