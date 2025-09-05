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
      study_type?: string
      supporting_quote?: string
      addresses_issues?: number[]
      results?: Array<{
        outcome_variable?: string
        effect_direction?: string
        effect_size_type?: string
        effect_size?: string
        uncertainty?: string
        p_value?: string
        population_measured?: string
        subgroup_or_dose?: string
        result_text?: string
        supporting_quote?: string
      }>
    }>
    mappings?: unknown[]
    conclusion?: {
      top_line_summary?: string
      detailed_explanation?: string
      supporting_quote?: string
    }
    metadata?: Record<string, unknown>
  }
}

interface DocumentDetailViewProps {
  extraction: DocumentDetailResult['extraction']
}

export function DocumentDetailView({ extraction }: DocumentDetailViewProps) {
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
                          {intervention.study_type && (
                            <Badge variant="outline" className="text-xs bg-purple-50 text-purple-700">
                              Study: {intervention.study_type}
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
                            <div key={resultIndex} className="bg-green-50 border-l-4 border-green-200 p-2 rounded">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="font-medium text-green-900 text-sm">
                                  {result.outcome_variable}
                                </span>
                                <Badge variant="outline" className="text-xs bg-green-100 text-green-700">
                                  {result.effect_direction}
                                </Badge>
                              </div>
                              
                              {/* Quantitative measures */}
                              {(result.effect_size || result.p_value || result.uncertainty) && (
                                <div className="flex gap-3 text-xs text-green-800 mb-1">
                                  {result.effect_size && (
                                    <span>Effect: {result.effect_size}</span>
                                  )}
                                  {result.p_value && (
                                    <span>p = {result.p_value}</span>
                                  )}
                                  {result.uncertainty && (
                                    <span>CI: {result.uncertainty}</span>
                                  )}
                                </div>
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