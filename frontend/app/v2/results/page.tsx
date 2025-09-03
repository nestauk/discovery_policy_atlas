'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { PapersTable } from '@/components/search/papers-table'
import { InterventionsTable, InterventionData } from '@/components/search/interventions-table'
import { Paper } from '@/types/search'
import { 
  FileText, 
  Loader2,
  ArrowLeft,
  AlertCircle,
  BookOpen,
  ChevronRight,
  ChevronDown,
  Target,
  TrendingUp,
  Bot,
  Brain,
  BarChart3
} from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { V2ChatInterface } from '@/components/chatbot/V2ChatInterface'
import { V2ChatbotWidget } from '@/components/chatbot/V2ChatbotWidget'
import NetworkVisualizer from '@/components/network/NetworkVisualizer'

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
  cited_by_count?: number  // Citation count from API
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
      {/* Document Header */}


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
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-base">
                <div className="flex items-center gap-2">
                  <Target className="h-4 w-4 text-blue-600" />
                  <span className="text-blue-900">Interventions & Results ({interventions.length})</span>
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
                                    <Badge variant="outline" className="text-xs bg-green-100 text-green-700">
                                      {result.effect_direction}
                                    </Badge>
                                  </div>
                                  
                                  {/* Quantitative measures */}
                                  {(result.effect_size || result.effect_size_type || result.uncertainty || result.p_value) && (
                                    <div className="mb-2">
                                      {result.effect_size_type && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">Effect Type: </span>
                                          {result.effect_size_type}
                                        </div>
                                      )}
                                      {result.effect_size && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">Effect Size: </span>
                                          {result.effect_size}
                                        </div>
                                      )}
                                      {result.uncertainty && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">Uncertainty: </span>
                                          ±{result.uncertainty}
                                        </div>
                                      )}
                                      {result.p_value && (
                                        <div className="text-xs text-green-600 mb-1">
                                          <span className="font-medium">P-value: </span>
                                          {result.p_value}
                                        </div>
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
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between text-base">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-purple-600" />
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

export default function AnalysisResultsPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasLoadedData, setHasLoadedData] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const hasStartedPollingRef = useRef<string | null>(null) // Track which project we're polling
  const lastRefreshTimeRef = useRef<number>(0) // Throttle refreshes
  const [activeTab, setActiveTab] = useState('summary')
  const [evidenceSubTab, setEvidenceSubTab] = useState('interventions')
  const [insightsSubTab, setInsightsSubTab] = useState('network')
  
  // Data states
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [interventions, setInterventions] = useState<InterventionData[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)
  
  // Document detail view state
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [documentDetail, setDocumentDetail] = useState<DocumentDetailResult | null>(null)
  const [loadingDocumentDetail, setLoadingDocumentDetail] = useState(false)
  const [documentDetailError, setDocumentDetailError] = useState<string | null>(null)

  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth, getDocumentExtraction, getAnalysisProject, getProjectInterventions } = useAPI()

  // Get search parameters (memoized to prevent re-runs)
  const searchConfig = useMemo(() => ({
    query: searchParams.get('query') || '',
    projectId: searchParams.get('project_id') || '',
    sources: searchParams.get('sources')?.split(',') || [],
    limit: parseInt(searchParams.get('limit') || '50'),
    relevanceEnabled: searchParams.get('relevance_enabled') === 'true',
    useAbstractsOnly: searchParams.get('use_abstracts_only') === 'true',
    mode: searchParams.get('mode') || 'semantic',
    booleanQuery: searchParams.get('boolean_query') || ''
  }), [searchParams])

  // Use only active project ID (no URL fallback to avoid confusion)
  const effectiveProjectId = activeProject?.id || ''

  // Define data loading functions
  const loadData = useCallback(async () => {
    if (hasLoadedData || loadingData) return

    // Get current active project ID dynamically
    const currentActiveProject = useAnalysisProjectStore.getState().activeProject
    const currentProjectId = currentActiveProject?.id
    
    if (!currentProjectId) {
      console.log('No active project found, cannot load data')
      return
    }

    console.log('Loading project data for:', currentProjectId)
    setHasLoadedData(true)
    setLoadingData(true)
    setDataError(null)

    try {
      // Load documents and interventions in parallel
      const [docsResponse, interventionsResponse] = await Promise.all([
        fetchWithAuth(`/api/analysis-projects/${currentProjectId}/documents`),
        getProjectInterventions(currentProjectId).catch(error => {
          console.warn('Failed to load interventions:', error)
          return { interventions: [] }
        })
      ])
      
      setDocuments(docsResponse.documents || [])
      setInterventions(interventionsResponse.interventions || [])
    } catch (error) {
      console.error('Failed to load project data:', error)
      setDataError(error instanceof Error ? error.message : 'Failed to load data')
      setHasLoadedData(false)
    } finally {
      setLoadingData(false)
    }
  }, [hasLoadedData, loadingData, fetchWithAuth, getProjectInterventions])

  const refreshData = useCallback(async () => {
    // Throttle refreshes to prevent infinite loops (minimum 5 seconds between calls)
    const now = Date.now()
    if (now - lastRefreshTimeRef.current < 5000) {
      console.log('Refresh throttled - too soon since last refresh')
      return
    }
    lastRefreshTimeRef.current = now

    // Get current active project ID dynamically
    const currentActiveProject = useAnalysisProjectStore.getState().activeProject
    const currentProjectId = currentActiveProject?.id
    
    if (!currentProjectId) {
      console.log('No active project found, cannot refresh data')
      return
    }

    console.log('Refreshing project data for:', currentProjectId)
    setLoadingData(true)
    setDataError(null)

    try {
      // Load documents and interventions in parallel
      const [docsResponse, interventionsResponse] = await Promise.all([
        fetchWithAuth(`/api/analysis-projects/${currentProjectId}/documents`),
        getProjectInterventions(currentProjectId).catch(error => {
          console.warn('Failed to refresh interventions:', error)
          return { interventions: [] }
        })
      ])
      
      setDocuments(docsResponse.documents || [])
      setInterventions(interventionsResponse.interventions || [])
      // Mark as loaded if it wasn't already
      if (!hasLoadedData) {
        setHasLoadedData(true)
      }
    } catch (error) {
      console.error('Failed to refresh project data:', error)
      setDataError(error instanceof Error ? error.message : 'Failed to load data')
    } finally {
      setLoadingData(false)
    }
  }, [fetchWithAuth, getProjectInterventions]) // eslint-disable-line react-hooks/exhaustive-deps
  
  // Handle case where URL has project ID but no active project is set
  useEffect(() => {
    const urlProjectId = searchConfig.projectId
    if (urlProjectId && (!activeProject || activeProject.id !== urlProjectId)) {
      console.log(`URL has project ID ${urlProjectId} but active project is ${activeProject?.id || 'none'}`)
      console.log('Redirecting to projects page to select the correct project')
      router.push('/v2/projects')
    }
  }, [searchConfig.projectId, activeProject, router])

  // Reset flags when project changes
  useEffect(() => {
    setHasLoadedData(false)
    setAnalysisComplete(false)
    setError(null)
    setDocuments([])
    setInterventions([])
    // Also reset polling refs
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    hasStartedPollingRef.current = null
    setIsPolling(false)
  }, [effectiveProjectId])

  // Stop polling when analysis is complete (safety mechanism)
  useEffect(() => {
    if (analysisComplete && pollingIntervalRef.current) {
      console.log('Analysis complete detected - ensuring polling is stopped')
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
      setIsPolling(false)
      hasStartedPollingRef.current = null
    }
  }, [analysisComplete])

  // Start polling when project ID is available and check if analysis is running
  useEffect(() => {
    if (!effectiveProjectId) {
      console.log('No effective project ID, skipping polling setup')
      return
    }

    // Check if we're already polling this project
    if (hasStartedPollingRef.current === effectiveProjectId) {
      console.log(`Already polling project ${effectiveProjectId}, skipping duplicate setup`)
      return
    }

    // Check if analysis is already complete (skip polling for completed projects)
    if (analysisComplete) {
      console.log(`Analysis already complete for project ${effectiveProjectId}, skipping polling setup`)
      return
    }

    console.log(`Setting up polling for project: ${effectiveProjectId}`)

    // Clear any existing polling
    if (pollingIntervalRef.current) {
      console.log('Clearing existing polling interval')
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }

    // Mark this project as being polled
    hasStartedPollingRef.current = effectiveProjectId

    const checkProjectStatus = async () => {
      try {
        // Get current active project ID dynamically (not from closure)
        const currentActiveProject = useAnalysisProjectStore.getState().activeProject
        const currentProjectId = currentActiveProject?.id
        
        if (!currentProjectId) {
          console.log('No active project found, stopping polling')
          return true // Stop polling if no active project
        }
        
        // Check if this polling instance is still for the current project
        if (currentProjectId !== effectiveProjectId) {
          console.log(`Project changed from ${effectiveProjectId} to ${currentProjectId}, stopping this polling instance`)
          return true // Stop this polling instance as project has changed
        }
        
        console.log(`Checking status for project: ${currentProjectId}`)
        const projectData = await getAnalysisProject(currentProjectId)
        const project = projectData.project

        // Update active project with latest data
        const { setActiveProject: updateActiveProject } = useAnalysisProjectStore.getState()
        updateActiveProject({
          ...currentActiveProject,
          status: project.status,
          run_id: project.run_id,
          total_references: project.total_references,
          relevant_references: project.relevant_references
        })

        // Check if analysis is complete
        console.log(`Project status: ${project.status}`)
        
        if (project.status === 'completed') {
          console.log('✅ Analysis COMPLETED - stopping polling')
          setAnalysisComplete(true)
          return true
        } else if (project.status === 'failed') {
          console.log('❌ Analysis FAILED - stopping polling')
          setError('Analysis failed. Please try again.')
          return true
        } else if (project.status === 'created') {
          console.log('📝 Project exists but analysis not started - stopping polling')
          setAnalysisComplete(true)
          return true
        } else if (project.status === 'running') {
          console.log('🔄 Analysis still RUNNING - continuing to poll')
        } else {
          console.log(`⚠️ Unknown status: ${project.status} - continuing to poll`)
        }

        return false
      } catch (error) {
        console.error('Failed to poll project status:', error)
        return false
      }
    }



    const startPolling = async () => {
      console.log('Starting to check project status for:', effectiveProjectId)
      
      // Always load data initially, regardless of status
      console.log('Loading initial data...')
      loadData()
      
      // Check initial status
      const isComplete = await checkProjectStatus()
      
      if (isComplete) {
        // Analysis is already complete, no need to continue polling
        console.log('Analysis already complete, no polling needed')
      } else {
        // Analysis is still running, start polling every 20 seconds
        console.log('Analysis in progress, starting 20-second polling')
        setIsPolling(true)
        
        pollingIntervalRef.current = setInterval(async () => {
          // Check if we should still be polling (prevent race conditions)
          if (!pollingIntervalRef.current) {
            console.log('Polling interval already cleared, skipping...')
            return
          }
          
          console.log('Polling project status and refreshing data...')
          
          // Always refresh data during polling to get stepwise updates
          await refreshData()
          
          const isComplete = await checkProjectStatus()
          if (isComplete) {
            console.log('Analysis completed! Stopping polling immediately.')
            
            // Clear interval immediately
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current)
              pollingIntervalRef.current = null
            }
            
            // Reset polling state
            setIsPolling(false)
            hasStartedPollingRef.current = null
            
            // Refresh data one final time to ensure we have the complete results
            await refreshData()
          } else {
            console.log('Analysis still running, will check again in 20 seconds...')
          }
        }, 20000) // Poll every 20 seconds
      }
    }

    startPolling()

    // Cleanup function
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
        setIsPolling(false)
      }
      hasStartedPollingRef.current = null
    }
  }, [effectiveProjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load data when navigating to a project that hasn't been loaded yet
  useEffect(() => {
    if (effectiveProjectId && !hasLoadedData && !loadingData) {
      console.log('Initial load for new project:', effectiveProjectId)
      loadData()
    }
  }, [effectiveProjectId, hasLoadedData, loadingData]) // eslint-disable-line react-hooks/exhaustive-deps

  const goBackToSearch = () => {
    router.push('/v2/search')
  }

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
  }, [effectiveProjectId, getDocumentExtraction])

  // Close document detail view
  const closeDocumentDetail = () => {
    setSelectedDocumentId(null)
    setDocumentDetail(null)
    setDocumentDetailError(null)
  }

  // Transform documents for table display
  const transformedPapers: Paper[] = documents.map((doc: AnalysisDocument) => ({
    id: String(doc.id || doc.doc_id || `doc-${Math.random()}`),
    title: String(doc.title || 'Untitled'),
    doi: String(doc.doi || ''),
    publication_year: Number(doc.year || 0),
    cited_by_count: Number(doc.cited_by_count || 0),
    authors: Array.isArray(doc.authors) ? doc.authors : ['Unknown'],
    is_relevant: Boolean(doc.is_relevant !== false),
    abstract: doc.abstract_or_summary,
    relevance_reason: doc.relevance_reason,
    confidence: doc.relevance_confidence,
    source_country: doc.source_country,
    source_type: doc.source_type,
    venue: doc.venue,
    top_line: doc.top_line,
    landing_page_url: doc.landing_page_url,
    full_text_available: doc.full_text_available,
    extraction_status: doc.extraction_status
  }))

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
                onClick={goBackToSearch}
                className="flex items-center gap-2"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Search
              </Button>
            </div>
            <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
            Results
              {isPolling && (
                <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
              )}
            </h1>
            <p className="text-slate-600 mt-1">
              {searchConfig.query ? (
                <>&quot;{searchConfig.query}&quot;</>
              ) : activeProject ? (
                <>Project: {activeProject.title}</>
              ) : (
                <>No Project Selected</>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-slate-50">

        {/* Show error state */}
        {error && (
          <div className="p-6">
            <div className="max-w-4xl mx-auto">
              <Card>
                <CardContent className="p-6">
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-red-800 font-medium mb-2">
                      <AlertCircle className="h-4 w-4" />
                      Analysis Failed
                    </div>
                    <p className="text-red-700 text-sm">{error}</p>
                    <Button 
                      onClick={() => window.location.reload()} 
                      size="sm" 
                      variant="outline" 
                      className="mt-3"
                    >
                      Try Again
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Show empty state if no project is selected */}
        {!effectiveProjectId && !error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center p-8">
              <FileText className="h-16 w-16 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Project Selected</h3>
              <p className="text-slate-600 mb-6">
                Please select a project or start a new analysis to view results.
              </p>
              <div className="flex gap-3 justify-center">
                <Button onClick={() => router.push('/v2/projects')} variant="outline">
                  <FileText className="h-4 w-4 mr-2" />
                  View Projects
                </Button>
                <Button onClick={() => router.push('/v2/search')}>
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Start New Search
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Show results tabs */}
        {effectiveProjectId && (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
            <div className="px-6 pt-4">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="summary" className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Extraction
                </TabsTrigger>
                <TabsTrigger value="evidence" className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  Evidence
                </TabsTrigger>
                <TabsTrigger value="assistant" className="flex items-center gap-2">
                  <Bot className="h-4 w-4" />
                  Assistant
                </TabsTrigger>
                <TabsTrigger value="insights" className="flex items-center gap-2">
                  <Brain className="h-4 w-4" />
                  Insights
                </TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-auto">
              <TabsContent value="summary" className="p-6 m-0">
                <div className="max-w-6xl mx-auto">


                  {/* Document List */}
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
                      <div className="flex items-center justify-between">
                      </div>
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
                </div>
              </TabsContent>

              <TabsContent value="evidence" className="p-6 m-0">
                <div className="max-w-6xl mx-auto">
                  {/* Evidence Sub-tabs as smaller buttons */}
                  <div className="mb-6">
                    <div className="flex gap-2">
                    <Button
                        variant={evidenceSubTab === 'interventions' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setEvidenceSubTab('interventions')}
                        className="flex items-center gap-2"
                      >
                        <Target className="h-3 w-3" />
                        Interventions ({interventions.length})
                      </Button>                      
                      <Button
                        variant={evidenceSubTab === 'documents' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setEvidenceSubTab('documents')}
                        className="flex items-center gap-2"
                      >
                        <FileText className="h-3 w-3" />
                        Documents ({documents.length})
                      </Button>

                    </div>
                  </div>

                  {/* Content based on active sub-tab */}
                  {evidenceSubTab === 'documents' && (
                    <div>
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
                        <PapersTable papers={transformedPapers} />
                      ) : (
                        <div className="text-center py-12">
                          <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-slate-900 mb-2">No Documents Available</h3>
                          <p className="text-slate-600">Documents will appear here once the analysis is processed.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {evidenceSubTab === 'interventions' && (
                    <div>
                      <InterventionsTable 
                        interventions={interventions} 
                        loading={loadingData}
                      />
                    </div>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="assistant" className="m-0 h-[600px]">
                <V2ChatInterface 
                  autoFocus={activeTab === 'assistant'}
                  placeholder="Ask about the evidence in this project..."
                  className="h-full"
                />
              </TabsContent>

              <TabsContent value="insights" className="p-6 m-0">
                <div className="max-w-6xl mx-auto">
                  {/* Insights Sub-tabs as smaller buttons */}
                  <div className="mb-6">
                    <div className="flex gap-2">
                      <Button
                        variant={insightsSubTab === 'network' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setInsightsSubTab('network')}
                        className="flex items-center gap-2"
                      >
                        <Brain className="h-3 w-3" />
                        Network
                      </Button>
                      <Button
                        variant={insightsSubTab === 'charts' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setInsightsSubTab('charts')}
                        className="flex items-center gap-2"
                      >
                        <BarChart3 className="h-3 w-3" />
                        Charts
                      </Button>
                    </div>
                  </div>

                  {/* Content based on active sub-tab */}
                  {insightsSubTab === 'network' && (
                    <div>
                      <NetworkVisualizer />
                    </div>
                  )}

                  {insightsSubTab === 'charts' && (
                    <div className="text-center py-12">
                      <BarChart3 className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-slate-900 mb-2">Charts Coming Soon</h3>
                      <p className="text-slate-600">Interactive charts and analytics will be available here.</p>
                    </div>
                  )}
                </div>
              </TabsContent>
            </div>
          </Tabs>
        )}
      </div>

      {/* Floating Chatbot Widget */}
      <V2ChatbotWidget />
    </div>
  )
}