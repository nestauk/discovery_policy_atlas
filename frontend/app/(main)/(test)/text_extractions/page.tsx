'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { 
  FileText, 
  Loader2,
  ArrowLeft,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  Target,
  TrendingUp
} from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'

interface AnalysisDocument {
  id: string
  doc_id: string
  title: string
  source: string
  authors?: string[]
  year?: number
  abstract_or_summary?: string
  is_relevant?: boolean
  relevance_reason?: string
  relevance_confidence?: number
  source_country?: string
  source_type?: string
  venue?: string
  top_line?: string
  doi?: string
  landing_page_url?: string
  full_text_available?: boolean
  extraction_status?: string
  cited_by_count?: number
}

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
        // Support both 'direction' (new schema) and 'effect_direction' (legacy)
        direction?: string
        impact_direction?: string
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

// Document Detail View Component
function DocumentDetailView({ extraction }: { 
  extraction: DocumentDetailResult['extraction']
}) {
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
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-600" />
                  <span className="text-red-900 font-medium">Issues & Problems ({issues.length})</span>
                </div>
                {openSections.issues ? 
                  <ChevronDown className="h-4 w-4 text-gray-500" /> : 
                  <ChevronRight className="h-4 w-4 text-gray-500" />
                }
              </div>
            </CardContent>
          </Card>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-3 mt-2">
            {issues.map((issue, index: number) => (
              <Card key={issue.idx || index} className="border-red-100">
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <div className="w-6 h-6 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
                      <span className="text-red-700 font-medium text-sm">{issue.idx !== undefined ? issue.idx : index + 1}</span>
                    </div>
                    <div className="flex-1">
                      <h5 className="font-medium text-red-900 mb-1">{issue.label}</h5>
                      <p className="text-red-700 text-sm mb-2">{issue.explanation}</p>
                      {issue.supporting_quote && (
                        <blockquote className="text-red-600 text-xs italic border-l-4 border-red-200 pl-3">
                          &ldquo;{issue.supporting_quote}&rdquo;
                        </blockquote>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
            {issues.length === 0 && (
              <p className="text-gray-500 text-sm italic">No issues identified in this document.</p>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Interventions & Results Section */}
      <Collapsible open={openSections.interventions} onOpenChange={() => toggleSection('interventions')}>
        <CollapsibleTrigger asChild>
          <Card className="cursor-pointer hover:bg-gray-50 border-blue-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Target className="h-4 w-4 text-blue-600" />
                  <span className="text-blue-900 font-medium">Interventions & Results ({interventions.length})</span>
                </div>
                {openSections.interventions ? 
                  <ChevronDown className="h-4 w-4 text-gray-500" /> : 
                  <ChevronRight className="h-4 w-4 text-gray-500" />
                }
              </div>
            </CardContent>
          </Card>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-4 mt-2">
            {interventions.map((intervention, index: number) => (
              <Card key={intervention.idx || index} className="border-blue-100">
                <CardContent className="p-4">
                  <div className="space-y-3">
                    {/* Intervention Header */}
                    <div className="flex items-start gap-3">
                      <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                        <span className="text-blue-700 font-medium text-sm">{intervention.idx !== undefined ? intervention.idx : index + 1}</span>
                      </div>
                      <div className="flex-1">
                        <h5 className="font-medium text-blue-900 mb-1">{intervention.name}</h5>
                        <p className="text-blue-700 text-sm mb-2">{intervention.description}</p>
                        
                        {/* Intervention Details */}
                        <div className="flex gap-2 mb-2">
                          <Badge variant="outline" className="text-xs bg-blue-50">
                            {intervention.type}
                          </Badge>
                          {intervention.country && (
                            <Badge variant="outline" className="text-xs bg-blue-50">
                              {intervention.country}
                            </Badge>
                          )}
                          {intervention.study_type && (
                            <Badge variant="outline" className="text-xs bg-blue-50">
                              Study: {intervention.study_type}
                            </Badge>
                          )}
                        </div>

                        {/* Issues Addressed */}
                        {intervention.addresses_issues && intervention.addresses_issues.length > 0 && (
                          <div className="mb-2">
                            <span className="text-xs text-blue-600 font-medium">Addresses issues: </span>
                            {intervention.addresses_issues.map((issueIdx: number) => {
                              const relatedIssue = issues.find(issue => issue.idx === issueIdx)
                              const issueTitle = relatedIssue?.label || `Issue ${issueIdx}`
                              return (
                                <Badge key={issueIdx} variant="outline" className="text-xs mr-1 bg-red-50 text-red-700" title={issueTitle}>
                                  #{issueIdx}: {issueTitle}
                                </Badge>
                              )
                            })}
                          </div>
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
                                    {/* Support both 'direction' (new) and 'effect_direction' (legacy) */}
                                    <Badge variant="outline" className="text-xs bg-green-100 text-green-700">
                                      {result.direction ||
                                        result.impact_direction ||
                                        result.effect_direction}
                                    </Badge>
                                  </div>
                                  
                                  {/* Quantitative measures */}
                                  {((result.effect_size && result.effect_size !== 'null') || (result.effect_size_type && result.effect_size_type !== 'null') || (result.uncertainty && result.uncertainty !== 'null') || (result.p_value && result.p_value !== 'null') || (result.heterogeneity_I2 && result.heterogeneity_I2 !== 'null')) && (
                                    <div className="mb-2">
                                      {result.effect_size_type && result.effect_size_type !== 'null' && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">Effect Type: </span>
                                          {result.effect_size_type}
                                        </div>
                                      )}
                                      {result.effect_size && result.effect_size !== 'null' && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">
                                            Effect Size{result.summary_statistic && result.summary_statistic !== 'null' ? ` (${result.summary_statistic})` : ''}:{' '}
                                          </span>
                                          {result.effect_size}
                                        </div>
                                      )}
                                      {result.uncertainty && result.uncertainty !== 'null' && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">Uncertainty: </span>
                                          ±{result.uncertainty}
                                        </div>
                                      )}
                                      {result.p_value && result.p_value !== 'null' && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">P-value: </span>
                                          {result.p_value}
                                        </div>
                                      )}
                                      {/* SR-specific: heterogeneity measures for pooled results (always show for SRs) */}
                                      {result.estimate_level === 'pooled' && (
                                        <>
                                          <div className="text-xs text-green-600 mb-1">
                                            <span className="font-medium">I²: </span>
                                            {result.heterogeneity_I2 && result.heterogeneity_I2 !== 'null' ? (
                                              result.heterogeneity_I2
                                            ) : (
                                              <span className="text-green-400 italic">n/a</span>
                                            )}
                                          </div>
                                          <div className="text-xs text-green-600 mb-1">
                                            <span className="font-medium">τ²: </span>
                                            {result.tau2 && result.tau2 !== 'null' ? (
                                              result.tau2
                                            ) : (
                                              <span className="text-green-400 italic">n/a</span>
                                            )}
                                          </div>
                                        </>
                                      )}
                                    </div>
                                  )}
                                  
                                  {/* Population information */}
                                  {result.population_measured && (
                                    <div className="mb-2">
                                      <div className="text-xs text-green-600 mb-1">
                                        <span className="font-medium">Population: </span>
                                        {result.population_measured}
                                      </div>
                                    </div>
                                  )}
                                  
                                  <p className="text-green-700 text-xs">{result.result_text}</p>
                                  {result.supporting_quote && (
                                    <blockquote className="text-green-600 text-xs italic mt-1">
                                      &ldquo;{result.supporting_quote}&rdquo;
                                    </blockquote>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
            {interventions.length === 0 && (
              <p className="text-gray-500 text-sm italic">No interventions identified in this document.</p>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Conclusion Section */}
      {conclusion && (
        <Collapsible open={openSections.conclusion} onOpenChange={() => toggleSection('conclusion')}>
          <CollapsibleTrigger asChild>
            <Card className="cursor-pointer hover:bg-gray-50 border-purple-200">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-purple-600" />
                    <span className="text-purple-900 font-medium">Conclusion</span>
                  </div>
                  {openSections.conclusion ? 
                    <ChevronDown className="h-4 w-4 text-gray-500" /> : 
                    <ChevronRight className="h-4 w-4 text-gray-500" />
                  }
                </div>
              </CardContent>
            </Card>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <Card className="border-purple-100 mt-2">
              <CardContent className="p-4">
                <h5 className="font-medium text-purple-900 mb-2">{conclusion.top_line_summary}</h5>
                <p className="text-purple-700 text-sm mb-3">{conclusion.detailed_explanation}</p>
                {conclusion.supporting_quote && (
                  <blockquote className="text-purple-600 text-xs italic border-l-4 border-purple-200 pl-3">
                    &ldquo;{conclusion.supporting_quote}&rdquo;
                  </blockquote>
                )}
              </CardContent>
            </Card>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}

export default function ExtractionsPage() {
  const router = useRouter()
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)
  
  // Document detail view state
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [documentDetail, setDocumentDetail] = useState<DocumentDetailResult | null>(null)
  const [loadingDocumentDetail, setLoadingDocumentDetail] = useState(false)
  const [documentDetailError, setDocumentDetailError] = useState<string | null>(null)

  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth, getDocumentExtraction } = useAPI()

  // Use only active project ID
  const effectiveProjectId = activeProject?.id || ''

  // Load documents data
  const loadData = useCallback(async () => {
    if (!effectiveProjectId) return

    setLoadingData(true)
    setDataError(null)

    try {
      const docsResponse = await fetchWithAuth(`/api/analysis-projects/${effectiveProjectId}/documents`)
      setDocuments(docsResponse.documents || [])
    } catch (error) {
      console.error('Failed to load project documents:', error)
      setDataError(error instanceof Error ? error.message : 'Failed to load data')
    } finally {
      setLoadingData(false)
    }
  }, [effectiveProjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load data when project changes
  useEffect(() => {
    if (effectiveProjectId) {
      loadData()
    }
  }, [effectiveProjectId, loadData])

  // Load document detail extraction
  const loadDocumentDetail = useCallback(async (documentId: string) => {
    if (!effectiveProjectId) return
    
    setLoadingDocumentDetail(true)
    setDocumentDetailError(null)
    setSelectedDocumentId(documentId)
    
    try {
      const result = await getDocumentExtraction(effectiveProjectId, documentId)
      setDocumentDetail(result)
    } catch (error) {
      console.error('Failed to load document detail:', error)
      setDocumentDetailError(error instanceof Error ? error.message : 'Failed to load document detail')
    } finally {
      setLoadingDocumentDetail(false)
    }
  }, [effectiveProjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close document detail view
  const closeDocumentDetail = () => {
    setSelectedDocumentId(null)
    setDocumentDetail(null)
    setDocumentDetailError(null)
  }

  const goBackToResults = () => {
    router.push('/results')
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-4 mb-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={goBackToResults}
                className="flex items-center gap-2"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Results
              </Button>
            </div>
            <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
              Extractions
            </h1>
            <p className="text-slate-600 mt-1">
              {activeProject ? (
                <>Project: {activeProject.title}</>
              ) : (
                <>No Project Selected</>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-slate-50 p-6">
        <div className="max-w-6xl mx-auto">
          {/* Show empty state if no project is selected */}
          {!effectiveProjectId && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center p-8">
                <FileText className="h-16 w-16 text-slate-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">No Project Selected</h3>
                <p className="text-slate-600 mb-6">
                  Please select a project to view document extractions.
                </p>
                <Button onClick={() => router.push('/projects')} variant="outline">
                  <FileText className="h-4 w-4 mr-2" />
                  View Projects
                </Button>
              </div>
            </div>
          )}

          {/* Document List */}
          {effectiveProjectId && (
            <>
              {loadingData ? (
                <div className="flex items-center justify-center py-12">
                  <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-slate-600">Loading documents...</p>
                  </div>
                </div>
              ) : dataError ? (
                <div className="text-center py-12">
                  <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-900 mb-2">Error Loading Data</h3>
                  <p className="text-slate-600">{dataError}</p>
                </div>
              ) : documents.length > 0 ? (
                <div className="space-y-4">
                  <div className="space-y-3">
                    {documents.map((doc) => {
                      const isExpanded = selectedDocumentId === doc.id
                      const handleCardClick = (e: React.MouseEvent) => {
                        // Don't trigger if clicking on a link
                        if ((e.target as HTMLElement).closest('a')) {
                          return
                        }
                        
                        if (isExpanded) {
                          closeDocumentDetail()
                        } else {
                          loadDocumentDetail(doc.id)
                        }
                      }
                      
                      return (
                        <Card 
                          key={doc.id} 
                          className={`border-slate-200 cursor-pointer transition-all hover:shadow-md ${
                            isExpanded ? 'ring-2 ring-blue-300 bg-blue-50' : ''
                          }`}
                          onClick={handleCardClick}
                        >
                          <CardContent className="p-4">
                            {/* Card Header - Always Visible */}
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <h3 className="font-semibold text-slate-900 mb-2">
                                  {doc.landing_page_url ? (
                                    <a 
                                      href={doc.landing_page_url} 
                                      target="_blank" 
                                      rel="noopener noreferrer"
                                      className="text-blue-600 hover:text-blue-800 hover:underline"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      {doc.title || 'Untitled Document'}
                                    </a>
                                  ) : (
                                    doc.title || 'Untitled Document'
                                  )}
                                </h3>
                                <div className="flex items-center gap-2 mb-2">
                                  <Badge variant="outline" className="text-xs">
                                    {doc.source || 'Unknown Source'}
                                  </Badge>
                                  {doc.year && (
                                    <Badge variant="outline" className="text-xs">
                                      {doc.year}
                                    </Badge>
                                  )}
                                  {doc.is_relevant !== null && (
                                    <Badge 
                                      variant="outline" 
                                      className={`text-xs ${
                                        doc.is_relevant 
                                          ? 'bg-green-100 text-green-700' 
                                          : 'bg-red-100 text-red-700'
                                      }`}
                                    >
                                      {doc.is_relevant ? 'Relevant' : 'Not Relevant'}
                                    </Badge>
                                  )}
                                  {/* Extraction Status Indicator */}
                                  {doc.extraction_status && (
                                    <Badge 
                                      variant="outline" 
                                      className={`text-xs ${
                                        doc.extraction_status === 'success' 
                                          ? 'bg-blue-100 text-blue-700' 
                                          : doc.extraction_status === 'failed'
                                          ? 'bg-red-100 text-red-700'
                                          : doc.extraction_status === 'skipped'
                                          ? 'bg-yellow-100 text-yellow-700'
                                          : 'bg-gray-100 text-gray-700'
                                      }`}
                                    >
                                      {doc.extraction_status === 'success' ? '✓ Extracted' :
                                       doc.extraction_status === 'failed' ? '✗ Failed' :
                                       doc.extraction_status === 'skipped' ? '⊘ Skipped' :
                                       `✓ ${doc.extraction_status}`}
                                    </Badge>
                                  )}
                                </div>
                                {!isExpanded && doc.abstract_or_summary && (
                                  <p className="text-slate-600 text-sm line-clamp-2 mb-2">
                                    {doc.abstract_or_summary}
                                  </p>
                                )}
                              </div>
                              <div className="flex items-center gap-2 ml-4">
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4 text-slate-400" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 text-slate-400" />
                                )}
                              </div>
                            </div>
                            
                            {/* Expanded Content */}
                            {isExpanded && (
                              <div className="mt-4 pt-4 border-t border-slate-200">
                                {loadingDocumentDetail ? (
                                  <div className="flex items-center justify-center py-8">
                                    <div className="text-center">
                                      <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2 text-blue-600" />
                                      <p className="text-blue-700 text-sm">Loading document details...</p>
                                    </div>
                                  </div>
                                ) : documentDetailError ? (
                                  <div className="text-center py-4">
                                    <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
                                    <p className="text-red-600 text-sm">{documentDetailError}</p>
                                  </div>
                                ) : documentDetail && documentDetail.extraction ? (
                                  <DocumentDetailView extraction={documentDetail.extraction} />
                                ) : documentDetail ? (
                                  <div className="text-center py-4">
                                    <FileText className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                                    <p className="text-gray-600 text-sm">No extraction data available for this document</p>
                                  </div>
                                ) : null}
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      )
                    })}
                  </div>
                </div>
              ) : (
                <div className="text-center py-12">
                  <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-900 mb-2">No Documents Available</h3>
                  <p className="text-slate-600">Documents will appear here once the analysis is processed.</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
