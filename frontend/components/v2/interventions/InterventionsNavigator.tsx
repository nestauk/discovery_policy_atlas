'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { useAuth } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Loader2, ChevronRight, ChevronDown, Target, AlertTriangle, Star, Download } from 'lucide-react'
import { NavigatorInterventionsTable } from '@/components/v2/interventions/NavigatorInterventionsTable'

interface IssueTheme {
  theme_name: string
  description: string
  frequency: number
  related_interventions: InterventionTheme[]
}

interface InterventionTheme {
  theme_name: string
  description: string
  impact_summary?: string
  frequency: number
  avg_impact_score?: number
  avg_evidence_score?: number
  detailed_interventions?: DetailedIntervention[]
}

interface DetailedIntervention {
  name: string
  description: string
  type?: string
  country?: string
  study_type?: string
  sample_size?: number | null
  impact_score?: number
  evidence_score?: number
  impact_justification?: string
  evidence_justification?: string
  document_url?: string
  results: Array<{
    outcome_variable?: string
    effect_direction?: string
    effect_size?: string
    p_value?: string
    uncertainty?: string
    result_text?: string
    population_measured?: string
    subgroup_or_dose?: string
  }>
  source_documents: Array<{
    doc_id?: string
    title?: string
    source?: string
    landing_page_url?: string
  }>
}

interface NavigatorData {
  issue_themes: IssueTheme[]
}

interface InterventionsNavigatorProps {
  showHeader?: boolean
  viewMode?: 'grouped' | 'all'
  onViewModeChange?: (mode: 'grouped' | 'all') => void
  sortBy?: 'frequency' | 'impact' | 'evidence'
  onSortByChange?: (sortBy: 'frequency' | 'impact' | 'evidence') => void
  onDownload?: () => void
  isPreparingDownload?: boolean
}

export function InterventionsNavigator({ 
  showHeader = true,
  viewMode: externalViewMode,
  onViewModeChange,
  sortBy: externalSortBy,
  onSortByChange,
  onDownload,
  isPreparingDownload: externalIsPreparingDownload
}: InterventionsNavigatorProps) {
  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth } = useAPI()
  const { getToken } = useAuth()
  
  const [data, setData] = useState<NavigatorData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set())
  const [expandedInterventions, setExpandedInterventions] = useState<Set<string>>(new Set())
  
  // Use external state if provided, otherwise use internal state
  const [internalViewMode, setInternalViewMode] = useState<'grouped' | 'all'>('all')
  const [internalSortBy, setInternalSortBy] = useState<'frequency' | 'impact' | 'evidence'>('impact')
  const [internalIsPreparingDownload, setInternalIsPreparingDownload] = useState(false)
  
  const viewMode = externalViewMode ?? internalViewMode
  const setViewMode = onViewModeChange ?? setInternalViewMode
  const sortBy = externalSortBy ?? internalSortBy
  const setSortBy = onSortByChange ?? setInternalSortBy
  const isPreparingDownload = externalIsPreparingDownload ?? internalIsPreparingDownload

  const loadNavigatorData = useCallback(async () => {
    if (!activeProject?.id) return
    
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetchWithAuth(`/api/analysis-projects/${activeProject.id}/issue-intervention-navigator`)
      console.log('Navigator API response:', response)
      console.log('Number of issue themes:', response?.issue_themes?.length || 0)
      if (response?.issue_themes?.length > 0) {
        console.log('First issue theme:', response.issue_themes[0])
        console.log('First intervention (if any):', response.issue_themes[0]?.related_interventions?.[0])
      }
      setData(response as NavigatorData)
    } catch (err) {
      console.error('Failed to load navigator data:', err)
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [activeProject?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!activeProject?.id) return
    loadNavigatorData()
  }, [activeProject?.id, loadNavigatorData])

  const toggleIssue = useCallback((themeName: string) => {
    setExpandedIssues(prev => {
      const newExpanded = new Set(prev)
      if (newExpanded.has(themeName)) {
        newExpanded.delete(themeName)
      } else {
        newExpanded.add(themeName)
      }
      return newExpanded
    })
  }, [])

  const toggleIntervention = useCallback((themeName: string) => {
    setExpandedInterventions(prev => {
      const newExpanded = new Set(prev)
      if (newExpanded.has(themeName)) {
        newExpanded.delete(themeName)
      } else {
        newExpanded.add(themeName)
      }
      return newExpanded
    })
  }, [])

  const handleDownloadCSV = useCallback(async () => {
    // Use external handler if provided
    if (onDownload) {
      onDownload()
      return
    }
    
    // Otherwise use internal download logic
    if (!activeProject?.id) return
    
    setInternalIsPreparingDownload(true)
    
    try {
      const response = await fetchWithAuth(`/api/analysis-projects/${activeProject.id}/download/interventions-csv`)
      
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
      console.error('Failed to download CSV:', err)
      alert('Failed to download CSV. Please try again.')
    } finally {
      setInternalIsPreparingDownload(false)
    }
  }, [activeProject?.id, activeProject?.title, fetchWithAuth, getToken, onDownload])

  const renderStars = useCallback((score?: number) => {
    if (!score) return null
    return (
      <div className="flex items-center gap-1">
        <div className="flex">
          {[1, 2, 3, 4, 5].map((i) => (
            <Star
              key={i}
              className={`h-3 w-3 ${
                i <= Math.round(score) ? 'fill-yellow-400 text-yellow-400' : 'text-slate-300'
              }`}
            />
          ))}
        </div>
        <span className="text-xs text-slate-600">{score.toFixed(1)}</span>
      </div>
    )
  }, [])

  const sortInterventions = useCallback((interventions: InterventionTheme[]) => {
    return [...interventions].sort((a, b) => {
      switch (sortBy) {
        case 'impact':
          return (b.avg_impact_score || 0) - (a.avg_impact_score || 0)
        case 'evidence':
          return (b.avg_evidence_score || 0) - (a.avg_evidence_score || 0)
        case 'frequency':
        default:
          return (b.detailed_interventions?.length || 0) - (a.detailed_interventions?.length || 0)
      }
    })
  }, [sortBy])

  const getAllInterventions = useMemo(() => {
    if (!data) return []
    
    const interventionsMap = new Map()
    
    data.issue_themes.forEach(issue => {
      issue.related_interventions.forEach(intervention => {
        const key = intervention.theme_name
        if (interventionsMap.has(key)) {
          const existing = interventionsMap.get(key)
          existing.frequency += intervention.frequency
          if (intervention.avg_impact_score) {
            existing.impact_scores.push(intervention.avg_impact_score)
          }
          if (intervention.avg_evidence_score) {
            existing.evidence_scores.push(intervention.avg_evidence_score)
          }
          // Keep the first impact_summary we encounter (if current doesn't have one)
          if (!existing.impact_summary && intervention.impact_summary) {
            existing.impact_summary = intervention.impact_summary
          }
          // Deduplicate detailed interventions by name
          const newDetails = intervention.detailed_interventions || []
          newDetails.forEach(detail => {
            const exists = existing.detailed_interventions.some((d: DetailedIntervention) => d.name === detail.name)
            if (!exists) {
              existing.detailed_interventions.push(detail)
            }
          })
        } else {
          interventionsMap.set(key, {
            ...intervention,
            impact_scores: intervention.avg_impact_score ? [intervention.avg_impact_score] : [],
            evidence_scores: intervention.avg_evidence_score ? [intervention.avg_evidence_score] : [],
            detailed_interventions: [...(intervention.detailed_interventions || [])]
          })
        }
      })
    })
    
    const interventions = Array.from(interventionsMap.values()).map(intervention => ({
      ...intervention,
      avg_impact_score: intervention.impact_scores.length > 0 
        ? intervention.impact_scores.reduce((a: number, b: number) => a + b, 0) / intervention.impact_scores.length 
        : undefined,
      avg_evidence_score: intervention.evidence_scores.length > 0
        ? intervention.evidence_scores.reduce((a: number, b: number) => a + b, 0) / intervention.evidence_scores.length
        : undefined
    }))
    
    return sortInterventions(interventions)
  }, [data, sortInterventions])

  const convertToNavigatorInterventionData = useCallback((detailedInterventions: DetailedIntervention[]) => {
    return detailedInterventions.map((detail) => ({
      name: detail.name,
      type: detail.type || 'Unknown',
      country: detail.country || 'Unknown',
      description: detail.description,
      result_count: detail.results?.length || 0,
      results_summary: (detail.results || []).map(result => ({
        outcome: result.outcome_variable || 'Outcome',
        direction: result.effect_direction || 'unknown',
        effect_size: result.effect_size,
        effect_size_type: undefined,
        p_value: result.p_value,
        uncertainty: result.uncertainty,
        result_text: result.result_text,
        supporting_quote: undefined,
        population_measured: result.population_measured,
        subgroup_or_dose: result.subgroup_or_dose,
      })),
      total_sample_size: detail.sample_size || null,
      documents: detail.source_documents?.map(doc => ({
        doc_id: doc.doc_id || '',
        title: doc.title || 'Unknown',
        source: doc.source || 'Unknown',
        landing_page_url: doc.landing_page_url || detail.document_url,
      })) || [],
      impact_score: detail.impact_score,
      evidence_score: detail.evidence_score,
      impact_justification: detail.impact_justification,
      evidence_justification: detail.evidence_justification,
    }))
  }, [])

  if (!activeProject) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Target className="h-16 w-16 text-slate-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">No Project Selected</h3>
          <p className="text-slate-600">Select a project to view the interventions navigator.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header - only show on standalone page */}
      {showHeader && (
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Label htmlFor="standalone-group-by-issues" className="text-sm text-slate-700">
                  Group by issues
                </Label>
                <Switch
                  id="standalone-group-by-issues"
                  checked={viewMode === 'grouped'}
                  onCheckedChange={(checked) => setViewMode(checked ? 'grouped' : 'all')}
                />
              </div>
              
              <div className="flex items-center gap-2">
                <Label className="text-sm text-slate-700">Sort by:</Label>
                <select 
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'frequency' | 'impact' | 'evidence')}
                  className="text-sm border rounded px-2 py-1 bg-white"
                >
                  <option value="impact">Impact</option>
                  <option value="evidence">Evidence</option>
                  <option value="frequency">Frequency</option>
                </select>
              </div>
              
              <div className="flex items-center gap-2">
                <Button
                  onClick={handleDownloadCSV}
                  disabled={isPreparingDownload || !data || data.issue_themes.length === 0}
                  variant="outline"
                  size="sm"
                  className="flex items-center gap-2"
                >
                  <Download className="h-4 w-4" />
                  {isPreparingDownload ? 'Downloading...' : 'Download'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Content */}
      <div className="flex-1">
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
              <p className="text-slate-600">Loading interventions data...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="text-center py-12">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">Error Loading Data</h3>
            <p className="text-slate-600">{error}</p>
            <div className="flex gap-2 mt-4 justify-center">
              <Button onClick={loadNavigatorData}>
                Try Again
              </Button>
              <Button 
                variant="outline" 
                onClick={async () => {
                  try {
                    const debugResponse = await fetchWithAuth(`/api/analysis-projects/${activeProject?.id}/debug-themes`)
                    console.log('Debug themes response:', debugResponse)
                  } catch (err) {
                    console.error('Debug failed:', err)
                  }
                }}
              >
                Debug Themes
              </Button>
            </div>
          </div>
        )}

        {data && (
          <div className="space-y-6">
            {data.issue_themes.length === 0 ? (
              <Card>
                <CardContent className="p-8 text-center">
                  <AlertTriangle className="h-12 w-12 text-amber-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-900 mb-2">No Issue-Intervention Mappings Found</h3>
                  <p className="text-slate-600">
                    This project doesn&apos;t have any extracted mappings between issues and interventions yet.
                    This happens when documents are still being processed or don&apos;t contain linked policy interventions.
                  </p>
                </CardContent>
              </Card>
            ) : viewMode === 'all' ? (
              <div className="space-y-4">
                {getAllInterventions.map((intervention) => (
                  <Card key={intervention.theme_name} className="overflow-hidden">
                    <CardHeader className="pb-2">
                      <div 
                        className="flex items-center justify-between cursor-pointer"
                        onClick={() => toggleIntervention(`all-${intervention.theme_name}`)}
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-3">
                            <h5 className="font-medium text-lg">{intervention.theme_name}</h5>
                          </div>
                          {expandedInterventions.has(`all-${intervention.theme_name}`) && (
                            <div className="mt-1 space-y-1">
                              <p className="text-sm text-slate-600">{intervention.description}</p>
                              {intervention.impact_summary && (
                                <p className="text-sm text-slate-600">
                                  <span className="font-semibold">Impact: </span>
                                  {intervention.impact_summary}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                        
                        <div className="flex items-start gap-4 ml-4">
                          {intervention.avg_impact_score && (
                            <div className="text-right">
                              <div className="text-xs text-slate-500">Impact:</div>
                              {renderStars(intervention.avg_impact_score)}
                            </div>
                          )}
                          {intervention.avg_evidence_score && (
                            <div className="text-right">
                              <div className="text-xs text-slate-500">Evidence:</div>
                              {renderStars(intervention.avg_evidence_score)}
                            </div>
                          )}
                          <div className="text-right">
                            <div className="text-xs text-slate-500">Frequency:</div>
                            <div className="flex items-center gap-1">
                              <span className="text-xs text-slate-600">{intervention.detailed_interventions?.length || 0}</span>
                            </div>
                          </div>
                          <div className="ml-2">
                            {expandedInterventions.has(`all-${intervention.theme_name}`) ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </div>
                        </div>
                      </div>
                    </CardHeader>

                    {expandedInterventions.has(`all-${intervention.theme_name}`) && (
                      <CardContent className="pt-0">
                        {intervention.detailed_interventions?.length ? (
                          <div className="space-y-3">
                            <h6 className="text-sm font-medium text-slate-700">Detailed Interventions:</h6>
                            <NavigatorInterventionsTable 
                              interventions={convertToNavigatorInterventionData(intervention.detailed_interventions)}
                            />
                          </div>
                        ) : (
                          <div className="text-sm text-slate-600">
                            <p>This intervention theme appears in <strong>{intervention.frequency}</strong> documents across multiple issues.</p>
                          </div>
                        )}
                      </CardContent>
                    )}
                  </Card>
                ))}
              </div>
            ) : (
              data.issue_themes.map((issue) => (
                <Card key={issue.theme_name} className="overflow-hidden">
                  <CardHeader className="pb-3">
                    <div 
                      className="flex items-center justify-between cursor-pointer"
                      onClick={() => toggleIssue(issue.theme_name)}
                    >
                      <div className="flex-1">
                        <CardTitle className="text-lg flex items-center gap-3">
                          {issue.theme_name}
                          <Badge variant="secondary">{issue.frequency} documents</Badge>
                        </CardTitle>
                        {expandedIssues.has(issue.theme_name) && (
                          <p className="text-slate-600 mt-2">{issue.description}</p>
                        )}
                      </div>
                      <div className="ml-4">
                        {expandedIssues.has(issue.theme_name) ? (
                          <ChevronDown className="h-5 w-5" />
                        ) : (
                          <ChevronRight className="h-5 w-5" />
                        )}
                      </div>
                    </div>
                  </CardHeader>

                  {expandedIssues.has(issue.theme_name) && (
                    <CardContent className="pt-0">
                      <div className="space-y-4">
                        <h4 className="font-medium text-slate-900 flex items-center gap-2">
                          Interventions:
                        </h4>
                        
                        {sortInterventions(issue.related_interventions).map((intervention) => (
                          <Card key={intervention.theme_name} className="ml-6">
                            <CardHeader className="pb-2">
                              <div 
                                className="flex items-center justify-between cursor-pointer"
                                onClick={() => toggleIntervention(`${issue.theme_name}-${intervention.theme_name}`)}
                              >
                                <div className="flex-1">
                                  <div className="flex items-center gap-3">
                                    <h5 className="font-medium">{intervention.theme_name}</h5>
                                  </div>
                                  {expandedInterventions.has(`${issue.theme_name}-${intervention.theme_name}`) && (
                                    <div className="mt-1 space-y-1">
                                      <p className="text-sm text-slate-600">{intervention.description}</p>
                                      {intervention.impact_summary && (
                                        <p className="text-sm text-slate-600">
                                          <span className="font-semibold">Impact: </span>
                                          {intervention.impact_summary}
                                        </p>
                                      )}
                                    </div>
                                  )}
                                </div>
                                
                                <div className="flex items-start gap-4 ml-4">
                                  {intervention.avg_impact_score && (
                                    <div className="text-right">
                                      <div className="text-xs text-slate-500">Impact:</div>
                                      {renderStars(intervention.avg_impact_score)}
                                    </div>
                                  )}
                                  {intervention.avg_evidence_score && (
                                    <div className="text-right">
                                      <div className="text-xs text-slate-500">Evidence:</div>
                                      {renderStars(intervention.avg_evidence_score)}
                                    </div>
                                  )}
                                  <div className="text-right">
                                    <div className="text-xs text-slate-500">Frequency:</div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-xs text-slate-600">{intervention.detailed_interventions?.length || 0}</span>
                                    </div>
                                  </div>
                                  <div className="ml-2">
                                    {expandedInterventions.has(`${issue.theme_name}-${intervention.theme_name}`) ? (
                                      <ChevronDown className="h-4 w-4" />
                                    ) : (
                                      <ChevronRight className="h-4 w-4" />
                                    )}
                                  </div>
                                </div>
                              </div>
                            </CardHeader>

                            {expandedInterventions.has(`${issue.theme_name}-${intervention.theme_name}`) && (
                              <CardContent className="pt-0">
                                {intervention.detailed_interventions?.length ? (
                                  <div className="space-y-3">
                                    <h6 className="text-sm font-medium text-slate-700">Detailed Interventions:</h6>
                                    <NavigatorInterventionsTable 
                                      interventions={convertToNavigatorInterventionData(intervention.detailed_interventions)}
                                    />
                                  </div>
                                ) : (
                                  <div className="text-sm text-slate-600">
                                    <p>This intervention theme appears in <strong>{intervention.frequency}</strong> documents.</p>
                                  </div>
                                )}
                              </CardContent>
                            )}
                          </Card>
                        ))}
                      </div>
                    </CardContent>
                  )}
                </Card>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
