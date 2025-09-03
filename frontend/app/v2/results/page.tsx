'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { 
  FileText, 
  Loader2,
  ArrowLeft,
  AlertCircle,
  BookOpen,
  Bot,
  Filter,
  Target,
  AlertTriangle,
  Brain,
  BarChart3
} from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import NetworkVisualizer from '@/components/network/NetworkVisualizer'
import { SynthesisSummary } from '@/types/search'
import { KeyIssuesTable } from './KeyIssuesTable'
import { InterventionsTable } from './InterventionsTable'
import { ExecutiveBriefing } from './ExecutiveBriefing'
import { V2ChatInterface } from '@/components/chatbot/V2ChatInterface'
import { V2ChatbotWidget } from '@/components/chatbot/V2ChatbotWidget'
import EvidenceThematicView from '@/components/v2/evidence/EvidenceThematicView'
import type { InterventionData } from '@/components/search/interventions-table'
import { PapersTable } from '@/components/search/papers-table'

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
  text_source?: string  // "full_text" or "abstract" - what was used for extraction
  study_strength?: string  // strongest study type letter from interventions
  sample_size?: number  // largest sample size from interventions
  cited_by_count?: number  // Citation count from API
  extraction_results?: {
    conclusion?: {
      top_line_summary?: string
      detailed_explanation?: string
      supporting_quote?: string
      evidence_strength?: {
        stars: number | null
        justification: string
        evidence_gap?: string | null
      }
      predicted_impact?: {
        stars: number | null
        justification: string
        evidence_gap?: string | null
      }
    }
    issues?: unknown[]
    interventions?: unknown[]
    mappings?: unknown[]
    results?: unknown[]
  }
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
  const [activeTab, setActiveTab] = useState('evidence')
  const [summaryData, setSummaryData] = useState<SynthesisSummary | null>(null)
  const [isLoadingSummary, setIsLoadingSummary] = useState(false)
  // const [activeTab, setActiveTab] = useState('summary')
  const [evidenceSubTab, setEvidenceSubTab] = useState('documents')
  
  // Relevance filtering state
  const [showRelevantOnly, setShowRelevantOnly] = useState(true)
  
  // Column visibility state - controls Study Type, Sample Size, Source, Status
  const [showAdditionalColumns, setShowAdditionalColumns] = useState(false)
  const [insightsSubTab, setInsightsSubTab] = useState('network')
  
  // Data states
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [interventions, setInterventions] = useState<InterventionData[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)

  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth, getAnalysisProject, getProjectInterventions } = useAPI()

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

  // Lazy-fetch summary data when summary tab is opened first time
  // Fetch summary when Summary tab is opened or project changes
  useEffect(() => {
    const fetchSummary = async () => {
      if (activeTab !== 'summary') return
      if (!effectiveProjectId) return
      if (isLoadingSummary) return
      setIsLoadingSummary(true)
              try {
          console.log('[ResultsPage] Fetching summary for project:', effectiveProjectId);
          const data = await fetchWithAuth(`api/analysis-projects/${effectiveProjectId}/summary`)
          console.log('[ResultsPage] Summary data received:', {
            hasExecutiveBriefing: !!data.executive_briefing,
            briefingLength: data.executive_briefing?.length || 0,
            issuesCount: data.key_issues?.length || 0,
            interventionsCount: data.interventions?.length || 0
          });
          setSummaryData(data as SynthesisSummary)
        } catch (err) {
        console.error('Failed to fetch summary data', err)
      } finally {
        setIsLoadingSummary(false)
      }
    }
    fetchSummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, effectiveProjectId])

  const goBackToSearch = () => {
    router.push('/v2/search')
  }

  // Create study strength and sample size mappings from interventions data
  const { studyStrengthMapping, sampleSizeMapping } = useMemo(() => {
    const strengthMapping: Record<string, string> = {}
    const sizeMapping: Record<string, number> = {}
    
    // Study type ranking function (same as backend)
    const getStudyTypeRank = (studyType: string): number => {
      if (!studyType) return 999
      const type = studyType.trim().toLowerCase()
      
      if (type === 'g') return 1  // RCT - highest quality
      if (type === 'h') return 2  // Meta-analysis
      if (type === 'f') return 3  // Quasi-experimental
      if (type === 'e') return 4  // Comparison of outcomes
      if (type === 'd') return 5  // Pre/post study
      if (type === 'c') return 6  // Cross-sectional with controls
      if (type === 'b') return 7  // Pre/post study
      if (type === 'a') return 8  // Cross-sectional
      if (type === 'i') return 9  // Policy recommendation
      if (type === 'j') return 10 // News/opinion
      return 999 // Unknown
    }
    
    // Process interventions to find strongest study type and largest sample size per document
    interventions.forEach((intervention) => {
      intervention.documents?.forEach((doc: { doc_id: string }) => {
        const docId = doc.doc_id
        if (!docId) return
        
        // Get study type from intervention
        const studyType = intervention.highest_study_type
        if (studyType) {
          const currentRank = getStudyTypeRank(studyType)
          const existingStudyType = strengthMapping[docId]
          const existingRank = existingStudyType ? getStudyTypeRank(existingStudyType) : 999
          
          // Keep the strongest (lowest rank number) study type
          if (currentRank < existingRank) {
            strengthMapping[docId] = studyType
          }
        }
        
        // Get sample size from intervention
        const sampleSize = intervention.total_sample_size
        if (sampleSize && sampleSize > 0) {
          const existingSize = sizeMapping[docId] || 0
          // Keep the largest sample size
          if (sampleSize > existingSize) {
            sizeMapping[docId] = sampleSize
          }
        }
      })
    })
    
    return {
      studyStrengthMapping: strengthMapping,
      sampleSizeMapping: sizeMapping
    }
  }, [interventions])

  // Transform documents for table display and apply filtering
  const { transformedPapers, relevantCount } = useMemo(() => {
    const allTransformed = documents.map((doc: AnalysisDocument) => {
      // Extract evidence assessment from conclusion if available
      const conclusion = doc.extraction_results?.conclusion
      const evidenceStrength = conclusion?.evidence_strength
      const predictedImpact = conclusion?.predicted_impact
      
      return {
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
        extraction_status: doc.extraction_status,
        text_source: doc.text_source,
        source: doc.source,
        study_strength: studyStrengthMapping[doc.doc_id] || undefined,
        sample_size: sampleSizeMapping[doc.doc_id] || undefined,
        // Add evidence assessment fields
        evidence_strength: evidenceStrength?.stars || undefined,
        evidence_strength_justification: evidenceStrength?.justification,
        predicted_impact: predictedImpact?.stars || undefined,
        predicted_impact_justification: predictedImpact?.justification
      }
    });

    const relevant = allTransformed.filter(doc => doc.is_relevant);
    
    // Apply filtering based on toggle
    const filtered = showRelevantOnly ? relevant : allTransformed;
    
    return {
      transformedPapers: filtered,
      relevantCount: relevant.length
    };
  }, [documents, showRelevantOnly, studyStrengthMapping, sampleSizeMapping]);

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
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="summary" className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Extraction
                </TabsTrigger>
                <TabsTrigger value="evidence" className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  Evidence
                </TabsTrigger>
                <TabsTrigger value="insights" className="flex items-center gap-2">
                  <Brain className="h-4 w-4" />
                  Insights
                </TabsTrigger>
                <TabsTrigger value="summary" className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Summary
                </TabsTrigger>
                <TabsTrigger value="assistant" className="flex items-center gap-2">
                  <Bot className="h-4 w-4" />
                  Assistant
                </TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-auto">

              <TabsContent value="summary" className="p-6 m-0">
                <div className="max-w-6xl mx-auto">
                  {isLoadingSummary && (
                    <div className="flex items-center justify-center py-12">
                      <div className="text-center">
                        <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                        <p className="text-slate-600">Loading summary...</p>
                      </div>
                    </div>
                  )}
                  {summaryData && (
                    <div className="space-y-8">
                      <ExecutiveBriefing briefing={summaryData.executive_briefing} />
                      <KeyIssuesTable issues={summaryData.key_issues} />
                      <InterventionsTable interventions={summaryData.interventions} />
                    </div>
                  )}
                  {!isLoadingSummary && !summaryData && (
                    <div className="text-center py-12">
                      <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-slate-900 mb-2">No Summary Available</h3>
                      <p className="text-slate-600">Open the Summary tab after analysis completes to load aggregated insights.</p>
                    </div>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="evidence" className="p-6 m-0">
                <div className="max-w-6xl mx-auto">
                  {/* Evidence Sub-tabs as smaller buttons */}
                  <div className="mb-6">
                    <div className="flex items-center justify-between">
                      <div className="flex gap-2">
                        <Button
                          variant={evidenceSubTab === 'documents' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setEvidenceSubTab('documents')}
                          className="flex items-center gap-2"
                        >
                          <FileText className="h-3 w-3" />
                          Documents ({showRelevantOnly ? relevantCount : documents.length})
                        </Button>
                        <Button
                          variant={evidenceSubTab === 'interventions' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setEvidenceSubTab('interventions')}
                          className="flex items-center gap-2"
                        >
                          <Target className="h-3 w-3" />
                          Interventions
                        </Button>
                        <Button
                          variant={evidenceSubTab === 'issues' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setEvidenceSubTab('issues')}
                          className="flex items-center gap-2"
                        >
                          <AlertTriangle className="h-3 w-3" />
                          Key Issues
                        </Button>
                      </div>

                      {/* Filter Toggles (only show for documents) */}
                      {evidenceSubTab === 'documents' && (
                        <div className="flex items-center gap-6">
                          <div className="flex items-center gap-2">
                            <Label htmlFor="additional-columns" className="text-sm text-slate-700">
                              More info
                            </Label>
                            <Switch
                              id="additional-columns"
                              checked={showAdditionalColumns}
                              onCheckedChange={setShowAdditionalColumns}
                            />
                          </div>
                          <div className="flex items-center gap-2">
                            <Label htmlFor="relevance-filter" className="text-sm text-slate-700">
                              Relevant only
                            </Label>
                            <Switch
                              id="relevance-filter"
                              checked={showRelevantOnly}
                              onCheckedChange={setShowRelevantOnly}
                            />
                          </div>
                        </div>
                      )}
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
                      ) : transformedPapers.length > 0 ? (
                        <PapersTable papers={transformedPapers} showAdditionalColumns={showAdditionalColumns} />
                      ) : documents.length > 0 && showRelevantOnly ? (
                        <div className="text-center py-12">
                          <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-slate-900 mb-2">No Relevant Documents</h3>
                          <p className="text-slate-600 mb-4">All {documents.length} documents in this project were marked as non-relevant.</p>
                          <Button 
                            variant="outline" 
                            onClick={() => setShowRelevantOnly(false)}
                            className="flex items-center gap-2"
                          >
                            <Filter className="h-4 w-4" />
                            Show All Documents
                          </Button>
                        </div>
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
                      <EvidenceThematicView projectId={effectiveProjectId} themeType="intervention" />
                    </div>
                  )}

                  {evidenceSubTab === 'issues' && (
                    <div>
                      <EvidenceThematicView projectId={effectiveProjectId} themeType="issue" />
                    </div>
                  )}
                </div>
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

              <TabsContent value="assistant" className="m-0 h-[600px]">
                <V2ChatInterface 
                  autoFocus={activeTab === 'assistant'}
                  placeholder="Ask about the evidence in this project..."
                  className="h-full"
                />
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