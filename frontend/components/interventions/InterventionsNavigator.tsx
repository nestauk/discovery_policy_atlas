'use client'

import { useState, useEffect, useMemo } from 'react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import { useProjectDataCache } from '@/lib/projectDataCache'
import { Button } from '@/components/ui/button'
import { Loader2, Target, AlertTriangle } from 'lucide-react'
import { ThemeList, type ThemeListItem } from './ThemeList'
import { ThemeDetailView } from './ThemeDetailView'
import type { OutcomeTheme, RiskTheme, TransferabilityBreakdown } from '@/types/search'

interface DetailedIntervention {
  name: string
  description: string
  type?: string
  country?: string
  evidence_category?: string
  evidence_category_reasoning?: string
  is_systematic_review?: boolean
  sample_size?: number | null
  impact_score?: number
  evidence_score?: number
  impact_score_label?: string
  impact_score_breakdown?: Record<string, unknown> | null
  transferability_score?: number
  transferability_breakdown?: Record<string, unknown> | null
  impact_justification?: string
  evidence_justification?: string
  has_harm_warning?: boolean
  harm_warning_reason?: string
  supporting_quote?: string
  document_url?: string
  results: Array<{
    outcome_variable?: string
    direction?: string
    effect_direction?: string
    effect_size?: string
    effect_size_type?: string
    p_value?: string
    uncertainty?: string
    result_text?: string
    supporting_quote?: string
    population_measured?: string
    subgroup_or_dose?: string
    heterogeneity_I2?: string
    tau2?: string
    summary_statistic?: string
    estimate_level?: string
    n_studies?: number
    sample_size?: number
    stratum_type?: string
    stratum_value?: string
  }>
  source_documents: Array<{
    doc_id?: string
    title?: string
    source?: string
    landing_page_url?: string
    evidence_category?: string
    evidence_confidence?: number
    sample_size?: number
  }>
}

interface InterventionTheme {
  theme_name: string
  description: string
  impact_summary?: string
  frequency: number
  impact_score?: number
  impact_score_label?: string
  impact_score_breakdown?: Record<string, unknown> | null
  avg_impact_score?: number
  avg_evidence_score?: number
  detailed_interventions?: DetailedIntervention[]
  transferability_rating?: string | null
  transferability_note?: string | null
  transferability_breakdown?: TransferabilityBreakdown | null
  outcome_themes?: OutcomeTheme[]
  risk_themes?: RiskTheme[]
  // Evidence mix fields
  stars?: number
  base_rating?: number
  cap_applied?: string | null
  cap_message?: string | null
  display_evidence_mix?: Record<string, number>
  // Issue-specific fields (when grouped by issue)
  issue_display_evidence_mix?: Record<string, number>
  issue_stars?: number
  issue_base_rating?: number
  issue_cap_applied?: string | null
  issue_cap_message?: string | null
}

interface IssueTheme {
  theme_name: string
  description: string
  frequency: number
  related_interventions: InterventionTheme[]
}

interface NavigatorData {
  issue_themes: IssueTheme[]
  all_interventions?: InterventionTheme[]
}

interface OverviewItem {
  theme_name: string
  description: string
  frequency: number
  avg_impact_score: number | null
  avg_evidence_score: number | null
  study_count: number
}

interface OverviewData {
  interventions: OverviewItem[]
  issue_themes: { theme_name: string; frequency: number }[]
}

interface InterventionsNavigatorProps {
  showHeader?: boolean
  isPublic?: boolean
  publicProjectId?: string
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
  const _shown = tiers[Math.max(0, Math.min(4, value - 1))]

  return (
    <div className="flex-1 min-w-[180px]">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium text-gray-700">{label}</div>
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
  showHeader = true,
  isPublic = false,
  publicProjectId,
}: InterventionsNavigatorProps) {
  const { activeProject } = useAnalysisProjectStore()
  const { fetchWithAuth } = useAPI()
  const { getCached, setCache } = useProjectDataCache()
  
  const projectId = isPublic ? publicProjectId : activeProject?.id
  
  // Full navigator data (heavy, loaded in background)
  const [data, setData] = useState<NavigatorData | null>(null)
  // Lightweight overview (fast, shown immediately)
  const [overviewData, setOverviewData] = useState<OverviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [selectedTheme, setSelectedTheme] = useState<ThemeListItem | null>(null)
  
  const [sortBy, _setSortBy] = useState<'impact' | 'evidence'>('evidence')
  const [minImpact, setMinImpact] = useState(1)
  const [minEvidence, setMinEvidence] = useState(1)
  const [issueThemeFilter, setIssueThemeFilter] = useState<string>('All')

  const hasFullData = !!data
  
  const issueThemeOptions = useMemo(() => {
    if (data) {
      return ['All', ...data.issue_themes.map(t => t.theme_name)]
    }
    if (overviewData) {
      return ['All', ...overviewData.issue_themes.map(t => t.theme_name)]
    }
    return ['All']
  }, [data, overviewData])

  // Progressive loading: overview first, then full data in background
  useEffect(() => {
    if (!projectId) return

    let cancelled = false

    const load = async () => {
      // 1. Check cache for full data
      const cachedFull = getCached('navigator', projectId) as NavigatorData | undefined
      if (cachedFull) {
        setData(cachedFull)
        return
      }

      // 2. Check cache for overview
      const cachedOverview = getCached('navigatorOverview', projectId) as OverviewData | undefined
      if (cachedOverview) {
        setOverviewData(cachedOverview)
      } else {
        // 3. Fetch lightweight overview (fast)
        setLoading(true)
        setError(null)
        try {
          let overview: OverviewData
          if (isPublic) {
            // Public projects fall back to full data (no overview endpoint)
            const { getPublicNavigator } = await import('@/lib/publicApi')
            const response = await getPublicNavigator(projectId) as NavigatorData
            if (!cancelled) {
              setData(response)
              setCache('navigator', projectId, response)
              setLoading(false)
            }
            return
          } else {
            overview = await fetchWithAuth(
              `/api/analysis-projects/${projectId}/navigator-overview`
            ) as OverviewData
          }
          if (!cancelled) {
            setOverviewData(overview)
            setCache('navigatorOverview', projectId, overview)
            setLoading(false)
          }
        } catch (err) {
          console.error('Failed to load navigator overview, falling back to full load:', err)
          // Don't set error — fall through to load full data directly
        }
      }

      // 4. Fetch full data (in background if overview loaded, or as primary if it failed)
      try {
        let response: NavigatorData
        if (isPublic) {
          const { getPublicNavigator } = await import('@/lib/publicApi')
          response = await getPublicNavigator(projectId) as NavigatorData
        } else {
          response = await fetchWithAuth(
            `/api/analysis-projects/${projectId}/issue-intervention-navigator`
          ) as NavigatorData
        }
        if (!cancelled) {
          setData(response)
          setCache('navigator', projectId, response)
          setLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to load full navigator data:', err)
          setError(err instanceof Error ? err.message : 'Failed to load data')
          setLoading(false)
        }
      }
    }

    load()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, isPublic])

  // Aggregate all intervention themes across issues (or from all_interventions if available)
  const allInterventionThemes = useMemo(() => {
    // When full data hasn't arrived yet, use overview data for the list
    if (!data && overviewData && issueThemeFilter === 'All') {
      return overviewData.interventions.map(item => ({
        theme_name: item.theme_name,
        description: item.description,
        frequency: item.study_count,
        avg_impact_score: item.avg_impact_score ?? undefined,
        avg_evidence_score: item.avg_evidence_score ?? undefined,
        detailed_interventions: undefined,
        impact_summary: undefined as string | undefined,
        transferability_rating: undefined as string | null | undefined,
        transferability_note: undefined as string | null | undefined,
        transferability_breakdown: undefined as TransferabilityBreakdown | null | undefined,
        outcome_themes: undefined as OutcomeTheme[] | undefined,
        risk_themes: undefined as RiskTheme[] | undefined,
        display_evidence_mix: undefined as Record<string, number> | undefined,
        stars: undefined as number | undefined,
        cap_message: undefined as string | null | undefined,
        impact_score_breakdown: undefined as Record<string, unknown> | null | undefined,
      }))
    }

    if (!data) return []
    
    // If backend provides all_interventions directly, use that
    if (data.all_interventions && data.all_interventions.length > 0) {
      // Apply issue theme filter if needed
      if (issueThemeFilter === 'All') {
        return data.all_interventions.map(intervention => ({
          theme_name: intervention.theme_name,
          description: intervention.description,
          impact_summary: intervention.impact_summary,
          frequency: intervention.frequency,
          avg_impact_score: intervention.impact_score ?? intervention.avg_impact_score,
          avg_evidence_score: intervention.stars ?? intervention.avg_evidence_score,
          detailed_interventions: intervention.detailed_interventions,
          // Pass through all the rich data
          transferability_rating: intervention.transferability_rating,
          transferability_note: intervention.transferability_note,
          transferability_breakdown: intervention.transferability_breakdown,
          outcome_themes: intervention.outcome_themes,
          risk_themes: intervention.risk_themes,
          display_evidence_mix: intervention.display_evidence_mix,
          stars: intervention.stars,
          cap_message: intervention.cap_message,
          impact_score_breakdown: intervention.impact_score_breakdown,
        }))
      }
      
      // Filter by issue theme - need to aggregate from issue_themes
      const filteredIssues = data.issue_themes.filter(t => t.theme_name === issueThemeFilter)
      const interventionsMap = new Map<string, InterventionTheme>()
      
      filteredIssues.forEach(issue => {
        issue.related_interventions.forEach(intervention => {
          if (!interventionsMap.has(intervention.theme_name)) {
            interventionsMap.set(intervention.theme_name, intervention)
          }
        })
      })
      
      return Array.from(interventionsMap.values()).map(intervention => ({
        theme_name: intervention.theme_name,
        description: intervention.description,
        impact_summary: intervention.impact_summary,
        frequency: intervention.frequency,
        avg_impact_score: intervention.impact_score ?? intervention.avg_impact_score,
        avg_evidence_score: intervention.issue_stars ?? intervention.avg_evidence_score,
        detailed_interventions: intervention.detailed_interventions,
        transferability_rating: intervention.transferability_rating,
        transferability_note: intervention.transferability_note,
        transferability_breakdown: intervention.transferability_breakdown,
        outcome_themes: intervention.outcome_themes,
        risk_themes: intervention.risk_themes,
        display_evidence_mix: intervention.issue_display_evidence_mix ?? intervention.display_evidence_mix,
        stars: intervention.issue_stars ?? intervention.stars,
        cap_message: intervention.issue_cap_message ?? intervention.cap_message,
        impact_score_breakdown: intervention.impact_score_breakdown,
      }))
    }
    
    // Fallback: aggregate from issue_themes
    const interventionsMap = new Map<string, {
      theme_name: string
      description: string
      impact_summary?: string
      frequency: number
      impact_scores: number[]
      evidence_scores: number[]
      detailed_interventions: DetailedIntervention[]
      transferability_rating?: string | null
      transferability_note?: string | null
      transferability_breakdown?: TransferabilityBreakdown | null
      outcome_themes?: OutcomeTheme[]
      risk_themes?: RiskTheme[]
      display_evidence_mix?: Record<string, number>
      stars?: number
      cap_message?: string | null
      impact_score_breakdown?: Record<string, unknown> | null
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
          // Merge detailed interventions (dedupe by doc)
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
          // Merge outcome themes if not already set
          if (!existing.outcome_themes && intervention.outcome_themes) {
            existing.outcome_themes = intervention.outcome_themes
          }
          if (!existing.risk_themes && intervention.risk_themes) {
            existing.risk_themes = intervention.risk_themes
          }
          if (!existing.transferability_breakdown && intervention.transferability_breakdown) {
            existing.transferability_breakdown = intervention.transferability_breakdown
            existing.transferability_rating = intervention.transferability_rating
            existing.transferability_note = intervention.transferability_note
          }
        } else {
          interventionsMap.set(key, {
            theme_name: intervention.theme_name,
            description: intervention.description,
            impact_summary: intervention.impact_summary,
            frequency: intervention.frequency,
            impact_scores: intervention.avg_impact_score != null ? [intervention.avg_impact_score] : [],
            evidence_scores: intervention.avg_evidence_score != null ? [intervention.avg_evidence_score] : [],
            detailed_interventions: [...(intervention.detailed_interventions || [])],
            transferability_rating: intervention.transferability_rating,
            transferability_note: intervention.transferability_note,
            transferability_breakdown: intervention.transferability_breakdown,
            outcome_themes: intervention.outcome_themes,
            risk_themes: intervention.risk_themes,
            display_evidence_mix: intervention.issue_display_evidence_mix ?? intervention.display_evidence_mix,
            stars: intervention.issue_stars ?? intervention.stars,
            cap_message: intervention.issue_cap_message ?? intervention.cap_message,
            impact_score_breakdown: intervention.impact_score_breakdown,
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
      detailed_interventions: intervention.detailed_interventions,
      transferability_rating: intervention.transferability_rating,
      transferability_note: intervention.transferability_note,
      transferability_breakdown: intervention.transferability_breakdown,
      outcome_themes: intervention.outcome_themes,
      risk_themes: intervention.risk_themes,
      display_evidence_mix: intervention.display_evidence_mix,
      stars: intervention.stars,
      cap_message: intervention.cap_message,
      impact_score_breakdown: intervention.impact_score_breakdown,
    }))
  }, [data, overviewData, issueThemeFilter])

  // Get the full intervention data for the selected theme
  const selectedThemeData = useMemo(() => {
    if (!selectedTheme || !data) return null
    
    // Find the full intervention data with all the rich fields
    const fullData = allInterventionThemes.find(t => t.theme_name === selectedTheme.theme_name)
    return fullData || null
  }, [selectedTheme, data, allInterventionThemes])

  // Get interventions for the selected theme (for ThemeDetailView)
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

  if (!projectId) {
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
    // Full data available — show detail view
    if (selectedThemeData) {
      return (
        <div className="flex flex-col h-full">
          <ThemeDetailView
            themeName={selectedTheme.theme_name}
            themeDescription={selectedThemeData.description || selectedTheme.description}
            avgImpactScore={selectedThemeData.avg_impact_score ?? selectedTheme.avg_impact_score ?? undefined}
            avgEvidenceScore={selectedThemeData.avg_evidence_score ?? selectedTheme.avg_evidence_score ?? undefined}
            interventions={selectedThemeInterventions}
            onBack={() => setSelectedTheme(null)}
            impactSummary={selectedThemeData.impact_summary}
            outcomeThemes={selectedThemeData.outcome_themes}
            riskThemes={selectedThemeData.risk_themes}
            transferabilityRating={selectedThemeData.transferability_rating}
            transferabilityNote={selectedThemeData.transferability_note}
            transferabilityBreakdown={selectedThemeData.transferability_breakdown}
            displayEvidenceMix={selectedThemeData.display_evidence_mix}
            evidenceStars={selectedThemeData.stars}
            capMessage={selectedThemeData.cap_message}
            isPublic={isPublic}
            projectId={projectId ?? undefined}
          />
        </div>
      )
    }

    // Full data still loading — show spinner for this theme
    return (
      <div className="flex flex-col h-full">
        <div className="mb-4">
          <Button variant="ghost" size="sm" onClick={() => setSelectedTheme(null)}>
            ← Back
          </Button>
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
            <p className="text-slate-600">Loading details for {selectedTheme.theme_name}...</p>
          </div>
        </div>
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
                <div className="text-sm font-medium text-gray-700 mb-2">Choose by issues</div>
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
        {loading && !overviewData && !data && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
              <p className="text-slate-600">Loading interventions data...</p>
            </div>
          </div>
        )}

        {error && !overviewData && !data && (
          <div className="text-center py-12">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">Error Loading Data</h3>
            <p className="text-slate-600">{error}</p>
          </div>
        )}

        {(data || overviewData) && !loading && !error && (
          <>
            {allInterventionThemes.length === 0 ? (
              <div className="bg-white border border-gray-100 rounded-xl p-8 text-center">
                <AlertTriangle className="h-12 w-12 text-amber-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">No Interventions Found</h3>
                <p className="text-slate-600">
                  This happens when documents are still being processed or synthesis has not completed.
                </p>
              </div>
            ) : (
              <>
                <ThemeList
                  themes={allInterventionThemes}
                  onSelectTheme={setSelectedTheme}
                  sortBy={sortBy}
                  minImpact={minImpact}
                  minEvidence={minEvidence}
                />
                {!hasFullData && (
                  <div className="flex items-center justify-center py-3 text-xs text-slate-400">
                    <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                    Loading detailed data…
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
