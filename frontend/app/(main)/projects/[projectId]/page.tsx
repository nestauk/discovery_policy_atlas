'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
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
  Download
} from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { useAuth } from '@clerk/nextjs'
import { SynthesisSummary } from '@/types/search'
import { ExecutiveBriefing } from '../../results/ExecutiveBriefing'
import { ChatInterface } from '@/components/chatbot/ChatInterface'
import { ChatbotWidget } from '@/components/chatbot/ChatbotWidget'
import { ProjectCharts } from '@/components/charts/ProjectCharts'
import { InterventionsNavigator } from '@/components/interventions/InterventionsNavigator'
import type { InterventionData } from '@/components/interventions/InterventionsTable'
import { PapersTable } from '@/components/documents/PapersTable'
import { SearchPlanModal } from '@/components/results/SearchPlanModal'
import { getEvidenceCategoryRank } from '@/lib/evidenceCategories'

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
  // Evidence categorisation fields
  evidence_category?: string
  evidence_category_rank?: number
  evidence_confidence?: number
  evidence_category_reasoning?: string
  full_text_available?: boolean
  extraction_status?: string
  text_source?: string
  study_strength?: string
  sample_size?: number
  cited_by_count?: number
  // Top-level evidence/impact fields (surfaced by API)
  evidence_strength?: number
  evidence_strength_justification?: string
  predicted_impact?: number
  predicted_impact_justification?: string
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
    }
    issues?: unknown[]
    interventions?: unknown[]
    mappings?: unknown[]
    results?: unknown[]
  }
  impact_score?: number | null
  impact_score_label?: string
  impact_score_breakdown?: Record<string, unknown>
  transferability_score?: number
  transferability_breakdown?: Record<string, unknown>
}

type TabType = 'summary' | 'evidence' | 'assistant'
type EvidenceSubTabType = 'interventions' | 'documents'

export default function ProjectResultsPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const router = useRouter()
  const showRerunButton = process.env.NEXT_PUBLIC_SHOW_SYNTHESIS_RERUN === 'true'
  
  // Get projectId from URL params
  const projectId = params.projectId as string
  
  // Get tab state from URL query params, with defaults and validation
  const tabParam = searchParams.get('tab')
  const validTabs: TabType[] = ['summary', 'evidence', 'assistant']
  const urlTab: TabType = validTabs.includes(tabParam as TabType) ? (tabParam as TabType) : 'summary'
  
  const subtabParam = searchParams.get('subtab')
  const validSubTabs: EvidenceSubTabType[] = ['interventions', 'documents']
  const urlSubTab: EvidenceSubTabType = validSubTabs.includes(subtabParam as EvidenceSubTabType) 
    ? (subtabParam as EvidenceSubTabType) 
    : 'interventions'
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasLoadedData, setHasLoadedData] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const hasStartedPollingRef = useRef<string | null>(null)
  const lastRefreshTimeRef = useRef<number>(0)
  const [summaryData, setSummaryData] = useState<SynthesisSummary | null>(null)
  const [isLoadingSummary, setIsLoadingSummary] = useState(false)

  // Column visibility state
  const [showAdditionalColumns, setShowAdditionalColumns] = useState(false)
  
  // Documents download state
  const [isPreparingDocumentsDownload, setIsPreparingDocumentsDownload] = useState(false)
  
  // Interventions view state
  const [isPreparingInterventionsDownload, setIsPreparingInterventionsDownload] = useState(false)
  
  // Data states
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [interventions, setInterventions] = useState<InterventionData[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)
  const [isRerunningSynthesis, setIsRerunningSynthesis] = useState(false)
  const [rerunError, setRerunError] = useState<string | null>(null)

  const [projectLoading, setProjectLoading] = useState(false)

  const { activeProject, setActiveProject, projects, setProjects } = useAnalysisProjectStore()
  const { fetchWithAuth, getAnalysisProject, getProjectInterventions, rerunSynthesisForProject } = useAPI()
  const { getToken } = useAuth()

  // Update URL when tab changes (without full navigation)
  const updateUrl = useCallback((tab: TabType, subtab?: EvidenceSubTabType) => {
    const params = new URLSearchParams()
    if (tab !== 'summary') {
      params.set('tab', tab)
    }
    if (tab === 'evidence' && subtab && subtab !== 'interventions') {
      params.set('subtab', subtab)
    }
    const queryString = params.toString()
    const newUrl = `/projects/${projectId}${queryString ? `?${queryString}` : ''}`
    router.replace(newUrl, { scroll: false })
  }, [projectId, router])

  // Handle tab changes
  const handleTabChange = useCallback((tab: string) => {
    const newTab = tab as TabType
    // When switching to evidence tab, default to interventions if not already on evidence
    const subtab = newTab === 'evidence' && urlTab !== 'evidence' ? 'interventions' : urlSubTab
    updateUrl(newTab, subtab)
  }, [updateUrl, urlSubTab, urlTab])

  const handleSubTabChange = useCallback((subtab: EvidenceSubTabType) => {
    updateUrl('evidence', subtab)
  }, [updateUrl])

  // Load project from API if not in store or different project
  useEffect(() => {
    const loadProjectIfNeeded = async () => {
      if (!projectId) {
        setError('No project ID provided')
        return
      }
      
      // If we already have this project in store, no need to fetch
      if (activeProject?.id === projectId) return
      
      setProjectLoading(true)
      setError(null)
      try {
        const projectData = await getAnalysisProject(projectId)
        if (projectData?.project) {
          setActiveProject(projectData.project)
        } else {
          setError('Project not found')
        }
      } catch (err) {
        console.error('Failed to load project:', err)
        const errorMessage = err instanceof Error ? err.message : 'Failed to load project'
        setError(errorMessage)
        // If it's a 404, redirect to projects list after a delay
        if (errorMessage.includes('404') || errorMessage.includes('not found')) {
          setTimeout(() => {
            router.push('/projects')
          }, 2000)
        }
      } finally {
        setProjectLoading(false)
      }
    }
    
    loadProjectIfNeeded()
  }, [projectId, activeProject?.id, getAnalysisProject, setActiveProject, router])

  // Define data loading functions
  const loadData = useCallback(async () => {
    if (hasLoadedData || loadingData) return

    if (!projectId) {
      console.log('No project ID, cannot load data')
      return
    }

    console.log('Loading project data for:', projectId)
    setHasLoadedData(true)
    setLoadingData(true)
    setDataError(null)

    try {
      const [docsResponse, interventionsResponse] = await Promise.all([
        fetchWithAuth(`/api/analysis-projects/${projectId}/documents`),
        getProjectInterventions(projectId).catch(error => {
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
  }, [hasLoadedData, loadingData, projectId, fetchWithAuth, getProjectInterventions])

  const refreshData = useCallback(async () => {
    const now = Date.now()
    if (now - lastRefreshTimeRef.current < 5000) {
      console.log('Refresh throttled - too soon since last refresh')
      return
    }
    lastRefreshTimeRef.current = now

    if (!projectId) {
      console.log('No project ID, cannot refresh data')
      return
    }

    console.log('Refreshing project data for:', projectId)
    setLoadingData(true)
    setDataError(null)

    try {
      const [docsResponse, interventionsResponse] = await Promise.all([
        fetchWithAuth(`/api/analysis-projects/${projectId}/documents`),
        getProjectInterventions(projectId).catch(error => {
          console.warn('Failed to refresh interventions:', error)
          return { interventions: [] }
        })
      ])
      
      setDocuments(docsResponse.documents || [])
      setInterventions(interventionsResponse.interventions || [])
      if (!hasLoadedData) {
        setHasLoadedData(true)
      }
    } catch (error) {
      console.error('Failed to refresh project data:', error)
      setDataError(error instanceof Error ? error.message : 'Failed to load data')
    } finally {
      setLoadingData(false)
    }
  }, [projectId, fetchWithAuth, getProjectInterventions, hasLoadedData])

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
    if (!projectId) return
    
    setIsPreparingDocumentsDownload(true)
    
    try {
      console.log('Requesting documents CSV for project:', projectId)
      const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/download/documents-csv`)
      console.log('Documents CSV response:', response)
      
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
  }, [projectId, fetchWithAuth, getToken, activeProject?.title])
  
  const handleDownloadInterventionsCSV = useCallback(async () => {
    if (!projectId) return
    
    setIsPreparingInterventionsDownload(true)
    
    try {
      const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/download/interventions-csv`)
      
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
  }, [projectId, fetchWithAuth, getToken, activeProject?.title])

  // Reset flags when project changes
  useEffect(() => {
    setHasLoadedData(false)
    setAnalysisComplete(false)
    setError(null)
    setDocuments([])
    setInterventions([])
    setSummaryData(null)
    navigatorStatsProjectIdRef.current = null // Reset navigator stats ref
    summaryLoadedRef.current = null // Reset summary ref
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    hasStartedPollingRef.current = null
    setIsPolling(false)
  }, [projectId])

  // Stop polling when analysis is complete
  useEffect(() => {
    if (analysisComplete && pollingIntervalRef.current) {
      console.log('Analysis complete detected - ensuring polling is stopped')
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
      setIsPolling(false)
      hasStartedPollingRef.current = null
    }
  }, [analysisComplete])

  // Start polling when project ID is available
  useEffect(() => {
    if (!projectId) {
      console.log('No project ID, skipping polling setup')
      return
    }

    if (hasStartedPollingRef.current === projectId) {
      console.log(`Already polling project ${projectId}, skipping duplicate setup`)
      return
    }

    if (analysisComplete) {
      console.log(`Analysis already complete for project ${projectId}, skipping polling setup`)
      return
    }

    console.log(`Setting up polling for project: ${projectId}`)

    if (pollingIntervalRef.current) {
      console.log('Clearing existing polling interval')
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }

    hasStartedPollingRef.current = projectId

    const checkProjectStatus = async () => {
      try {
        console.log(`Checking status for project: ${projectId}`)
        const projectData = await getAnalysisProject(projectId)
        const project = projectData.project

        // Use project from API directly, not stale activeProject
        setActiveProject(project)

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
        } else if (project.status === 'synthesising') {
          console.log('🔄 Analysis SYNTHESISING - continuing to poll')
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
      console.log('Starting to check project status for:', projectId)
      
      console.log('Loading initial data...')
      loadData()
      
      const isComplete = await checkProjectStatus()
      
      if (isComplete) {
        console.log('Analysis already complete, no polling needed')
      } else {
        console.log('Analysis in progress, starting 20-second polling')
        setIsPolling(true)
        
        pollingIntervalRef.current = setInterval(async () => {
          if (!pollingIntervalRef.current) {
            console.log('Polling interval already cleared, skipping...')
            return
          }
          
          console.log('Polling project status and refreshing data...')
          
          await refreshData()
          
          const isComplete = await checkProjectStatus()
          if (isComplete) {
            console.log('Analysis completed! Stopping polling immediately.')
            
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current)
              pollingIntervalRef.current = null
            }
            
            setIsPolling(false)
            hasStartedPollingRef.current = null
            
            await refreshData()
          } else {
            console.log('Analysis still running, will check again in 20 seconds...')
          }
        }, 20000)
      }
    }

    startPolling()

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
        setIsPolling(false)
      }
      hasStartedPollingRef.current = null
    }
  }, [projectId, analysisComplete]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load data when navigating to a project
  useEffect(() => {
    if (projectId && !hasLoadedData && !loadingData) {
      console.log('Initial load for project:', projectId)
      loadData()
    }
  }, [projectId, hasLoadedData, loadingData, loadData])

  // Track which project/tab combination we've loaded summary for
  const summaryLoadedRef = useRef<string | null>(null)

  // Fetch summary when Summary tab is opened
  useEffect(() => {
    const fetchSummary = async () => {
      if (urlTab !== 'summary') {
        // Reset ref when not on summary tab
        summaryLoadedRef.current = null
        return
      }
      if (!projectId) return
      
      // Create a unique key for this project/tab combination
      const summaryKey = `${projectId}-${urlTab}`
      
      // Skip if we've already loaded summary for this project/tab
      if (summaryLoadedRef.current === summaryKey) return
      
      if (isLoadingSummary) return
      
      summaryLoadedRef.current = summaryKey
      setIsLoadingSummary(true)
      try {
        console.log('[ResultsPage] Fetching summary for project:', projectId)
        const data = await fetchWithAuth(`api/analysis-projects/${projectId}/summary`)
        console.log('[ResultsPage] Summary data received:', {
          hasExecutiveBriefing: !!data.executive_briefing,
          briefingLength: data.executive_briefing?.length || 0,
          issuesCount: data.key_issues?.length || 0,
          interventionsCount: data.interventions?.length || 0
        })
        setSummaryData(data as SynthesisSummary)
      } catch (err) {
        console.error('Failed to fetch summary data', err)
        setSummaryData(null)
        // Reset ref on error so we can retry
        summaryLoadedRef.current = null
      } finally {
        setIsLoadingSummary(false)
      }
    }
    fetchSummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlTab, projectId])

  // Navigator stats for summary tab
  const [navigatorStats, setNavigatorStats] = useState({
    interventionGroupCount: null as number | null,
    interventionCount: null as number | null,
    loading: true,
    error: null as string | null,
  })
  
  // Track which project we've loaded stats for to prevent re-fetching
  const navigatorStatsProjectIdRef = useRef<string | null>(null)

  useEffect(() => {
    async function fetchNavigatorStats() {
      if (!projectId) return
      
      // Skip if we've already loaded stats for this project
      if (navigatorStatsProjectIdRef.current === projectId) return
      
      navigatorStatsProjectIdRef.current = projectId
      setNavigatorStats(prev => ({ ...prev, loading: true, error: null }))
      try {
        const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/issue-intervention-navigator`)
        const interventionThemeNames = new Set<string>()
        const interventionNames = new Set<string>()
        if (response?.issue_themes) {
          response.issue_themes.forEach((issue: { related_interventions?: { theme_name?: string; detailed_interventions?: { name?: string }[] }[] }) => {
            issue.related_interventions?.forEach((intervention) => {
              if (intervention.theme_name) interventionThemeNames.add(intervention.theme_name)
              intervention.detailed_interventions?.forEach((d) => {
                if (d.name) interventionNames.add(d.name)
              })
            })
          })
        }
        setNavigatorStats({
          interventionGroupCount: interventionThemeNames.size,
          interventionCount: interventionNames.size,
          loading: false,
          error: null,
        })
      } catch (err) {
        setNavigatorStats({
          interventionGroupCount: null,
          interventionCount: null,
          loading: false,
          error: (err as Error)?.message || 'Failed to load intervention stats',
        })
        // Reset ref on error so we can retry
        navigatorStatsProjectIdRef.current = null
      }
    }
    fetchNavigatorStats()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const overtonCount = documents.filter(doc => doc.source === 'overton').length
  const openalexCount = documents.filter(doc => doc.source === 'openalex').length

  // Create study strength and sample size mappings
  const { studyStrengthMapping, sampleSizeMapping } = useMemo(() => {
    const strengthMapping: Record<string, string> = {}
    const sizeMapping: Record<string, number> = {}
    
    const getStudyTypeRank = (studyType: string): number => {
      if (!studyType) return 999
      const type = studyType.trim().toLowerCase()
      
      if (type === 'g') return 1
      if (type === 'h') return 2
      if (type === 'f') return 3
      if (type === 'e') return 4
      if (type === 'd') return 5
      if (type === 'c') return 6
      if (type === 'b') return 7
      if (type === 'a') return 8
      if (type === 'i') return 9
      if (type === 'j') return 10
      return 999
    }
    
    interventions.forEach((intervention) => {
      intervention.documents?.forEach((doc: { doc_id: string }) => {
        const docId = doc.doc_id
        if (!docId) return
        
        const studyType = intervention.highest_study_type
        if (studyType) {
          const currentRank = getStudyTypeRank(studyType)
          const existingStudyType = strengthMapping[docId]
          const existingRank = existingStudyType ? getStudyTypeRank(existingStudyType) : 999
          
          if (currentRank < existingRank) {
            strengthMapping[docId] = studyType
          }
        }
        
        const sampleSize = intervention.total_sample_size
        if (sampleSize && sampleSize > 0) {
          const existingSize = sizeMapping[docId] || 0
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

  // Calculate progress
  const progressInfo = useMemo(() => {
    if (!projectId || !activeProject) {
      return { stage: 'idle', progress: 0, text: 'No project selected' }
    }

    const status = activeProject.status
    
    if (status === 'created') {
      return { stage: 'created', progress: 0, text: 'Analysis not started' }
    }
    
    if (status === 'running') {
      if (documents.length === 0) {
        return { stage: 'retrieving', progress: 25, text: 'Retrieving and screening documents...' }
      }
      
      const relevantDocs = documents.filter(doc => doc.is_relevant !== false)
      const totalRelevantDocs = relevantDocs.length
      const extractedDocs = relevantDocs.filter(doc => 
        doc.extraction_status === 'completed' || doc.extraction_status === 'success'
      ).length
      
      if (extractedDocs === 0) {
        return { stage: 'extracting', progress: 50, text: 'Extracting intervention data from documents...' }
      }
      
      const extractionProgress = Math.round((extractedDocs / totalRelevantDocs) * 20) + 50
      return { 
        stage: 'extracting', 
        progress: Math.min(extractionProgress, 70), 
        text: `Extracting intervention data from documents... (${extractedDocs}/${totalRelevantDocs})` 
      }
    }
    
    if (status === 'synthesising') {
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
  }, [projectId, activeProject, documents])

  // Transform documents for table display
  const { transformedPapers, relevantCount } = useMemo(() => {
    const allTransformed = documents.map((doc: AnalysisDocument) => {
      const conclusion = doc.extraction_results?.conclusion
      const evidenceStrength = conclusion?.evidence_strength
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
        evidence_strength: evidenceStrength?.stars || undefined,
        evidence_strength_justification: evidenceStrength?.justification,
        impact_score: doc.impact_score,
        impact_score_label: doc.impact_score_label,
        impact_score_breakdown: doc.impact_score_breakdown,
        transferability_score: doc.transferability_score,
        transferability_breakdown: doc.transferability_breakdown,
        // Evidence categorisation fields
        evidence_category: doc.evidence_category,
        evidence_category_rank: doc.evidence_category ? getEvidenceCategoryRank(doc.evidence_category) : 999,
        evidence_confidence: doc.evidence_confidence,
        evidence_category_reasoning: doc.evidence_category_reasoning
      }
    })

    // Always filter to show only relevant documents
    const relevant = allTransformed.filter(doc => doc.is_relevant)

    return {
      transformedPapers: relevant,
      relevantCount: relevant.length
    }
  }, [documents, studyStrengthMapping, sampleSizeMapping])

  // Show loading state while fetching project
  if (projectLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
          <p className="text-slate-600">Loading project...</p>
        </div>
      </div>
    )
  }

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
            {projectId && activeProject && (
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
          {projectId && activeProject?.search_query && (
            <SearchPlanModal project={activeProject} />
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
                      Error Loading Project
                    </div>
                    <p className="text-red-700 text-sm">{error}</p>
                    <Button 
                      onClick={() => router.push('/projects')} 
                      size="sm" 
                      variant="outline" 
                      className="mt-3"
                    >
                      <ArrowLeft className="h-4 w-4 mr-2" />
                      Back to Projects
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Show empty state if no project */}
        {!projectId && !error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center p-8">
              <FileText className="h-16 w-16 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Project Selected</h3>
              <p className="text-slate-600 mb-6">
                Please select a project or start a new analysis to view results.
              </p>
              <div className="flex gap-3 justify-center">
                <Button onClick={() => router.push('/projects')} variant="outline">
                  <FileText className="h-4 w-4 mr-2" />
                  View Projects
                </Button>
                <Button onClick={() => router.push('/search')}>
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Start New Search
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Show results tabs */}
        {projectId && !error && (
          <Tabs value={urlTab} onValueChange={handleTabChange} className="h-full flex flex-col">
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
                  {/* Stat Cards Row */}
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
                      onClick={() => {
                        updateUrl('evidence', 'interventions')
                      }}
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
                          updateUrl('evidence', 'documents')
                        }}
                      />
                      <ProjectCharts projectId={projectId} projectTitle={activeProject?.title} />
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
                  {/* Evidence Sub-tabs */}
                  <div className="mb-6">
                    <div className="flex items-center justify-between">
                      <div className="flex gap-2">
                        <Button
                          variant={urlSubTab === 'interventions' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => handleSubTabChange('interventions')}
                          className="flex items-center gap-2"
                        >
                          <Target className="h-3 w-3" />
                          Interventions
                        </Button>
                        <Button
                          variant={urlSubTab === 'documents' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => handleSubTabChange('documents')}
                          className="flex items-center gap-2"
                        >
                          <FileText className="h-3 w-3" />
                          Documents ({relevantCount})
                        </Button>
                      </div>

                      {/* Filter Toggles (only show for documents) */}
                      {urlSubTab === 'documents' && (
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
                      
                      {/* Download button for interventions */}
                      {urlSubTab === 'interventions' && (
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
                      )}
                    </div>
                  </div>

                  {/* Content based on active sub-tab */}
                  {urlSubTab === 'interventions' && (
                    <div>
                      <InterventionsNavigator showHeader={true} />
                    </div>
                  )}

                  {urlSubTab === 'documents' && (
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
                      ) : documents.length > 0 ? (
                        <div className="text-center py-12">
                          <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-slate-900 mb-2">No Relevant Documents</h3>
                          <p className="text-slate-600">All {documents.length} documents in this project were marked as non-relevant.</p>
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
                <ChatInterface 
                  autoFocus={urlTab === 'assistant'}
                  placeholder="Ask about the evidence in this project..."
                  className="h-full"
                />
              </TabsContent>
            </div>
          </Tabs>
        )}
      </div>

      {/* Floating Chatbot Widget */}
      <ChatbotWidget />
    </div>
  )
}
