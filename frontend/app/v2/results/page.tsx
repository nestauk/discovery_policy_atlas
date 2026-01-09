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
  Target,
  Bot,
  Filter,
  Download
} from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { useAuth } from '@clerk/nextjs'
import { SynthesisSummary } from '@/types/search'
import { ExecutiveBriefing } from './ExecutiveBriefing'
import { V2ChatInterface } from '@/components/chatbot/V2ChatInterface'
import { V2ChatbotWidget } from '@/components/chatbot/V2ChatbotWidget'
import { ProjectCharts } from '@/components/charts/ProjectCharts'
import { InterventionsNavigator } from '@/components/v2/interventions/InterventionsNavigator'
import type { InterventionData } from '@/components/search/interventions-table'
import { PapersTable } from '@/components/search/papers-table'
import { SearchPlanModal } from '@/components/v2/results/SearchPlanModal'

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
  const showRerunButton = process.env.NEXT_PUBLIC_SHOW_SYNTHESIS_RERUN === 'true'
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasLoadedData, setHasLoadedData] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const hasStartedPollingRef = useRef<string | null>(null) // Track which project we're polling
  const lastRefreshTimeRef = useRef<number>(0) // Throttle refreshes
  const [activeTab, setActiveTab] = useState('summary')
  const [summaryData, setSummaryData] = useState<SynthesisSummary | null>(null)
  const [isLoadingSummary, setIsLoadingSummary] = useState(false)
  const [evidenceSubTab, setEvidenceSubTab] = useState('interventions')
  
  // Relevance filtering state
  const [showRelevantOnly, setShowRelevantOnly] = useState(true)
  
  // Column visibility state - controls Study Type, Sample Size, Source, Status
  const [showAdditionalColumns, setShowAdditionalColumns] = useState(false)
  
  // Documents download state
  const [isPreparingDocumentsDownload, setIsPreparingDocumentsDownload] = useState(false)
  
  // Interventions view state
  const [interventionsGroupByIssues, setInterventionsGroupByIssues] = useState(false)
  const [interventionsSortBy, setInterventionsSortBy] = useState<'frequency' | 'impact' | 'evidence'>('frequency')
  const [isPreparingInterventionsDownload, setIsPreparingInterventionsDownload] = useState(false)
  
  // Data states
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [interventions, setInterventions] = useState<InterventionData[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)
  const [isRerunningSynthesis, setIsRerunningSynthesis] = useState(false)
  const [rerunError, setRerunError] = useState<string | null>(null)

  const { activeProject, setActiveProject, projects, setProjects } = useAnalysisProjectStore()
  const { fetchWithAuth, getAnalysisProject, getProjectInterventions, rerunSynthesisForProject } = useAPI()
  const { getToken } = useAuth()

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

  const handleRerunSynthesis = useCallback(async () => {
    if (!activeProject?.id || isRerunningSynthesis) return

    const forceFlag = true
    if (activeProject.status === 'running') {
      const confirmed = window.confirm(
        'Synthesis is currently running. Force rerun anyway? This will start a new synthesis run.'
      )
      if (!confirmed) return
    }

    setIsRerunningSynthesis(true)
    setRerunError(null)

    try {
      await rerunSynthesisForProject(activeProject.id, {
        force: forceFlag,
        invalidate_previous: true,
      })

      const updated = { ...activeProject, status: 'running' as const }
      setActiveProject(updated)
      setProjects(projects.map((p) => (p.id === updated.id ? { ...p, status: updated.status } : p)))
    } catch (error) {
      console.error('Failed to rerun synthesis', error)
      setRerunError('Failed to start synthesis rerun')
    } finally {
      setIsRerunningSynthesis(false)
    }
  }, [activeProject, isRerunningSynthesis, rerunSynthesisForProject, setActiveProject, setProjects, projects])

  const handleDownloadDocumentsCSV = useCallback(async () => {
    if (!effectiveProjectId) return
    
    setIsPreparingDocumentsDownload(true)
    
    try {
      console.log('Requesting documents CSV for project:', effectiveProjectId)
      const response = await fetchWithAuth(`/api/analysis-projects/${effectiveProjectId}/download/documents-csv`)
      console.log('Documents CSV response:', response)
      
      // Immediately trigger download using the download key
      if (response.download_key) {
        console.log('Got download key, proceeding with download:', response.download_key)
        const token = await getToken()
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        const cleanBaseUrl = baseUrl.replace(/\/$/, '')
        
        const downloadResponse = await fetch(`${cleanBaseUrl}/api/download/${response.download_key}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'text/csv',
          },
        })
        
        console.log('Download response status:', downloadResponse.status)
        
        if (downloadResponse.ok) {
          // Simple approach: generate filename on frontend with project name
          const projectName = activeProject?.title || 'project'
          const cleanProjectName = projectName.replace(/[^a-zA-Z0-9\s]/g, '').replace(/\s+/g, '_')
          const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '_')
          const filename = `${cleanProjectName}_documents_${timestamp}.csv`
          
          console.log('Generated filename:', filename)

          const blob = await downloadResponse.blob()
          const url = window.URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = filename
          document.body.appendChild(a)
          a.click()
          window.URL.revokeObjectURL(url)
          document.body.removeChild(a)
          console.log('Download completed successfully')
        } else {
          const errorText = await downloadResponse.text()
          console.error('Download failed:', downloadResponse.status, errorText)
          alert(`Failed to download file: ${downloadResponse.status}`)
        }
      } else {
        console.error('No download key received:', response)
        alert('No download key received from server')
      }
    } catch (err) {
      console.error('Failed to download documents CSV:', err)
      alert('Failed to download documents CSV. Please try again.')
    } finally {
      setIsPreparingDocumentsDownload(false)
    }
  }, [effectiveProjectId, fetchWithAuth, getToken, activeProject?.title])
  
  const handleDownloadInterventionsCSV = useCallback(async () => {
    if (!effectiveProjectId) return
    
    setIsPreparingInterventionsDownload(true)
    
    try {
      const response = await fetchWithAuth(`/api/analysis-projects/${effectiveProjectId}/download/interventions-csv`)
      
      if (response.download_key) {
        const token = await getToken()
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        const cleanBaseUrl = baseUrl.replace(/\/$/, '')
        
        const downloadResponse = await fetch(`${cleanBaseUrl}/api/download/${response.download_key}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'text/csv',
          },
        })
        
        if (downloadResponse.ok) {
          const projectName = activeProject?.title || 'project'
          const cleanProjectName = projectName.replace(/[^a-zA-Z0-9\s]/g, '').replace(/\s+/g, '_')
          const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '_')
          const filename = `${cleanProjectName}_interventions_${timestamp}.csv`

          const blob = await downloadResponse.blob()
          const url = window.URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = filename
          document.body.appendChild(a)
          a.click()
          window.URL.revokeObjectURL(url)
          document.body.removeChild(a)
        } else {
          alert('Failed to download file')
        }
      }
    } catch (err) {
      console.error('Failed to download interventions CSV:', err)
      alert('Failed to download interventions CSV. Please try again.')
    } finally {
      setIsPreparingInterventionsDownload(false)
    }
  }, [effectiveProjectId, fetchWithAuth, getToken, activeProject?.title])
  
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
          relevant_references: project.relevant_references,
          search_query: project.search_query  // Include search_query data
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
          console.log('🔄 Analysis still RUNNING (extraction phase) - continuing to poll')
        } else if (project.status === 'synthesising') {
          console.log('🔄 Analysis SYNTHESISING (generating summary) - continuing to poll')
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
        setSummaryData(null) // Reset on error to prevent invalid state
      } finally {
        setIsLoadingSummary(false)
      }
    }
    fetchSummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, effectiveProjectId])


  // --- Stat Cards for Summary Tab ---
  // Intervention group and intervention counts from navigator API
  const [navigatorStats, setNavigatorStats] = useState({
    interventionGroupCount: null as number | null,
    interventionCount: null as number | null,
    loading: true,
    error: null as string | null,
  });

  useEffect(() => {
    async function fetchNavigatorStats() {
      if (!effectiveProjectId) return;
      setNavigatorStats(prev => ({ ...prev, loading: true, error: null }));
      try {
        const response = await fetchWithAuth(`/api/analysis-projects/${effectiveProjectId}/issue-intervention-navigator`);
        // Count unique intervention themes (groups)
        const interventionThemeNames = new Set<string>();
        const interventionNames = new Set<string>();
        if (response?.issue_themes) {
          response.issue_themes.forEach((issue: { related_interventions?: { theme_name?: string; detailed_interventions?: { name?: string }[] }[] }) => {
            issue.related_interventions?.forEach((intervention) => {
              if (intervention.theme_name) interventionThemeNames.add(intervention.theme_name);
              // Count unique detailed interventions by name
              intervention.detailed_interventions?.forEach((d) => {
                if (d.name) interventionNames.add(d.name);
              });
            });
          });
        }
        setNavigatorStats({
          interventionGroupCount: interventionThemeNames.size,
          interventionCount: interventionNames.size,
          loading: false,
          error: null,
        });
        if (typeof window !== 'undefined') {
          console.log('[StatCards] Intervention themes:', Array.from(interventionThemeNames));
          console.log('[StatCards] Detailed interventions:', Array.from(interventionNames));
        }
      } catch (err) {
        setNavigatorStats({
          interventionGroupCount: null,
          interventionCount: null,
          loading: false,
          error: (err as Error)?.message || 'Failed to load intervention stats',
        });
      }
    }
    fetchNavigatorStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveProjectId]);

  const overtonCount = documents.filter(doc => doc.source === 'overton').length;
  const openalexCount = documents.filter(doc => doc.source === 'openalex').length;
  // Debug output
  if (typeof window !== 'undefined') {
    // console.log('[StatCards] Unique intervention names:', uniqueInterventionNames);
    // console.log('[StatCards] Unique group names:', uniqueGroupNames);
    console.log('[StatCards] Interventions raw:', interventions);
    console.log('[StatCards] Overton:', overtonCount, 'OpenAlex:', openalexCount);
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

  // Calculate progress based on project status and document extraction status
  const progressInfo = useMemo(() => {
    if (!effectiveProjectId || !activeProject) {
      return { stage: 'idle', progress: 0, text: 'No project selected' }
    }

    const status = activeProject.status
    
    if (status === 'created') {
      return { stage: 'created', progress: 0, text: 'Analysis not started' }
    }
    
    if (status === 'running') {
      // Check if we have documents to determine stage
      if (documents.length === 0) {
        return { stage: 'retrieving', progress: 25, text: 'Retrieving and screening documents...' }
      }
      
      // Calculate extraction progress based on relevant documents only
      const relevantDocs = documents.filter(doc => doc.is_relevant !== false)
      const totalRelevantDocs = relevantDocs.length
      const extractedDocs = relevantDocs.filter(doc => 
        doc.extraction_status === 'completed' || doc.extraction_status === 'success'
      ).length
      
      if (extractedDocs === 0) {
        return { stage: 'extracting', progress: 50, text: 'Extracting intervention data from documents...' }
      }
      
      // Still extracting - scale progress from 50% to 70%
      const extractionProgress = Math.round((extractedDocs / totalRelevantDocs) * 20) + 50
      return { 
        stage: 'extracting', 
        progress: Math.min(extractionProgress, 70), 
        text: `Extracting intervention data from documents... (${extractedDocs}/${totalRelevantDocs})` 
      }
    }
    
    if (status === 'synthesising') {
      // Extraction complete, synthesis in progress
      return { 
        stage: 'synthesising', 
        progress: 85, 
        text: 'Generating summary and insights...' 
      }
    }
    
    if (status === 'completed') {
      return { stage: 'completed', progress: 100, text: 'Analysis completed' }
    }
    
    if (status === 'failed') {
      return { stage: 'failed', progress: 0, text: 'Analysis failed' }
    }
    
    return { stage: 'unknown', progress: 0, text: 'Unknown status' }
  }, [effectiveProjectId, activeProject, documents])

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
            <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
            Results
              {isPolling && (
                <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
              )}
            </h1>
            {/* Progress Indicator */}
            {effectiveProjectId && activeProject && (
              <div className="flex items-center gap-3 mt-2 mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-32 bg-slate-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out"
                      style={{ width: `${progressInfo.progress}%` }}
                    />
                  </div>
                  <span className="text-sm text-slate-600 font-medium">
                    {progressInfo.progress}%
                  </span>
                </div>
                <span className="text-sm text-slate-600">
                  {progressInfo.text}
                </span>
              </div>
            )}
          </div>
          
          {/* Search Plan Settings Button */}
          {effectiveProjectId && activeProject?.search_query && (
            <div>
              <SearchPlanModal project={activeProject} />
            </div>
          )}
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
              <TabsList className="!grid w-full grid-cols-3">
                <TabsTrigger value="summary" className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Summary
                </TabsTrigger>
                <TabsTrigger value="evidence" className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  Evidence
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
                  {/* Stat Cards Row - only in summary tab */}
                  <div className="flex flex-wrap gap-4 mb-8">
                    <div className="bg-white rounded-lg shadow p-4 flex-1 min-w-[140px] text-center">
                      <div className="text-2xl font-bold">{overtonCount}</div>
                      <div className="text-xs text-slate-500">Policy documents (Overton)</div>
                    </div>
                    <div className="bg-white rounded-lg shadow p-4 flex-1 min-w-[140px] text-center">
                      <div className="text-2xl font-bold">{openalexCount}</div>
                      <div className="text-xs text-slate-500">Academic documents (OpenAlex)</div>
                    </div>
                    <div className="bg-white rounded-lg shadow p-4 flex-1 min-w-[140px] text-center">
                      <div className="text-2xl font-bold">{navigatorStats.loading ? '...' : navigatorStats.interventionGroupCount ?? '-'}</div>
                      <div className="text-xs text-slate-500">Intervention themes</div>
                    </div>
                    <div className="bg-white rounded-lg shadow p-4 flex-1 min-w-[140px] text-center">
                      <div className="text-2xl font-bold">{navigatorStats.loading ? '...' : navigatorStats.interventionCount ?? '-'}</div>
                      <div className="text-xs text-slate-500">Interventions</div>
                    </div>
                    <button
                      className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-6 flex items-center font-semibold transition min-w-[180px] justify-center shadow-md shadow-blue-200/40"
                      style={{ color: 'white' }}
                      onClick={() => setActiveTab('evidence')}
                    >
                      Explore Interventions
                      <span className="ml-2">→</span>
                    </button>
                  </div>
                  {/* Executive Briefing and charts */}
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
                      <ExecutiveBriefing 
                        briefing={summaryData.executive_briefing}
                        structuredBriefing={summaryData.structured_briefing}
                        citationMap={summaryData.citation_map}
                        evidenceCoverage={summaryData.evidence_coverage}
                        {...(showRerunButton
                          ? {
                              onRerunSynthesis: handleRerunSynthesis,
                              isRerunningSynthesis,
                              rerunError,
                            }
                          : {})}
                        onCitationClick={() => {
                          // Navigate to evidence tab and highlight the document
                          setActiveTab('evidence');
                          setEvidenceSubTab('documents');
                        }}
                      />
                      <ProjectCharts projectId={effectiveProjectId} projectTitle={activeProject?.title} />
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
                          variant={evidenceSubTab === 'interventions' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setEvidenceSubTab('interventions')}
                          className="flex items-center gap-2"
                        >
                          <Target className="h-3 w-3" />
                          Interventions
                        </Button>
                        <Button
                          variant={evidenceSubTab === 'documents' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setEvidenceSubTab('documents')}
                          className="flex items-center gap-2"
                        >
                          <FileText className="h-3 w-3" />
                          Documents ({showRelevantOnly ? relevantCount : documents.length})
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
                          
                          {/* Documents Download Button */}
                          <div className="flex items-center gap-2">
                            <Button
                              onClick={handleDownloadDocumentsCSV}
                              disabled={isPreparingDocumentsDownload || documents.length === 0}
                              variant="outline"
                              size="sm"
                              className="flex items-center gap-2"
                            >
                              <Download className="h-4 w-4" />
                              {isPreparingDocumentsDownload ? 'Downloading...' : 'Download'}
                            </Button>
                          </div>
                        </div>
                      )}
                      
                      {/* Controls for interventions */}
                      {evidenceSubTab === 'interventions' && (
                        <div className="flex items-center gap-6">
                          <div className="flex items-center gap-2">
                            <Label htmlFor="group-by-issues" className="text-sm text-slate-700">
                              Group by issues
                            </Label>
                            <Switch
                              id="group-by-issues"
                              checked={interventionsGroupByIssues}
                              onCheckedChange={setInterventionsGroupByIssues}
                            />
                          </div>
                          
                          <div className="flex items-center gap-2">
                            <Label className="text-sm text-slate-700">Sort by:</Label>
                            <select 
                              value={interventionsSortBy}
                              onChange={(e) => setInterventionsSortBy(e.target.value as 'frequency' | 'impact' | 'evidence')}
                              className="text-sm border rounded px-2 py-1 bg-white"
                            >
                              <option value="impact">Impact</option>
                              <option value="evidence">Evidence</option>
                              <option value="frequency">Frequency</option>
                            </select>
                          </div>
                          
                          {/* Interventions Download Button */}
                          <div className="flex items-center gap-2">
                            <Button
                              onClick={handleDownloadInterventionsCSV}
                              disabled={isPreparingInterventionsDownload}
                              variant="outline"
                              size="sm"
                              className="flex items-center gap-2"
                            >
                              <Download className="h-4 w-4" />
                              {isPreparingInterventionsDownload ? 'Downloading...' : 'Download'}
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Content based on active sub-tab */}
                  {evidenceSubTab === 'interventions' && (
                    <div>
                      <InterventionsNavigator 
                        showHeader={false}
                        viewMode={interventionsGroupByIssues ? 'grouped' : 'all'}
                        onViewModeChange={(mode) => setInterventionsGroupByIssues(mode === 'grouped')}
                        sortBy={interventionsSortBy}
                        onSortByChange={setInterventionsSortBy}
                        onDownload={handleDownloadInterventionsCSV}
                        isPreparingDownload={isPreparingInterventionsDownload}
                      />
                    </div>
                  )}

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