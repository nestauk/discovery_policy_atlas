'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Loader2, Target, AlertTriangle } from 'lucide-react'
import { ThemeList, type ThemeListItem } from './ThemeList'
import { ThemeDetailView } from './ThemeDetailView'

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

interface InterventionTheme {
  theme_name: string
  description: string
  impact_summary?: string
  frequency: number
  avg_impact_score?: number
  avg_evidence_score?: number
  detailed_interventions?: DetailedIntervention[]
}

interface IssueTheme {
  theme_name: string
  description: string
  frequency: number
  related_interventions: InterventionTheme[]
}

interface NavigatorData {
  issue_themes: IssueTheme[]
}

interface InterventionsNavigatorProps {
  showHeader?: boolean
}

function RangeFilter({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (v: number) => void
}) {
  const tiers = ['Very low', 'Low', 'Moderate', 'High', 'Very high']
  const shown = tiers[Math.max(0, Math.min(4, value - 1))]

  return (
    <div className="flex-1 min-w-[180px]">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium text-gray-700">{label}</div>
        <div className="text-xs text-gray-500">{shown}+</div>
      </div>
      <input
        type="range"
        min={1}
        max={5}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
      />
      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>Very low</span>
        <span>Very high</span>
      </div>
    </div>
  )
}

export function InterventionsNavigator({ 
  showHeader = true
}: InterventionsNavigatorProps) {
  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth } = useAPI()
  
  const [data, setData] = useState<NavigatorData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [selectedTheme, setSelectedTheme] = useState<ThemeListItem | null>(null)
  
  const [sortBy, _setSortBy] = useState<'impact' | 'evidence'>('evidence')
  const [minImpact, setMinImpact] = useState(1)
  const [minEvidence, setMinEvidence] = useState(1)
  const [issueThemeFilter, setIssueThemeFilter] = useState<string>('All')
  
  const issueThemeOptions = useMemo(() => {
    if (!data) return ['All']
    const themes = data.issue_themes.map(t => t.theme_name)
    return ['All', ...themes]
  }, [data])

  const loadNavigatorData = useCallback(async () => {
    if (!activeProject?.id) return
    
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetchWithAuth(`/api/analysis-projects/${activeProject.id}/issue-intervention-navigator`)
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
  }, [activeProject?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const allInterventionThemes = useMemo(() => {
    if (!data) return []
    
    const interventionsMap = new Map<string, {
      theme_name: string
      description: string
      impact_summary?: string
      frequency: number
      impact_scores: number[]
      evidence_scores: number[]
      detailed_interventions: DetailedIntervention[]
    }>()
    
    const filteredIssues = issueThemeFilter === 'All' 
      ? data.issue_themes 
      : data.issue_themes.filter(t => t.theme_name === issueThemeFilter)
    
    filteredIssues.forEach(issue => {
      issue.related_interventions.forEach(intervention => {
        const key = intervention.theme_name
        const existing = interventionsMap.get(key)
        
        if (existing) {
          existing.frequency += intervention.frequency
          if (intervention.avg_impact_score != null) {
            existing.impact_scores.push(intervention.avg_impact_score)
          }
          if (intervention.avg_evidence_score != null) {
            existing.evidence_scores.push(intervention.avg_evidence_score)
          }
          if (!existing.impact_summary && intervention.impact_summary) {
            existing.impact_summary = intervention.impact_summary
          }
          const newDetails = intervention.detailed_interventions || []
          newDetails.forEach(detail => {
            const detailDocId = detail.source_documents?.[0]?.doc_id || ''
            const detailDocTitle = detail.source_documents?.[0]?.title || ''
            const exists = existing.detailed_interventions.some(d => {
              const dDocId = d.source_documents?.[0]?.doc_id || ''
              const dDocTitle = d.source_documents?.[0]?.title || ''
              return d.name === detail.name && (dDocId === detailDocId || dDocTitle === detailDocTitle)
            })
            if (!exists) {
              existing.detailed_interventions.push(detail)
            }
          })
        } else {
          interventionsMap.set(key, {
            theme_name: intervention.theme_name,
            description: intervention.description,
            impact_summary: intervention.impact_summary,
            frequency: intervention.frequency,
            impact_scores: intervention.avg_impact_score != null ? [intervention.avg_impact_score] : [],
            evidence_scores: intervention.avg_evidence_score != null ? [intervention.avg_evidence_score] : [],
            detailed_interventions: [...(intervention.detailed_interventions || [])]
          })
        }
      })
    })
    
    return Array.from(interventionsMap.values()).map(intervention => ({
      theme_name: intervention.theme_name,
      description: intervention.description,
      impact_summary: intervention.impact_summary,
      frequency: intervention.frequency,
      avg_impact_score: intervention.impact_scores.length > 0 
        ? intervention.impact_scores.reduce((a, b) => a + b, 0) / intervention.impact_scores.length 
        : undefined,
      avg_evidence_score: intervention.evidence_scores.length > 0
        ? intervention.evidence_scores.reduce((a, b) => a + b, 0) / intervention.evidence_scores.length
        : undefined,
      detailed_interventions: intervention.detailed_interventions
    }))
  }, [data, issueThemeFilter])

  const selectedThemeInterventions = useMemo(() => {
    if (!selectedTheme || !data) return []
    
    const filteredIssues = issueThemeFilter === 'All' 
      ? data.issue_themes 
      : data.issue_themes.filter(t => t.theme_name === issueThemeFilter)
    
    const matching: InterventionTheme[] = []
    filteredIssues.forEach(issue => {
      issue.related_interventions.forEach(intervention => {
        if (intervention.theme_name === selectedTheme.theme_name) {
          matching.push(intervention)
        }
      })
    })
    return matching
  }, [selectedTheme, data, issueThemeFilter])

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

  if (selectedTheme) {
    const aggregated = allInterventionThemes.find(t => t.theme_name === selectedTheme.theme_name)
    
    return (
      <div className="flex flex-col h-full">
        <ThemeDetailView
          themeName={selectedTheme.theme_name}
          themeDescription={aggregated?.description || selectedTheme.description}
          avgImpactScore={aggregated?.avg_impact_score ?? selectedTheme.avg_impact_score ?? undefined}
          avgEvidenceScore={aggregated?.avg_evidence_score ?? selectedTheme.avg_evidence_score ?? undefined}
          interventions={selectedThemeInterventions}
          onBack={() => setSelectedTheme(null)}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {showHeader && (
        <div className="mb-6">
          <div className="bg-white border border-gray-100 rounded-xl p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <RangeFilter 
                label="Min Impact" 
                value={minImpact} 
                onChange={setMinImpact} 
              />
              <RangeFilter 
                label="Min Evidence" 
                value={minEvidence} 
                onChange={setMinEvidence} 
              />
              <div className="flex-1 min-w-[180px]">
                <div className="text-sm font-medium text-gray-700 mb-2">Issue theme</div>
                <select
                  value={issueThemeFilter}
                  onChange={(e) => setIssueThemeFilter(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  {issueThemeOptions.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      )}
      
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
            <Button onClick={loadNavigatorData} className="mt-4">
              Try Again
            </Button>
          </div>
        )}

        {data && !loading && !error && (
          <>
            {data.issue_themes.length === 0 ? (
              <div className="bg-white border border-gray-100 rounded-xl p-8 text-center">
                <AlertTriangle className="h-12 w-12 text-amber-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">No Interventions Found</h3>
                <p className="text-slate-600">
                  This happens when documents are still being processed or synthesis has not completed.
                </p>
              </div>
            ) : (
              <ThemeList
                themes={allInterventionThemes}
                onSelectTheme={setSelectedTheme}
                sortBy={sortBy}
                minImpact={minImpact}
                minEvidence={minEvidence}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
