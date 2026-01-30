'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { 
  AlertCircle,
  ChevronRight,
  ChevronDown,
  Target,
  TrendingUp,
} from 'lucide-react'

interface DocumentDetailResult {
  document: {
    id: string
    doc_id: string
    title: string
    source: string
    year?: number
    abstract_or_summary?: string
    is_relevant?: boolean
    extraction_status?: string
  }
  extraction: {
    issues: Array<{
      idx?: number
      label?: string
      explanation?: string
      supporting_quote?: string
    }>
    interventions: Array<{
      idx?: number
      name?: string
      description?: string
      type?: string
      country?: string
      sample_size?: string
      supporting_quote?: string
      addresses_issues?: number[]
      results?: Array<{
        outcome_variable?: string
        // Support both 'direction' (new schema) and 'effect_direction' (legacy)
        direction?: string
        effect_direction?: string
        effect_size_type?: string
        effect_size?: string
        uncertainty?: string
        p_value?: string
        population_measured?: string
        subgroup_or_dose?: string
        result_text?: string
        supporting_quote?: string
        // SR-specific fields for meta-analysis results
        heterogeneity_I2?: string
        tau2?: string
        summary_statistic?: string
        estimate_level?: string
        // SR sample size fields
        n_studies?: number
        sample_size?: number
        // Stratum fields (for SR subgroup analyses)
        stratum_type?: string
        stratum_value?: string
        is_primary_stratum?: boolean
      }>
    }>
    mappings?: unknown[]
    conclusion?: {
      top_line_summary?: string
      detailed_explanation?: string
      supporting_quote?: string
      evidence_strength?: {
        stars?: number | null
        justification?: string
        evidence_gap?: string
      }
    }
    metadata?: Record<string, unknown>
  }
}

interface DocumentDetailViewProps {
  extraction: DocumentDetailResult['extraction']
  isSystematicReview?: boolean
}

export function DocumentDetailView({ extraction, isSystematicReview = false }: DocumentDetailViewProps) {
  const [openSections, setOpenSections] = useState({
    issues: true,
    interventions: true,
    results: false,
    conclusion: true
  })

  const toggleSection = (section: keyof typeof openSections) => {
    setOpenSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  const issues = extraction.issues || []
  const interventions = extraction.interventions || []
  const conclusion = extraction.conclusion

  return (
    <div className="space-y-4">
      {/* Issues Section */}
      <Collapsible open={openSections.issues} onOpenChange={() => toggleSection('issues')}>
        <CollapsibleTrigger asChild>
          <Card className="cursor-pointer hover:bg-gray-50 border-red-200">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-base">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-600" />
                  <span className="text-red-900">Issues & Problems ({issues.length})</span>
                </div>
                {openSections.issues ? 
                  <ChevronDown className="h-4 w-4 text-gray-500" /> : 
                  <ChevronRight className="h-4 w-4 text-gray-500" />
                }
              </CardTitle>
            </CardHeader>
          </Card>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-3 mt-2">
            {issues.map((issue, index: number) => (
              <Card key={issue.idx || index} className="border-red-100">
                <CardContent className="p-4">
                  <div className="space-y-2">
                    <h5 className="font-semibold text-red-900">{issue.label}</h5>
                    {issue.explanation && (
                      <p className="text-sm text-gray-700 leading-relaxed">
                        {issue.explanation}
                      </p>
                    )}
                    {issue.supporting_quote && (
                      <blockquote className="border-l-4 border-red-200 pl-3 text-sm text-gray-600 italic">
                        &ldquo;{issue.supporting_quote}&rdquo;
                      </blockquote>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
            {issues.length === 0 && (
              <Card className="border-red-100">
                <CardContent className="p-4 text-center">
                  <p className="text-sm text-gray-500">No issues extracted</p>
                </CardContent>
              </Card>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Interventions Section */}
      <Collapsible open={openSections.interventions} onOpenChange={() => toggleSection('interventions')}>
        <CollapsibleTrigger asChild>
          <Card className="cursor-pointer hover:bg-gray-50 border-blue-200">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-base">
                <div className="flex items-center gap-2">
                  <Target className="h-4 w-4 text-blue-600" />
                  <span className="text-blue-900">Interventions ({interventions.length})</span>
                </div>
                {openSections.interventions ? 
                  <ChevronDown className="h-4 w-4 text-gray-500" /> : 
                  <ChevronRight className="h-4 w-4 text-gray-500" />
                }
              </CardTitle>
            </CardHeader>
          </Card>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-4 mt-2">
            {interventions.map((intervention, index: number) => (
              <Card key={intervention.idx || index} className="border-blue-100">
                <CardContent className="p-4">
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h5 className="font-semibold text-blue-900 mb-1">{intervention.name}</h5>
                        <div className="flex flex-wrap gap-2 mb-2">
                          {intervention.type && (
                            <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700">
                              {intervention.type}
                            </Badge>
                          )}
                          {intervention.country && (
                            <Badge variant="outline" className="text-xs bg-gray-50 text-gray-700">
                              📍 {intervention.country}
                            </Badge>
                          )}
                      {intervention.sample_size && intervention.sample_size !== 'null' && (
                        <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700">
                          Sample: {intervention.sample_size}
                        </Badge>
                      )}
                        </div>
                      </div>
                    </div>

                    {intervention.description && (
                      <p className="text-sm text-gray-700 leading-relaxed">
                        {intervention.description}
                      </p>
                    )}

                    {intervention.supporting_quote && (
                      <blockquote className="border-l-4 border-blue-200 pl-3 text-sm text-gray-600 italic">
                        &ldquo;{intervention.supporting_quote}&rdquo;
                      </blockquote>
                    )}

                    {/* Results for this intervention */}
                    {intervention.results && intervention.results.length > 0 && (
                      <div className="mt-3">
                        <h6 className="font-medium text-green-900 text-sm mb-2 flex items-center gap-1">
                          <TrendingUp className="h-3 w-3" />
                          Results ({intervention.results.length})
                        </h6>
                        <div className="space-y-2">
                          {intervention.results.map((result, resultIndex: number) => (
                            <div
                              key={resultIndex}
                              className="bg-green-50 border-l-4 border-green-200 p-2 rounded"
                            >
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <span className="font-medium text-green-900 text-sm">
                                  {result.outcome_variable}
                                </span>
                                {/* Stratum badge for subgroup analyses */}
                                {result.stratum_type && result.stratum_value && (
                                  <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
                                    {result.stratum_type}: {result.stratum_value}
                                  </Badge>
                                )}
                                {/* Support both 'direction' (new schema) and 'effect_direction' (legacy) */}
                                <Badge variant="outline" className="text-xs bg-green-100 text-green-700">
                                  {result.direction || result.effect_direction}
                                </Badge>
                              </div>

                              {/* Sample size info for SR */}
                              {isSystematicReview && (result.n_studies || result.sample_size) && (
                                <div className="flex gap-3 text-xs text-green-700 mb-1">
                                  {result.n_studies && (
                                    <span>k = {result.n_studies} studies</span>
                                  )}
                                  {result.sample_size && (
                                    <span>N = {result.sample_size.toLocaleString()}</span>
                                  )}
                                </div>
                              )}

                              {/* Quantitative measures */}
                              {((result.effect_size && result.effect_size !== 'null') || (result.p_value && result.p_value !== 'null') || (result.uncertainty && result.uncertainty !== 'null') || (result.heterogeneity_I2 && result.heterogeneity_I2 !== 'null')) && (
                                <div className="flex flex-wrap gap-3 text-xs text-green-800 mb-1">
                                  {result.effect_size && result.effect_size !== 'null' && (
                                    <span>
                                      {isSystematicReview ? 'Aggregate Effect' : 'Effect'}{result.summary_statistic && result.summary_statistic !== 'null' ? ` (${result.summary_statistic})` : ''}: {result.effect_size}
                                    </span>
                                  )}
                                  {/* Hide p-value for SRs */}
                                  {!isSystematicReview && result.p_value && result.p_value !== 'null' && (
                                    <span>p = {result.p_value}</span>
                                  )}
                                  {result.uncertainty && result.uncertainty !== 'null' && (
                                    <span>{isSystematicReview ? 'Aggregate CI' : 'CI'}: {result.uncertainty}</span>
                                  )}
                                  {/* SR-specific: heterogeneity measures (always show for SRs) */}
                                  {isSystematicReview && (
                                    <>
                                      <span>
                                        I²: {result.heterogeneity_I2 && result.heterogeneity_I2 !== 'null' ? result.heterogeneity_I2 : <span className="text-green-600 italic">n/a</span>}
                                      </span>
                                      <span>
                                        τ²: {result.tau2 && result.tau2 !== 'null' ? result.tau2 : <span className="text-green-600 italic">n/a</span>}
                                      </span>
                                    </>
                                  )}
                                </div>
                              )}

                              {/* Population measured */}
                              {result.population_measured && result.population_measured !== 'null' && (
                                <p className="text-xs text-green-700 mb-1">
                                  Population: {result.population_measured}
                                </p>
                              )}

                              {result.result_text && (
                                <p className="text-sm text-green-900 mb-1">{result.result_text}</p>
                              )}

                              {result.supporting_quote && (
                                <blockquote className="border-l-2 border-green-300 pl-2 text-xs text-green-700 italic">
                                  &ldquo;{result.supporting_quote}&rdquo;
                                </blockquote>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
            {interventions.length === 0 && (
              <Card className="border-blue-100">
                <CardContent className="p-4 text-center">
                  <p className="text-sm text-gray-500">No interventions extracted</p>
                </CardContent>
              </Card>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Conclusion Section */}
      {conclusion && (
        <Collapsible open={openSections.conclusion} onOpenChange={() => toggleSection('conclusion')}>
          <CollapsibleTrigger asChild>
            <Card className="cursor-pointer hover:bg-gray-50 border-purple-200">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between text-base">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-purple-600" />
                    <span className="text-purple-900">Conclusion</span>
                  </div>
                  {openSections.conclusion ? 
                    <ChevronDown className="h-4 w-4 text-gray-500" /> : 
                    <ChevronRight className="h-4 w-4 text-gray-500" />
                  }
                </CardTitle>
              </CardHeader>
            </Card>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <Card className="border-purple-100 mt-2">
              <CardContent className="p-4">
                <div className="space-y-3">
                  {conclusion.top_line_summary && (
                    <div>
                      <h6 className="font-medium text-purple-900 text-sm mb-1">Key Finding</h6>
                      <p className="text-sm text-gray-700 font-medium">
                        {conclusion.top_line_summary}
                      </p>
                    </div>
                  )}

                  {conclusion.detailed_explanation && (
                    <div>
                      <h6 className="font-medium text-purple-900 text-sm mb-1">Detailed Explanation</h6>
                      <p className="text-sm text-gray-700 leading-relaxed">
                        {conclusion.detailed_explanation}
                      </p>
                    </div>
                  )}

                  {conclusion.evidence_strength && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {conclusion.evidence_strength && (
                        <div>
                          <h6 className="font-medium text-purple-900 text-sm mb-1">Evidence strength</h6>
                          <div className="text-sm text-gray-700">
                            {typeof conclusion.evidence_strength.stars === 'number' && (
                              <div className="mb-1">
                                <span className="font-medium">Stars: </span>
                                {"★".repeat(Math.max(0, Math.min(5, conclusion.evidence_strength.stars)))}
                                {"☆".repeat(Math.max(0, 5 - Math.max(0, Math.min(5, conclusion.evidence_strength.stars))))}
                              </div>
                            )}
                            {conclusion.evidence_strength.justification && (
                              <p className="text-sm text-gray-700">{conclusion.evidence_strength.justification}</p>
                            )}
                            {conclusion.evidence_strength.stars == null && conclusion.evidence_strength.evidence_gap && (
                              <p className="text-xs text-gray-500 mt-1">Evidence gap: {conclusion.evidence_strength.evidence_gap}</p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {conclusion.supporting_quote && (
                    <blockquote className="border-l-4 border-purple-200 pl-3 text-sm text-gray-600 italic">
                      &ldquo;{conclusion.supporting_quote}&rdquo;
                    </blockquote>
                  )}
                </div>
              </CardContent>
            </Card>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}