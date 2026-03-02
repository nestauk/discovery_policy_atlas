'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  FileText,
  Loader2,
  AlertCircle,
  BookOpen,
  Target,
} from 'lucide-react'
import {
  getPublicProject,
  getPublicProjectSummary,
  getPublicProjectDocuments,
  getPublicProjectInterventions,
  getPublicNavigator,
  PublicProject,
} from '@/lib/publicApi'
import { SynthesisSummary } from '@/types/search'
import { ExecutiveBriefing } from '../../../(main)/results/ExecutiveBriefing'
import { ProjectCharts } from '@/components/charts/ProjectCharts'
import { InterventionsNavigator } from '@/components/interventions/InterventionsNavigator'
import type { InterventionData } from '@/components/interventions/InterventionsTable'
import { PapersTable } from '@/components/documents/PapersTable'
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
}

type TabType = 'summary' | 'evidence'
type EvidenceSubTabType = 'interventions' | 'documents'

export default function PublicProjectPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const router = useRouter()
  const { isSignedIn, isLoaded, getToken } = useAuth()

  const projectId = params.projectId as string
  const [accessChecked, setAccessChecked] = useState(false)

  useEffect(() => {
    if (!isLoaded || !projectId) return

    if (!isSignedIn) {
      setAccessChecked(true)
      return
    }

    const checkAccessAndRedirect = async () => {
      try {
        const token = await getToken()
        if (!token) {
          setAccessChecked(true)
          return
        }
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        const cleanBaseUrl = baseUrl.replace(/\/$/, '')
        const res = await fetch(
          `${cleanBaseUrl}/api/analysis-projects/${projectId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        if (res.ok) {
          router.replace(`/projects/${projectId}`)
        } else {
          setAccessChecked(true)
        }
      } catch {
        setAccessChecked(true)
      }
    }

    checkAccessAndRedirect()
  }, [isLoaded, isSignedIn, projectId, router, getToken])
  
  const tabParam = searchParams.get('tab')
  const validTabs: TabType[] = ['summary', 'evidence']
  const urlTab: TabType = validTabs.includes(tabParam as TabType) ? (tabParam as TabType) : 'summary'
  
  const subtabParam = searchParams.get('subtab')
  const validSubTabs: EvidenceSubTabType[] = ['interventions', 'documents']
  const urlSubTab: EvidenceSubTabType = validSubTabs.includes(subtabParam as EvidenceSubTabType) 
    ? (subtabParam as EvidenceSubTabType) 
    : 'interventions'

  const [project, setProject] = useState<PublicProject | null>(null)
  const [projectLoading, setProjectLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [summaryData, setSummaryData] = useState<SynthesisSummary | null>(null)
  const [isLoadingSummary, setIsLoadingSummary] = useState(false)
  
  const [documents, setDocuments] = useState<AnalysisDocument[]>([])
  const [interventions, setInterventions] = useState<InterventionData[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)
  
  const [showAdditionalColumns, setShowAdditionalColumns] = useState(false)

  const [navigatorStats, setNavigatorStats] = useState({
    interventionGroupCount: null as number | null,
    interventionCount: null as number | null,
    loading: true,
    error: null as string | null,
  })

  const updateUrl = useCallback((tab: TabType, subtab?: EvidenceSubTabType) => {
    const params = new URLSearchParams()
    if (tab !== 'summary') {
      params.set('tab', tab)
    }
    if (tab === 'evidence' && subtab && subtab !== 'interventions') {
      params.set('subtab', subtab)
    }
    const queryString = params.toString()
    const newUrl = `/public/projects/${projectId}${queryString ? `?${queryString}` : ''}`
    router.replace(newUrl, { scroll: false })
  }, [projectId, router])

  const handleTabChange = useCallback((tab: string) => {
    const newTab = tab as TabType
    const subtab = newTab === 'evidence' && urlTab !== 'evidence' ? 'interventions' : urlSubTab
    updateUrl(newTab, subtab)
  }, [updateUrl, urlSubTab, urlTab])

  const handleSubTabChange = useCallback((subtab: EvidenceSubTabType) => {
    updateUrl('evidence', subtab)
  }, [updateUrl])

  // Load project
  useEffect(() => {
    const loadProject = async () => {
      if (!projectId) {
        setError('No project ID provided')
        setProjectLoading(false)
        return
      }
      
      setProjectLoading(true)
      setError(null)
      try {
        const data = await getPublicProject(projectId)
        if (data?.project) {
          setProject(data.project)
        } else {
          setError('Project not found')
        }
      } catch (err) {
        console.error('Failed to load public project:', err)
        const errorMessage = err instanceof Error ? err.message : 'Failed to load project'
        setError(errorMessage)
      } finally {
        setProjectLoading(false)
      }
    }
    
    loadProject()
  }, [projectId])

  // Load documents and interventions
  useEffect(() => {
    const loadData = async () => {
      if (!projectId || !project) return
      
      setLoadingData(true)
      setDataError(null)
      
      try {
        const [docsResponse, interventionsResponse] = await Promise.all([
          getPublicProjectDocuments(projectId),
          getPublicProjectInterventions(projectId).catch(() => ({ interventions: [] }))
        ])
        
        setDocuments((docsResponse as { documents: AnalysisDocument[] }).documents || [])
        setInterventions((interventionsResponse as { interventions: InterventionData[] }).interventions || [])
      } catch (err) {
        console.error('Failed to load public project data:', err)
        setDataError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        setLoadingData(false)
      }
    }
    
    loadData()
  }, [projectId, project])

  // Load summary when on summary tab
  useEffect(() => {
    const fetchSummary = async () => {
      if (urlTab !== 'summary' || !projectId || !project) return
      if (summaryData) return
      
      setIsLoadingSummary(true)
      try {
        const data = await getPublicProjectSummary(projectId)
        setSummaryData(data as SynthesisSummary)
      } catch (err) {
        console.error('Failed to fetch public summary data', err)
        setSummaryData(null)
      } finally {
        setIsLoadingSummary(false)
      }
    }
    fetchSummary()
  }, [urlTab, projectId, project, summaryData])

  // Load navigator stats
  useEffect(() => {
    async function fetchNavigatorStats() {
      if (!projectId || !project) return
      
      setNavigatorStats(prev => ({ ...prev, loading: true, error: null }))
      try {
        const response = await getPublicNavigator(projectId) as {
          issue_themes?: {
            related_interventions?: {
              theme_name?: string
              detailed_interventions?: { name?: string }[]
            }[]
          }[]
        }
        const interventionThemeNames = new Set<string>()
        const interventionNames = new Set<string>()
        if (response?.issue_themes) {
          response.issue_themes.forEach((issue) => {
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
      }
    }
    fetchNavigatorStats()
  }, [projectId, project])

  const overtonCount = documents.filter(doc => doc.source === 'overton').length
  const openalexCount = documents.filter(doc => doc.source === 'openalex').length

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

  const { transformedPapers, relevantCount } = useMemo(() => {
    const allTransformed = documents.map((doc: AnalysisDocument) => {
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
        evidence_strength: doc.evidence_strength ?? undefined,
        evidence_strength_justification: doc.evidence_strength_justification,
        impact_score: doc.impact_score,
        impact_score_label: doc.impact_score_label,
        impact_score_breakdown: doc.impact_score_breakdown,
        transferability_score: doc.transferability_score,
        transferability_breakdown: doc.transferability_breakdown,
        evidence_category: doc.evidence_category,
        evidence_category_rank: doc.evidence_category ? getEvidenceCategoryRank(doc.evidence_category) : 999,
        evidence_confidence: doc.evidence_confidence,
        evidence_category_reasoning: doc.evidence_category_reasoning
      }
    })

    const relevant = allTransformed.filter(doc => doc.is_relevant)

    return {
      transformedPapers: relevant,
      relevantCount: relevant.length
    }
  }, [documents, studyStrengthMapping, sampleSizeMapping])

  // Show loading while checking auth or access
  if (!isLoaded || !accessChecked) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
          <p className="text-slate-600">Loading...</p>
        </div>
      </div>
    )
  }

  if (projectLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
          <p className="text-slate-600">Loading project...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Project Title */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-2xl font-bold text-slate-900">{project?.title || 'Public Project'}</h1>
          {project?.query && (
            <p className="mt-2 text-slate-600">{project.query}</p>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1">
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
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {projectId && !error && project && (
          <Tabs value={urlTab} onValueChange={handleTabChange} className="h-full flex flex-col">
            <div className="px-6 pt-4 max-w-6xl mx-auto w-full">
              <TabsList className="!grid w-full grid-cols-2">
                <TabsTrigger value="summary" className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Summary
                </TabsTrigger>
                <TabsTrigger value="evidence" className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  Evidence
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
                        projectId={projectId}
                        briefing={summaryData.executive_briefing}
                        structuredBriefing={summaryData.structured_briefing}
                        citationMap={summaryData.citation_map}
                        evidenceCoverage={summaryData.evidence_coverage}
                        onCitationClick={() => {
                          updateUrl('evidence', 'documents')
                        }}
                      />
                      <ProjectCharts projectId={projectId} projectTitle={project?.title} isPublic={true} />
                    </div>
                  )}
                  {!isLoadingSummary && !summaryData && (
                    <div className="text-center py-12">
                      <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-slate-900 mb-2">No Summary Available</h3>
                      <p className="text-slate-600">Summary data is not available for this project.</p>
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

                      {urlSubTab === 'documents' && (
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
                      )}
                    </div>
                  </div>

                  {urlSubTab === 'interventions' && (
                    <div>
                      <InterventionsNavigator showHeader={true} isPublic={true} publicProjectId={projectId} />
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
                          <p className="text-slate-600">All documents in this project were marked as non-relevant.</p>
                        </div>
                      ) : (
                        <div className="text-center py-12">
                          <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-slate-900 mb-2">No Documents Available</h3>
                          <p className="text-slate-600">Documents are not available for this project.</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </TabsContent>
            </div>
          </Tabs>
        )}
      </div>
    </div>
  )
}
