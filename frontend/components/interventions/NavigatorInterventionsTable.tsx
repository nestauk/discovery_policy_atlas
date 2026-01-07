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

interface NavigatorInterventionData {
  name: string
  type: string
  country: string
  description: string
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
  total_sample_size: number | null
  documents: Array<{
    doc_id: string
    title: string
    source: string
    landing_page_url?: string
  }>
  impact_score?: number
  evidence_score?: number
  impact_justification?: string
  evidence_justification?: string
}

interface NavigatorInterventionsTableProps {
  interventions: NavigatorInterventionData[]
  loading?: boolean
}

type SortField = 'name' | 'type' | 'country' | 'result_count' | 'sample_size' | 'impact_score' | 'evidence_score'
type SortDirection = 'asc' | 'desc'

export function NavigatorInterventionsTable({ interventions, loading = false }: NavigatorInterventionsTableProps) {
  const [sortField, setSortField] = useState<SortField>('impact_score')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

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
      let aValue: string | number | null = a[sortField === 'sample_size' ? 'total_sample_size' : sortField] ?? null
      let bValue: string | number | null = b[sortField === 'sample_size' ? 'total_sample_size' : sortField] ?? null

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

  const renderRating = (score?: number, justification?: string, defaultText?: string) => {
    if (!score) return <span className="text-xs text-gray-400">—</span>
    
    const rating = Math.round(score)
    const ratingDisplay = (
      <span className="inline-block px-2 py-0.5 rounded text-center font-medium bg-blue-100 text-blue-800 text-xs cursor-help">
        {rating}/5
      </span>
    )
    
    const tooltipText = justification || defaultText
    
    if (tooltipText) {
      return (
        <Tooltip content={tooltipText}>
          <span>{ratingDisplay}</span>
        </Tooltip>
      )
    }
    
    return ratingDisplay
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
        <div className="col-span-3">
          <SortButton field="name">Intervention</SortButton>
        </div>
        <div className="col-span-2">
          <SortButton field="country">Country</SortButton>
        </div>
        <div className="col-span-2">
          <SortButton field="type">Type</SortButton>
        </div>
        <div className="col-span-1">
          <SortButton field="impact_score">Impact</SortButton>
        </div>
        <div className="col-span-2">
          <SortButton field="evidence_score">Evidence</SortButton>
        </div>
        <div className="col-span-2 text-center">
          <SortButton field="sample_size">Sample Size</SortButton>
        </div>
      </div>

      {/* Rows */}
      {sortedInterventions.map((intervention, index) => {
        const interventionKey = `${intervention.name}-${index}`
        const isExpanded = expandedRows.has(interventionKey)
        
        return (
          <Card key={interventionKey} className="border-gray-200">
            <CardContent className="p-0">
              {/* Main Row */}
              <div 
                className="grid grid-cols-12 gap-4 px-4 py-3 cursor-pointer hover:bg-gray-50"
                onClick={() => toggleRowExpansion(interventionKey)}
              >
                <div className="col-span-3">
                  <div>
                    <h3 className="font-medium text-gray-900 text-sm">{intervention.name}</h3>
                  </div>
                </div>
                
                <div className="col-span-2">
                  <span className="text-sm text-gray-700">
                    {intervention.country && intervention.country !== 'Unknown' ? intervention.country : '—'}
                  </span>
                </div>
                
                <div className="col-span-2">
                  <span className="text-sm text-gray-700">
                    {intervention.type && intervention.type !== 'Unknown' ? intervention.type : '—'}
                  </span>
                </div>
                
                <div className="col-span-1">
                  {renderRating(
                    intervention.impact_score, 
                    intervention.impact_justification,
                    'Predicted impact of this intervention based on reported outcomes'
                  )}
                </div>
                
                <div className="col-span-2">
                  {renderRating(
                    intervention.evidence_score,
                    intervention.evidence_justification,
                    'Quality of evidence supporting this intervention based on study design and methodology'
                  )}
                </div>
                
                <div className="col-span-2 text-center">
                  {intervention.total_sample_size != null && intervention.total_sample_size > 0 ? (
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
                              
                              {/* Additional details */}
                              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                                <div>
                                  <span className="font-medium text-gray-600">
                                    Effect Size{result.summary_statistic && result.summary_statistic !== 'null' ? ` (${result.summary_statistic})` : ''}:{' '}
                                  </span>
                                  {result.effect_size && result.effect_size !== 'null' ? (
                                    <span className="text-gray-600">{result.effect_size}</span>
                                  ) : (
                                    <span className="text-gray-400 italic">n/a</span>
                                  )}
                                </div>
                                <div>
                                  <span className="font-medium text-gray-600">P-value: </span>
                                  {result.p_value && result.p_value !== 'null' ? (
                                    <span className="text-gray-600">{result.p_value}</span>
                                  ) : (
                                    <span className="text-gray-400 italic">n/a</span>
                                  )}
                                </div>
                                <div>
                                  <span className="font-medium text-gray-600">Uncertainty: </span>
                                  {result.uncertainty && result.uncertainty !== 'null' ? (
                                    <span className="text-gray-600">±{result.uncertainty}</span>
                                  ) : (
                                    <span className="text-gray-400 italic">n/a</span>
                                  )}
                                </div>
                                {/* SR-specific: heterogeneity measures for pooled results (always show for SRs) */}
                                {result.estimate_level === 'pooled' && (
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
                              
                              {/* Population info */}
                              {result.population_measured && (
                                <div className="mt-2 text-xs text-gray-600">
                                  <div><span className="font-medium">Population:</span> {result.population_measured}</div>
                                </div>
                              )}
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