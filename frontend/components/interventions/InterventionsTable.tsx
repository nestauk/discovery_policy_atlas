'use client'

import React, { useState, useMemo } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tooltip } from '@/components/ui/tooltip'
import {
  ChevronUp,
  ChevronDown,
  Target
} from 'lucide-react'
import {
  getEvidenceCategoryColors,
  getEvidenceCategoryShortName,
  getEvidenceMixColors,
  getEvidenceMixDisplayName,
} from '@/lib/evidenceCategories'
import { StarRating } from '@/components/ui/star-rating'

export interface InterventionData {
  name: string
  type: string
  country: string
  description: string
  evidence_category?: string
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
  }>
  evidence_category_rank: number
  total_sample_size: number | null
  avg_sample_size: number | null
  documents: Array<{
    doc_id: string
    title: string
    source: string
    landing_page_url?: string
  }>
  // Evidence strength assessment fields
  stars?: number
  base_rating?: number
  cap_applied?: string | null
  cap_message?: string | null
  evidence_mix?: Record<string, number>
}

interface InterventionsTableProps {
  interventions: InterventionData[]
  loading?: boolean
}

type SortField = 'name' | 'type' | 'country' | 'result_count' | 'evidence_category_rank' | 'sample_size' | 'stars'
type SortDirection = 'asc' | 'desc'

export function InterventionsTable({ interventions, loading = false }: InterventionsTableProps) {
  const [sortField, setSortField] = useState<SortField>('evidence_category_rank')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      // For stars and result_count, higher is better so default to descending
      // For evidence_category_rank, lower is better so default to ascending
      setSortDirection(field === 'stars' || field === 'result_count' || field === 'sample_size' ? 'desc' : 'asc')
    }
  }

  const sortedInterventions = useMemo(() => {
    return [...interventions].sort((a, b) => {
      let aValue: string | number | null | undefined = a[sortField === 'sample_size' ? 'total_sample_size' : sortField]
      let bValue: string | number | null | undefined = b[sortField === 'sample_size' ? 'total_sample_size' : sortField]

      // Handle null/undefined values
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

  const toggleRowExpansion = (interventionName: string) => {
    const newExpanded = new Set(expandedRows)
    if (newExpanded.has(interventionName)) {
      newExpanded.delete(interventionName)
    } else {
      newExpanded.add(interventionName)
    }
    setExpandedRows(newExpanded)
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
        <p className="text-gray-600">No intervention data available for this project.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-gray-50 rounded-lg border text-sm font-medium text-gray-700">
        <div className="col-span-3">
          <SortButton field="name">Intervention</SortButton>
        </div>
        <div className="col-span-2">
          <SortButton field="type">Type</SortButton>
        </div>
        <div className="col-span-1">
          <SortButton field="country">Country</SortButton>
        </div>
        <div className="col-span-2">
          Evidence Category
        </div>
        <div className="col-span-1 text-center">
          <SortButton field="result_count">Results</SortButton>
        </div>
        <div className="col-span-2">
          <SortButton field="stars">Evidence Strength</SortButton>
        </div>
        <div className="col-span-1 text-center">
          <SortButton field="sample_size">Sample Size</SortButton>
        </div>
      </div>

      {/* Rows */}
      {sortedInterventions.map((intervention, index) => {
        const isExpanded = expandedRows.has(intervention.name)
        
        return (
          <Card key={`${intervention.name}-${index}`} className="border-gray-200">
            <CardContent className="p-0">
              {/* Main Row */}
              <div
                className="grid grid-cols-12 gap-4 px-4 py-3 cursor-pointer"
                onClick={() => toggleRowExpansion(intervention.name)}
              >
                <div className="col-span-3">
                  <div>
                    <h3 className="font-medium text-gray-900 text-sm">{intervention.name}</h3>
                  </div>
                </div>

                <div className="col-span-2">
                  <span className="text-sm text-gray-700">{intervention.type.toLowerCase()}</span>
                </div>

                <div className="col-span-1">
                  <span className="text-sm text-gray-700">
                    {intervention.country && intervention.country !== 'Unknown' ? intervention.country : '—'}
                  </span>
                </div>

                <div className="col-span-2">
                  {intervention.evidence_category ? (
                    <Tooltip content={intervention.evidence_category}>
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
                  ) : (
                    <span className="text-gray-400 text-xs">—</span>
                  )}
                </div>

                <div className="col-span-1 text-center">
                  <span className="text-sm text-gray-700">{intervention.result_count}</span>
                </div>

                <div className="col-span-2">
                  {/* Evidence Strength: X/5 rating + evidence mix tags */}
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <StarRating
                        stars={intervention.stars ?? null}
                        tooltip={intervention.cap_message || undefined}
                      />
                      {intervention.cap_message && (
                        <span className="text-xs text-amber-600">⚠</span>
                      )}
                    </div>
                    {intervention.evidence_mix && Object.keys(intervention.evidence_mix).length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(intervention.evidence_mix).map(([key, count]) => (
                          <span
                            key={key}
                            className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium"
                            style={{
                              backgroundColor: getEvidenceMixColors(key).bg,
                              color: getEvidenceMixColors(key).text,
                            }}
                          >
                            {getEvidenceMixDisplayName(key)} ({count})
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="col-span-1 text-center">
                  {intervention.total_sample_size ? (
                    <span className="text-sm text-gray-700">
                      {intervention.total_sample_size.toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-500">-</span>
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

                    {/* Results Summary */}
                    {intervention.results_summary && intervention.results_summary.length > 0 && (
                      <div>
                        <div className="space-y-3">
                          {intervention.results_summary.map((result, idx) => (
                            <div key={idx} className="bg-white rounded p-3 border">
                              <div className="flex items-start justify-between mb-2">
                                {result.result_text ? (
                                  <Tooltip content={result.result_text}>
                                    <span className="text-sm font-medium text-gray-900 cursor-help">
                                      {result.outcome}
                                    </span>
                                  </Tooltip>
                                ) : (
                                  <span className="text-sm font-medium text-gray-900">{result.outcome}</span>
                                )}
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
                              
                              {/* Additional details - labels and fields based on evidence category */}
                              {(() => {
                                const isSystematicReview = intervention.is_systematic_review === true
                                return (
                                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                                    <div>
                                      <span className="font-medium text-gray-600">
                                        {isSystematicReview ? 'Aggregate Effect Size' : 'Effect Size'}
                                        {result.effect_size_type && result.effect_size_type !== 'null' ? ` (${result.effect_size_type})` : ''}:{' '}
                                      </span>
                                      {result.effect_size && result.effect_size !== 'null' ? (
                                        <span className="text-gray-600">{result.effect_size}</span>
                                      ) : (
                                        <span className="text-gray-400 italic">n/a</span>
                                      )}
                                    </div>
                                    {/* Hide P-value for Systematic Reviews */}
                                    {!isSystematicReview && (
                                      <div>
                                        <span className="font-medium text-gray-600">P-value: </span>
                                        {result.p_value && result.p_value !== 'null' ? (
                                          <span className="text-gray-600">{result.p_value}</span>
                                        ) : (
                                          <span className="text-gray-400 italic">n/a</span>
                                        )}
                                      </div>
                                    )}
                                    <div>
                                      <span className="font-medium text-gray-600">
                                        {isSystematicReview ? 'Aggregate Uncertainty' : 'Uncertainty'}:{' '}
                                      </span>
                                      {result.uncertainty && result.uncertainty !== 'null' ? (
                                        <span className="text-gray-600">±{result.uncertainty}</span>
                                      ) : (
                                        <span className="text-gray-400 italic">n/a</span>
                                      )}
                                    </div>
                                    {/* SR-specific: heterogeneity measures for Systematic Reviews */}
                                    {isSystematicReview && (
                                      <>
                                        <div>
                                          <span className="font-medium text-gray-600">I²: </span>
                                          {result.heterogeneity_I2 && result.heterogeneity_I2 !== 'null' ? (
                                            <span className="text-gray-600">{result.heterogeneity_I2}</span>
                                          ) : (
                                            <span className="text-gray-400 italic">n/a</span>
                                          )}
                                        </div>
                                        <div>
                                          <span className="font-medium text-gray-600">τ²: </span>
                                          {result.tau2 && result.tau2 !== 'null' ? (
                                            <span className="text-gray-600">{result.tau2}</span>
                                          ) : (
                                            <span className="text-gray-400 italic">n/a</span>
                                          )}
                                        </div>
                                      </>
                                    )}
                                  </div>
                                )
                              })()}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Source Documents */}
                    <div>
                      <div className="space-y-1">
                        {intervention.documents.map((doc, idx) => (
                          <div key={idx} className="text-xs text-gray-600 flex items-center gap-2">
                            <Badge variant="outline" className="text-xs">
                              {doc.source}
                            </Badge>
                            {intervention.evidence_category && (
                              <Tooltip content={intervention.evidence_category}>
                                <span
                                  className="inline-block px-2 py-0.5 rounded text-[10px] font-medium cursor-help whitespace-nowrap"
                                  style={{
                                    backgroundColor: getEvidenceCategoryColors(intervention.evidence_category).bg,
                                    color: getEvidenceCategoryColors(intervention.evidence_category).text,
                                  }}
                                >
                                  {getEvidenceCategoryShortName(intervention.evidence_category)}
                                </span>
                              </Tooltip>
                            )}
                            {doc.landing_page_url ? (
                              <a 
                                href={doc.landing_page_url} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:text-blue-800 hover:underline line-clamp-1"
                              >
                                {doc.title}
                              </a>
                            ) : (
                              <span className="line-clamp-1">{doc.title}</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
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
