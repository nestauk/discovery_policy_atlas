'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
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
  Download,
  Share2,
  Copy,
  Check,
  Globe,
  Lock,
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { useProjectDataCache } from '@/lib/projectDataCache'
import { useAuth, useUser } from '@clerk/nextjs'
import { SynthesisSummary } from '@/types/search'
import { ExecutiveBriefing } from '../../results/ExecutiveBriefing'
import { ChatInterface } from '@/components/chatbot/ChatInterface'
import { ChatbotWidget } from '@/components/chatbot/ChatbotWidget'
import { ProjectCharts } from '@/components/charts/ProjectCharts'
import { InterventionsNavigator } from '@/components/interventions/InterventionsNavigator'
import type { InterventionData } from '@/components/interventions/InterventionsTable'
import { PapersTable } from '@/components/documents/PapersTable'
import { SearchPlanModal } from '@/components/results/SearchPlanModal'
import { ResultsTutorial } from '@/components/results/ResultsTutorial'
import { getEvidenceCategoryRank } from '@/lib/evidenceCategories'

interface AnalysisDocument {
  id: string
  doc_id: string
  title: string
  source: string
  authors?: string[]
  author_institutions?: string[]
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
  // New fields for filtering
  is_evidence?: boolean
  is_relevant_evidence?: boolean
}

type TabType = 'summary' | 'evidence' | 'assistant'
type EvidenceSubTabType = 'interventions' | 'documents'

function estimateDurationRangeMinutes(maxResults: number, sourceCount: number): { min: number; max: number } {
  const effectiveSources = Math.max(1, sourceCount)
  const totalDocs = maxResults * effectiveSources
  const baseMinutes = 2 + 18 + (totalDocs * 15) / 60
  const min = Math.max(10, Math.round((baseMinutes * 0.7) / 5) * 5)
  const max = Math.max(min + 5, Math.round((baseMinutes * 1.3) / 5) * 5)
  return { min, max }
}

function estimateRemainingRangeMinutes(baseMinutes: number): { min: number; max: number } {
  const min = Math.max(5, Math.round((baseMinutes * 0.7) / 5) * 5)
  const max = Math.max(min + 5, Math.round((baseMinutes * 1.3) / 5) * 5)
  return { min, max }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

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
  
  // Documents filter state - only show relevant evidence documents by default
  const [showOnlyRelevant, setShowOnlyRelevant] = useState(true)
  
  // Documents download state
  const [isPreparingDocumentsDownload, setIsPreparingDocumentsDownload] = useState(false)
  
  // Interventions view state
  const [isPreparingInterventionsDownload, setIsPreparingInterventionsDownload] = useState(false)
  
  // Share dialog state
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [isTogglingVisibility, setIsTogglingVisibility] = useState(false)
  const [copied, setCopied] = useState(false)
  
  // Data states
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [interventions, setInterventions] = useState<InterventionData[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)
  const [isRerunningSynthesis, setIsRerunningSynthesis] = useState(false)
  const [rerunError, setRerunError] = useState<string | null>(null)

  const [projectLoading, setProjectLoading] = useState(false)
  const [parentProjectTitle, setParentProjectTitle] = useState<string | null>(null)
  const [currentMinuteTick, setCurrentMinuteTick] = useState<number>(Date.now())

  const { activeProject, setActiveProject, projects, setProjects } = useAnalysisProjectStore()
  const { fetchWithAuth, getAnalysisProject, getProjectInterventions, rerunSynthesisForProject } = useAPI()
  const { getToken } = useAuth()
  const { user } = useUser()
  
  const isProjectOwner = useMemo(() => {
    if (!user || !activeProject) return false
    const currentUserId = user.id
    const currentUserFullName = user.fullName || ''
    const currentUserEmail = user.emailAddresses?.[0]?.emailAddress || ''
    const currentUserEmailUsername = currentUserEmail.split('@')[0] || ''
    
    return (
      activeProject.created_by_user_id === currentUserId ||
      activeProject.created_by_name === currentUserFullName ||
      activeProject.created_by_name === currentUserEmail ||
      activeProject.created_by_name === currentUserEmailUsername
    )
  }, [user, activeProject])

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

  // Load project from API if not in store or different project.
  // Running projects are handled by the polling effect below.
  useEffect(() => {
    const loadProjectIfNeeded = async () => {
      if (!projectId) {
        setError('No project ID provided')
        return
      }

      // verifyAndPoll handles the fetch for running projects
      const storeStatus = activeProject?.id === projectId ? activeProject.status : null
      if (storeStatus === 'running' || storeStatus === 'synthesising') return

      // If we already have this project in store with full payload, no need to fetch.
      // The projects list endpoint omits search_query, so we must refetch when that field is missing.
      const hasSearchQueryField =
        !!activeProject &&
        Object.prototype.hasOwnProperty.call(activeProject, 'search_query')
      if (activeProject?.id === projectId && hasSearchQueryField) return
      
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

  // Fetch parent project title for "Refined from" indicator
  useEffect(() => {
    const parentId = activeProject?.parent_project_id
    if (!parentId) {
      setParentProjectTitle(null)
      return
    }
    // Check local store first to avoid an API call
    const cached = projects.find(p => p.id === parentId)
    if (cached) {
      setParentProjectTitle(cached.title)
      return
    }
    getAnalysisProject(parentId)
      .then((data: { project?: { title?: string } }) => {
        setParentProjectTitle(data?.project?.title || null)
      })
      .catch(() => {
        setParentProjectTitle(null)
      })
  }, [activeProject?.parent_project_id, projects, getAnalysisProject])

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

  const { getCached, setCache: setProjectCache, invalidateProject: invalidateProjectCache } = useProjectDataCache()

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

      invalidateProjectCache(activeProject.id)
      summaryLoadedRef.current = null
      setSummaryData(null)

      const updated = { ...activeProject, status: 'running' as const }
      setActiveProject(updated)
      setProjects(projects.map((p) => (p.id === updated.id ? { ...p, status: updated.status } : p)))
    } catch (error) {
      console.error('Failed to rerun synthesis', error)
      setRerunError('Failed to start synthesis rerun')
    } finally {
      setIsRerunningSynthesis(false)
    }
  }, [activeProject, isRerunningSynthesis, rerunSynthesisForProject, setActiveProject, setProjects, projects, invalidateProjectCache])

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

  // Always verify status from the API before polling — stale localStorage
  // (e.g. "failed" from a dropped HTTP connection) must not block polling.
  useEffect(() => {
    if (!projectId) return
    if (hasStartedPollingRef.current === projectId) return
    if (analysisComplete) return

    // Fetch project status and handle terminal states
    const fetchAndCheckStatus = async () => {
      const projectData = await getAnalysisProject(projectId)
      const project = projectData.project
      setActiveProject(project)

      const isStable = project.status === 'completed' || project.status === 'failed' || project.status === 'created'
      if (isStable) {
        setAnalysisComplete(project.status === 'completed' || project.status === 'created')
        if (project.status === 'failed') {
          setError('Analysis failed. Please try again.')
        }
      }
      return { project, isStable }
    }

    const startPolling = () => {
      hasStartedPollingRef.current = projectId

      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }

      setIsPolling(true)
      pollingIntervalRef.current = setInterval(async () => {
        if (!pollingIntervalRef.current) return

        await refreshData()

        try {
          const { isStable: done } = await fetchAndCheckStatus()
          if (done) {
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current)
              pollingIntervalRef.current = null
            }
            setIsPolling(false)
            hasStartedPollingRef.current = null
            await refreshData()
          }
        } catch (error) {
          console.error('Failed to poll project status:', error)
        }
      }, 20000)
    }

    const verifyAndPoll = async () => {
      try {
        const { isStable } = await fetchAndCheckStatus()

        if (isStable) return

        // Prevent duplicate polling if another effect started during the await
        if (hasStartedPollingRef.current === projectId) return

        startPolling()
      } catch (error) {
        console.error('Failed to verify project status:', error)
        // Fallback to store status if API is unreachable
        const storeStatus = activeProject?.id === projectId ? activeProject.status : null
        if (storeStatus === 'running' || storeStatus === 'synthesising') {
          startPolling()
        }
      }
    }

    verifyAndPoll()

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
        setIsPolling(false)
      }
      hasStartedPollingRef.current = null
    }
    // Deps intentionally limited to projectId — other values are refs or stable setters
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load data when navigating to a project
  useEffect(() => {
    if (projectId && !hasLoadedData && !loadingData) {
      console.log('Initial load for project:', projectId)
      loadData()
    }
  }, [projectId, hasLoadedData, loadingData, loadData])

  // Track which project we've loaded summary for
  const summaryLoadedRef = useRef<string | null>(null)

  // Fetch summary when Summary tab is opened
  useEffect(() => {
    const fetchSummary = async () => {
      if (urlTab !== 'summary') return
      if (!projectId) return

      // Skip if already loaded for this project
      if (summaryLoadedRef.current === projectId) return
      if (isLoadingSummary) return

      // Check in-memory cache first
      const cached = getCached('summary', projectId) as SynthesisSummary | undefined
      if (cached) {
        setSummaryData(cached)
        summaryLoadedRef.current = projectId
        return
      }

      summaryLoadedRef.current = projectId
      setIsLoadingSummary(true)
      try {
        const data = await fetchWithAuth(`api/analysis-projects/${projectId}/summary`)
        setSummaryData(data as SynthesisSummary)
        setProjectCache('summary', projectId, data)
      } catch (err) {
        console.error('Failed to fetch summary data', err)
        setSummaryData(null)
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
        const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/navigator-stats`)
        setNavigatorStats({
          interventionGroupCount: response.intervention_group_count ?? null,
          interventionCount: response.intervention_count ?? null,
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

  // Filter to relevant evidence documents for stats
  const relevantEvidenceDocs = documents.filter(doc => doc.is_relevant_evidence !== false && doc.is_relevant !== false && doc.is_evidence !== false)
  const overtonCount = relevantEvidenceDocs.filter(doc => doc.source === 'overton').length
  const openalexCount = relevantEvidenceDocs.filter(doc => doc.source === 'openalex').length

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

  const elapsedMinutes = useMemo(() => {
    if (!activeProject?.created_at) return null
    const createdAtMs = new Date(activeProject.created_at).getTime()
    if (Number.isNaN(createdAtMs)) return null
    return Math.max(0, Math.floor((currentMinuteTick - createdAtMs) / 60000))
  }, [activeProject?.created_at, currentMinuteTick])

  useEffect(() => {
    if (activeProject?.status !== 'running' && activeProject?.status !== 'synthesising') return
    setCurrentMinuteTick(Date.now())
    const interval = setInterval(() => setCurrentMinuteTick(Date.now()), 60000)
    return () => clearInterval(interval)
  }, [activeProject?.status])

  // Calculate progress
  const progressInfo = useMemo(() => {
    if (!projectId || !activeProject) {
      return {
        stage: 'idle',
        progress: 0,
        text: 'No project selected',
        stageDescription: '',
        remainingRange: null as { min: number; max: number } | null,
      }
    }

    const status = activeProject.status
    const backendProgress = activeProject.progress
    const configuredMaxResults = activeProject.search_query?.max_results ?? activeProject.search_query?.limit ?? 30
    const configuredSourcesCount = activeProject.search_query?.sources?.length ?? 2
    const configuredDocs = Math.max(1, configuredMaxResults * Math.max(1, configuredSourcesCount))
    const defaultRelevantRatio = 0.6
    const observedRelevantDocs = documents.filter((doc) => doc.is_relevant !== false).length
    const estimatedRelevantDocs = Math.max(
      1,
      observedRelevantDocs > 0 ? observedRelevantDocs : Math.round(configuredDocs * defaultRelevantRatio),
    )
    const overheadMinutes = 2
    const extractionMinutes = estimatedRelevantDocs * (15 / 60)
    const synthesisMinutes = 18
    const estimatedTotalMinutes = overheadMinutes + extractionMinutes + synthesisMinutes
    const retrievalEndProgress = clamp(Math.round((overheadMinutes / estimatedTotalMinutes) * 100), 10, 30)
    const extractionEndProgress = clamp(
      Math.round(((overheadMinutes + extractionMinutes) / estimatedTotalMinutes) * 100),
      retrievalEndProgress + 25,
      88,
    )
    const estimatedTotalRange = estimateDurationRangeMinutes(configuredMaxResults, configuredSourcesCount)
    
    if (status === 'created') {
      return {
        stage: 'created',
        progress: 0,
        text: 'Analysis not started',
        stageDescription: 'Your project is created and ready to run.',
        remainingRange: null,
      }
    }
    
    if (status === 'running') {
      if (documents.length === 0) {
        const retrievalProgressFromElapsed =
          elapsedMinutes !== null
            ? Math.round(retrievalEndProgress * clamp(elapsedMinutes / overheadMinutes, 0, 1))
            : retrievalEndProgress
        return {
          stage: 'retrieving',
          progress: Math.max(5, retrievalProgressFromElapsed),
          text: 'Retrieving and screening documents...',
          stageDescription: 'Searching academic databases and policy repositories for relevant documents.',
          remainingRange: estimatedTotalRange,
        }
      }
      
      const relevantDocs = documents.filter(doc => doc.is_relevant !== false)
      const totalRelevantDocs = relevantDocs.length
      const extractedDocs = relevantDocs.filter(doc => 
        doc.extraction_status === 'completed' || doc.extraction_status === 'success'
      ).length
      
      if (extractedDocs === 0) {
        return {
          stage: 'extracting',
          progress: retrievalEndProgress,
          text: 'Extracting intervention data from documents...',
          stageDescription: 'Reading documents and extracting intervention details with AI. This is usually the longest stage.',
          remainingRange: estimateRemainingRangeMinutes(18 + (totalRelevantDocs * 15) / 60),
        }
      }
      
      const extractionFraction = totalRelevantDocs > 0 ? extractedDocs / totalRelevantDocs : 0
      const extractionProgress =
        retrievalEndProgress +
        Math.round((extractionEndProgress - retrievalEndProgress) * clamp(extractionFraction, 0, 1))
      const remainingDocs = Math.max(totalRelevantDocs - extractedDocs, 0)
      return { 
        stage: 'extracting', 
        progress: Math.min(extractionProgress, extractionEndProgress), 
        text: `Extracting intervention data from documents... (${extractedDocs}/${totalRelevantDocs})`,
        stageDescription: 'Reading documents and extracting intervention details with AI. This is usually the longest stage.',
        remainingRange: estimateRemainingRangeMinutes(18 + (remainingDocs * 15) / 60),
      }
    }
    
    if (status === 'synthesising') {
      if (backendProgress) {
        const stepText =
          backendProgress.step_total > 0
            ? ` (${backendProgress.step_index}/${backendProgress.step_total})`
            : ''
        return {
          stage: 'synthesising',
          progress: clamp(backendProgress.percent, extractionEndProgress, 95),
          text: `${backendProgress.stage_label}${stepText}`,
          stageDescription: backendProgress.stage_description,
          remainingRange: estimateRemainingRangeMinutes(18),
        }
      }

      const synthElapsedMinutes =
        elapsedMinutes !== null ? Math.max(0, elapsedMinutes - (overheadMinutes + extractionMinutes)) : 0
      const synthProgressFraction =
        synthesisMinutes > 0 ? clamp(synthElapsedMinutes / synthesisMinutes, 0, 0.95) : 0.6
      const synthesisProgress =
        extractionEndProgress +
        Math.round((95 - extractionEndProgress) * synthProgressFraction)
      return { 
        stage: 'synthesising', 
        progress: Math.max(extractionEndProgress, synthesisProgress), 
        text: 'Generating summary and insights...',
        stageDescription: 'Combining findings into themes and generating your executive briefing.',
        remainingRange: estimateRemainingRangeMinutes(18),
      }
    }
    
    if (status === 'completed') {
      return {
        stage: 'completed',
        progress: 100,
        text: 'Analysis completed',
        stageDescription: 'Your results are ready to explore.',
        remainingRange: null,
      }
    }
    
    if (status === 'failed') {
      return {
        stage: 'failed',
        progress: 0,
        text: 'Analysis failed',
        stageDescription: 'Something went wrong while processing this analysis.',
        remainingRange: null,
      }
    }
    
    return {
      stage: 'unknown',
      progress: 0,
      text: 'Unknown status',
      stageDescription: '',
      remainingRange: null,
    }
  }, [projectId, activeProject, documents, elapsedMinutes])

  // Transform documents for table display
  const { transformedPapers, relevantCount } = useMemo(() => {
    const allTransformed = documents.map((doc: AnalysisDocument) => {
      const isRelevant = Boolean(doc.is_relevant !== false)
      const isEvidence = Boolean(doc.is_evidence !== false)
      const isRelevantEvidence = isRelevant && isEvidence
      
      return {
        id: String(doc.id || doc.doc_id || `doc-${Math.random()}`),
        title: String(doc.title || 'Untitled'),
        doi: String(doc.doi || ''),
        publication_year: Number(doc.year || 0),
        cited_by_count: Number(doc.cited_by_count || 0),
        authors: Array.isArray(doc.authors) ? doc.authors : ['Unknown'],
        author_institutions: Array.isArray(doc.author_institutions)
          ? doc.author_institutions
          : [],
        is_relevant: isRelevant,
        is_evidence: isEvidence,
        is_relevant_evidence: isRelevantEvidence,
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
        evidence_strength: doc.evidence_strength ?? undefined,
        evidence_strength_justification: doc.evidence_strength_justification,
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

    // Count relevant evidence documents
    const relevantEvidenceCount = allTransformed.filter(doc => doc.is_relevant_evidence).length

    return {
      transformedPapers: allTransformed,
      relevantCount: relevantEvidenceCount
    }
  }, [documents, studyStrengthMapping, sampleSizeMapping])

  const publicUrl = typeof window !== 'undefined' 
    ? `${window.location.origin}/public/projects/${projectId}` 
    : `/public/projects/${projectId}`

  const handleToggleVisibility = useCallback(async () => {
    if (!projectId || isTogglingVisibility) return
    
    setIsTogglingVisibility(true)
    try {
      const newIsPublic = !activeProject?.is_public
      await fetchWithAuth(`/api/analysis-projects/${projectId}/visibility`, {
        method: 'PATCH',
        body: JSON.stringify({ is_public: newIsPublic }),
      })
      setActiveProject({
        ...activeProject!,
        is_public: newIsPublic,
      })
    } catch (err) {
      console.error('Failed to toggle visibility:', err)
    } finally {
      setIsTogglingVisibility(false)
    }
  }, [projectId, activeProject, isTogglingVisibility, fetchWithAuth, setActiveProject])

  const handleCopyLink = useCallback(() => {
    navigator.clipboard.writeText(publicUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [publicUrl])

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
    <div className="flex-1 flex flex-col bg-slate-50">
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
            {/* Refined from indicator */}
            {activeProject?.parent_project_id && parentProjectTitle && (
              <p className="text-sm text-slate-500 mt-1">
                Refined from:{' '}
                <Link
                  href={`/projects/${activeProject.parent_project_id}`}
                  className="text-blue-600 hover:text-blue-800 hover:underline"
                >
                  {parentProjectTitle}
                </Link>
              </p>
            )}
            {/* Progress Indicator */}
            {projectId && activeProject && (
              <div data-tutorial="progress-bar" className="mt-2 mb-3 space-y-2">
                <div className="flex items-center gap-3">
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
                  <span className="text-sm text-slate-600">{progressInfo.text}</span>
                </div>
                {progressInfo.stageDescription && (
                  <p className="text-xs text-slate-500">{progressInfo.stageDescription}</p>
                )}
                {(activeProject.status === 'running' || activeProject.status === 'synthesising') && (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                    {elapsedMinutes !== null && (
                      <span>Running for {elapsedMinutes} minute{elapsedMinutes === 1 ? '' : 's'}</span>
                    )}
                    {progressInfo.remainingRange && (
                      <span>
                        Estimated remaining: ~{progressInfo.remainingRange.min}-{progressInfo.remainingRange.max} minutes
                      </span>
                    )}
                  </div>
                )}
                {(activeProject.status === 'running' || activeProject.status === 'synthesising') && (
                  <p className="text-xs text-slate-500">
                    You can safely close this tab. Your analysis will continue running and results will be ready when you return.
                  </p>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* Share Button - only visible to project owner */}
            {projectId && activeProject && isProjectOwner && (
              <Dialog open={shareDialogOpen} onOpenChange={setShareDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="flex items-center gap-2">
                    <Share2 className="h-4 w-4" />
                    Share
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-md">
                  <DialogHeader>
                    <DialogTitle>Share Project</DialogTitle>
                    <DialogDescription>
                      Make this project publicly accessible via a shareable link.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 pt-4">
                    {/* Visibility Toggle */}
                    <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        {activeProject.is_public ? (
                          <Globe className="h-5 w-5 text-green-600" />
                        ) : (
                          <Lock className="h-5 w-5 text-slate-500" />
                        )}
                        <div>
                          <div className="font-medium text-sm">
                            {activeProject.is_public ? 'Public' : 'Private'}
                          </div>
                          <div className="text-xs text-slate-500">
                            {activeProject.is_public 
                              ? 'Anyone with the link can view' 
                              : 'Only you can access this project'}
                          </div>
                        </div>
                      </div>
                      <Switch
                        checked={activeProject.is_public || false}
                        onCheckedChange={handleToggleVisibility}
                        disabled={isTogglingVisibility}
                      />
                    </div>
                    
                    {/* Share Link */}
                    {activeProject.is_public && (
                      <div className="space-y-2">
                        <Label className="text-sm font-medium">Public Link</Label>
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={publicUrl}
                            readOnly
                            className="flex-1 px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-md"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleCopyLink}
                            className="flex items-center gap-2"
                          >
                            {copied ? (
                              <>
                                <Check className="h-4 w-4 text-green-600" />
                                Copied
                              </>
                            ) : (
                              <>
                                <Copy className="h-4 w-4" />
                                Copy
                              </>
                            )}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </DialogContent>
              </Dialog>
            )}
            {/* Search Plan Settings Button */}
            {projectId && activeProject?.search_query && (
              <SearchPlanModal project={activeProject} />
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1">

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
          <div className="flex items-center justify-center min-h-[200px] py-12">
            <div className="text-center p-8">
              <FileText className="h-16 w-16 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Project Selected</h3>
              <p className="text-slate-600 mb-3">
                Projects store your full search output: summary insights, interventions, and source documents.
              </p>
              <p className="text-slate-600 mb-6">
                Select an existing project or start a new search to create one.
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
          <Tabs value={urlTab} onValueChange={handleTabChange} className="flex flex-col">
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

            <div>
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
                        projectId={projectId}
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
                      <p className="text-slate-600">
                        {activeProject?.status === 'running' || activeProject?.status === 'synthesising'
                          ? 'Your summary is still being generated. This usually appears once extraction and synthesis finish.'
                          : 'No summary could be generated for this project. Try refining your search parameters and running again.'}
                      </p>
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
                          data-tutorial="documents-subtab"
                        >
                          <FileText className="h-3 w-3" />
                          Documents ({showOnlyRelevant ? relevantCount : `${relevantCount}+${transformedPapers.length - relevantCount}`})
                        </Button>
                      </div>

                      {/* Filter Toggles (only show for documents) */}
                      {urlSubTab === 'documents' && (
                        <div className="flex items-center gap-6">
                          <div className="flex items-center gap-2">
                            <Switch
                              id="only-relevant"
                              checked={showOnlyRelevant}
                              onCheckedChange={setShowOnlyRelevant}
                            />
                            <Label htmlFor="only-relevant" className="text-sm text-slate-700">
                              Only relevant
                            </Label>
                          </div>
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
                    <div data-tutorial="documents-table">
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
                        <PapersTable 
                          papers={showOnlyRelevant 
                            ? transformedPapers.filter(p => p.is_relevant_evidence) 
                            : transformedPapers
                          } 
                          showAdditionalColumns={showAdditionalColumns}
                          highlightNonRelevant={!showOnlyRelevant}
                        />
                      ) : documents.length > 0 ? (
                        <div className="text-center py-12">
                          <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-slate-900 mb-2">No Relevant Documents</h3>
                          <p className="text-slate-600">
                            All {documents.length} documents were marked non-relevant. Try broadening your question, geography, or time window.
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-12">
                          <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-slate-900 mb-2">No Documents Available</h3>
                          <p className="text-slate-600">
                            {activeProject?.status === 'running' || activeProject?.status === 'synthesising'
                              ? 'Documents are being retrieved and screened. Check back shortly.'
                              : 'No documents matched this search. Try broadening your search terms or filters.'}
                          </p>
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

      <ResultsTutorial
        enabled={Boolean(projectId && activeProject?.status === 'completed')}
        onShowSummary={() => updateUrl('summary')}
        onShowEvidenceInterventions={() => updateUrl('evidence', 'interventions')}
        onShowEvidenceDocuments={() => updateUrl('evidence', 'documents')}
      />

      {/* Floating Chatbot Widget */}
      <ChatbotWidget />
    </div>
  )
}
