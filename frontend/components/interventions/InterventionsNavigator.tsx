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
import { NavigatorInterventionsTable } from '@/components/interventions/NavigatorInterventionsTable'
import { type InterventionData } from '@/components/interventions/InterventionsTable'
import { getEvidenceScoreExplanation, formatEvidenceMixCompact, getEvidenceCategories } from '@/lib/evidenceCategories'
import { Tooltip } from '@/components/ui/tooltip'

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
  // New evidence strength methodology
  stars?: number
  base_rating?: number
  cap_applied?: string | null
  cap_message?: string | null
  evidence_mix?: Record<string, number>  // Intervention-level (all docs for this intervention)
  issue_evidence_mix?: Record<string, number>  // Issue-specific (only shared docs)
  display_evidence_mix?: Record<string, number>
  issue_display_evidence_mix?: Record<string, number>
  issue_stars?: number
  issue_base_rating?: number
  issue_cap_applied?: string | null
  issue_cap_message?: string | null
  detailed_interventions?: DetailedIntervention[]
}

interface DetailedIntervention {
  name: string
  description: string
  type?: string
  country?: string
  evidence_category?: string
  is_systematic_review?: boolean
  sample_size?: number | null
  impact_score?: number
  evidence_score?: number
  impact_justification?: string
  evidence_justification?: string
  document_url?: string
  results: Array<{
    outcome_variable?: string
    // Support both 'direction' (new schema) and 'effect_direction' (legacy)
    direction?: string
    effect_direction?: string
    effect_size?: string
    effect_size_type?: string
    p_value?: string
    uncertainty?: string
    result_text?: string
    population_measured?: string
    subgroup_or_dose?: string
    // SR-specific fields for meta-analysis results
    heterogeneity_I2?: string
    tau2?: string
    summary_statistic?: string
    estimate_level?: string
    // Sample size fields
    n_studies?: number
    sample_size?: number
    // Stratum fields
    stratum_type?: string
    stratum_value?: string
  }>
  source_documents: Array<{
    doc_id?: string
    title?: string
    source?: string
    landing_page_url?: string
    evidence_category?: string
  }>
}

interface AggregatedInterventionRow {
  name: string
  type: string
  country: string
  description: string
  evidence_category?: string
  evidence_categories?: string[]
  is_systematic_review?: boolean
  result_count: number
  results_summary: Array<{
    outcome: string
    direction: string
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
    evidence_category?: string
    is_systematic_review?: boolean
  }>
  outcome_groups?: Array<{
    document: {
      doc_id: string
      title: string
      source: string
      landing_page_url?: string
      evidence_category?: string
      reported_sample_size?: number
    }
    results: AggregatedInterventionRow['results_summary']
  }>
  total_sample_size: number | null
  documents: Array<{
    doc_id: string
    title: string
    source: string
    landing_page_url?: string
  }>
  impact_score?: number
  evidence_score?: number
  impact_justification?: string
  evidence_justification?: string
}

interface NavigatorData {
  issue_themes: IssueTheme[]
}

// Type for result summary entries
type ResultSummary = AggregatedInterventionRow['results_summary'][number]

// Type for input results (from DetailedIntervention)
type ResultInput = DetailedIntervention['results'][number]

/**
 * Maps a raw result object to the standardized ResultSummary format.
 * Consolidates duplicated mapping logic.
 */
function mapResultToSummary(result: ResultInput, evidenceCategory?: string): ResultSummary {
  return {
    outcome: result.outcome_variable || 'Outcome',
    direction: result.direction || result.effect_direction || 'unknown',
    effect_size: result.effect_size,
    effect_size_type: result.effect_size_type,
    p_value: result.p_value,
    uncertainty: result.uncertainty,
    result_text: result.result_text,
    supporting_quote: undefined,
    population_measured: result.population_measured,
    subgroup_or_dose: result.subgroup_or_dose,
    heterogeneity_I2: result.heterogeneity_I2,
    tau2: result.tau2,
    summary_statistic: result.summary_statistic,
    estimate_level: result.estimate_level,
    n_studies: result.n_studies,
    sample_size: result.sample_size,
    stratum_type: result.stratum_type,
    stratum_value: result.stratum_value,
    evidence_category: evidenceCategory,
    is_systematic_review: evidenceCategory === 'Systematic Review and Meta-Analysis',
  }
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
  
  // Fallback state for extracted interventions (when synthesis is not done)
  const [fallbackInterventions, setFallbackInterventions] = useState<InterventionData[] | null>(null)
  const [loadingFallback, setLoadingFallback] = useState(false)
  
  // Use external state if provided, otherwise use internal state
  const [internalViewMode, setInternalViewMode] = useState<'grouped' | 'all'>('all')
  const [internalSortBy, setInternalSortBy] = useState<'frequency' | 'impact' | 'evidence'>('evidence')
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
  
  // Load fallback interventions if navigator data is empty
  useEffect(() => {
    const loadFallback = async () => {
      if (!activeProject?.id) return
      if (!data || data.issue_themes.length > 0) return // Only load if navigator is empty
      
      setLoadingFallback(true)
      try {
        const response = await fetchWithAuth(`/api/analysis-projects/${activeProject.id}/interventions`)
        setFallbackInterventions(response.interventions || [])
      } catch (err) {
        console.error('Failed to load fallback interventions:', err)
        setFallbackInterventions([])
      } finally {
        setLoadingFallback(false)
      }
    }
    
    loadFallback()
  }, [activeProject?.id, data]) // eslint-disable-line react-hooks/exhaustive-deps

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

  const renderStars = useCallback((score?: number, showDecimal: boolean = true, noDataTooltip?: string) => {
    // Show greyed stars with tooltip when no score
    if (score === undefined || score === null || score === 0) {
      return (
        <Tooltip content={noDataTooltip || "Not enough data"}>
          <div className="flex items-center gap-1 cursor-help">
            <div className="flex">
              {[1, 2, 3, 4, 5].map((i) => (
                <Star
                  key={i}
                  className="h-3 w-3 fill-gray-200 text-gray-200"
                />
              ))}
            </div>
            {showDecimal && <span className="text-xs text-slate-400">N/A</span>}
          </div>
        </Tooltip>
      )
    }
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
        {showDecimal && <span className="text-xs text-slate-600">{score.toFixed(1)}</span>}
      </div>
    )
  }, [])

  const computeDisplayEvidenceMix = useCallback((detailedInterventions?: DetailedIntervention[]) => {
    if (!detailedInterventions || detailedInterventions.length === 0) {
      return {}
    }
    const categories = getEvidenceCategories()
    const categoryToKey = new Map(categories.map(category => [category.name, category.key]))
    const counts: Record<string, number> = {}
    const seenDocIds = new Set<string>()
    for (const detail of detailedInterventions) {
      const sourceDoc = detail.source_documents?.[0]
      const docId = sourceDoc?.doc_id
      const evidenceCategory = sourceDoc?.evidence_category || detail.evidence_category
      if (!evidenceCategory) continue
      if (docId) {
        if (seenDocIds.has(docId)) continue
        seenDocIds.add(docId)
      }
      const key = categoryToKey.get(evidenceCategory) || 'unknown'
      counts[key] = (counts[key] || 0) + 1
    }
    return counts
  }, [])

  const parseSampleSizeValue = useCallback((value: unknown): number | null => {
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
      return Math.trunc(value)
    }
    if (typeof value === 'string') {
      const cleaned = value.replace(/,/g, '').trim()
      if (!cleaned) return null
      const match = cleaned.match(/\d+/)
      if (!match) return null
      const parsed = Number(match[0])
      return Number.isFinite(parsed) && parsed > 0 ? parsed : null
    }
    return null
  }, [])

  // Apply frontend caps + sample-size penalty for All Interventions aggregation.
  // Mirrors backend logic in evidence_strength.py where possible.
  const applyFrontendEvidenceCaps = useCallback((
    stars: number | undefined,
    evidenceMix: Record<string, number>,
    detailedInterventions: DetailedIntervention[] | undefined,
    fallbackCapMessage?: string | null
  ): { stars: number | undefined; capMessage?: string | null } => {
    if (stars === undefined) return { stars, capMessage: fallbackCapMessage ?? null }

    let adjustedStars = stars
    const capMessages: string[] = []
    const categories = getEvidenceCategories()
    const categoryToKey = new Map(categories.map(category => [category.name, category.key]))

    const hasSystematicReview = (evidenceMix['systematic_review'] || 0) > 0
    const hasRct = (evidenceMix['rct'] || 0) > 0
    const hasObservational = (evidenceMix['observational'] || 0) > 0
    const hasCausal = hasRct || hasObservational

    // Apply small-sample penalty for causal evidence if all known samples are < 100
    if (!hasSystematicReview && hasCausal && detailedInterventions?.length) {
      const seenDocIds = new Set<string>()
      const causalSampleSizes: number[] = []

      detailedInterventions.forEach((detail, idx) => {
        const sourceDoc = detail.source_documents?.[0]
        const docId = sourceDoc?.doc_id || `${detail.name || 'unknown'}-${idx}`
        const evidenceCategory = sourceDoc?.evidence_category || detail.evidence_category
        if (!evidenceCategory) return
        const key = categoryToKey.get(evidenceCategory)
        if (key !== 'rct' && key !== 'observational') return
        if (seenDocIds.has(docId)) return
        seenDocIds.add(docId)

        const sampleSize = parseSampleSizeValue(sourceDoc?.sample_size)
        if (sampleSize !== null) {
          causalSampleSizes.push(sampleSize)
        }
      })

      if (
        causalSampleSizes.length > 0
        && causalSampleSizes.every(sample => sample < 100)
      ) {
        adjustedStars = Math.max(0, adjustedStars - 1)
        capMessages.push(
          'All studies have sample sizes under 100, limiting statistical power'
        )
      }
    }

    // Apply single-study caps based on evidence mix
    if ((evidenceMix['systematic_review'] || 0) === 1 && adjustedStars > 4) {
      adjustedStars = 4
      capMessages.push('Limited by single systematic review')
    }
    if ((evidenceMix['rct'] || 0) === 1 && !hasSystematicReview && adjustedStars > 3) {
      adjustedStars = 3
      capMessages.push('Limited by single experimental study')
    }
    if (
      (evidenceMix['observational'] || 0) === 1
      && !hasSystematicReview
      && !hasRct
      && adjustedStars > 2
    ) {
      adjustedStars = 2
      capMessages.push('Limited by single observational study')
    }

    const capMessage = capMessages.length > 0
      ? capMessages.join('. ')
      : (fallbackCapMessage ?? null)

    return { stars: adjustedStars, capMessage }
  }, [parseSampleSizeValue])

  const sortInterventions = useCallback((interventions: InterventionTheme[]) => {
    return [...interventions].sort((a, b) => {
      switch (sortBy) {
        case 'impact':
          return (b.avg_impact_score || 0) - (a.avg_impact_score || 0)
        case 'evidence':
          // Use new stars field instead of avg_evidence_score
          return (b.stars ?? 0) - (a.stars ?? 0)
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
          // Keep the highest stars rating when combining themes
          // evidence_mix is now pre-computed per intervention theme (deduplicated),
          // so we just keep it alongside the stars rating
          if (intervention.stars !== undefined && (existing.stars === undefined || intervention.stars > existing.stars)) {
            existing.stars = intervention.stars
            existing.base_rating = intervention.base_rating
            existing.cap_applied = intervention.cap_applied
            existing.cap_message = intervention.cap_message
            existing.evidence_mix = intervention.evidence_mix
          } else if (!existing.evidence_mix && intervention.evidence_mix) {
            // Fallback: keep first evidence_mix if we don't have one yet
            existing.evidence_mix = intervention.evidence_mix
          }
          // Keep the first impact_summary we encounter (if current doesn't have one)
          if (!existing.impact_summary && intervention.impact_summary) {
            existing.impact_summary = intervention.impact_summary
          }
          // Deduplicate detailed interventions by name + evidence_category
          // This preserves different evidence types for the same intervention
          const newDetails = intervention.detailed_interventions || []
          newDetails.forEach(detail => {
            const exists = existing.detailed_interventions.some(
              (d: DetailedIntervention) => d.name === detail.name && d.evidence_category === detail.evidence_category
            )
            if (!exists) {
              existing.detailed_interventions.push(detail)
            }
          })
        } else {
          interventionsMap.set(key, {
            ...intervention,
            impact_scores: intervention.avg_impact_score ? [intervention.avg_impact_score] : [],
            evidence_mix: intervention.evidence_mix ? { ...intervention.evidence_mix } : {},
            detailed_interventions: [...(intervention.detailed_interventions || [])]
          })
        }
      })
    })

    const interventions = Array.from(interventionsMap.values()).map(intervention => {
      const displayMix = computeDisplayEvidenceMix(intervention.detailed_interventions)
      const capResult = applyFrontendEvidenceCaps(
        intervention.stars,
        displayMix,
        intervention.detailed_interventions,
        intervention.cap_message
      )
      return {
        ...intervention,
        avg_impact_score: intervention.impact_scores.length > 0
          ? intervention.impact_scores.reduce((a: number, b: number) => a + b, 0) / intervention.impact_scores.length
          : undefined,
        display_evidence_mix: displayMix,
        stars: capResult.stars,
        cap_message: capResult.capMessage ?? null,
      }
    })

    return sortInterventions(interventions)
  }, [data, sortInterventions, computeDisplayEvidenceMix, applyFrontendEvidenceCaps])

  const convertToNavigatorInterventionData = useCallback((detailedInterventions: DetailedIntervention[]) => {
    if (!detailedInterventions || detailedInterventions.length === 0) {
      return []
    }

    const categories = getEvidenceCategories()
    const categoryRank = new Map(categories.map(category => [category.name, category.rank]))

    const aggregated = new Map<string, {
      name: string
      types: Set<string>
      countries: Set<string>
      description: string
      evidence_categories: Set<string>
      has_sr: boolean
      has_non_sr: boolean
      result_count: number
      results_summary: AggregatedInterventionRow['results_summary']
      outcome_groups: Map<string, {
        document: AggregatedInterventionRow['outcome_groups'][number]['document']
        results: AggregatedInterventionRow['results_summary']
      }>
      total_sample_size: number | null
      documents: Map<string, AggregatedInterventionRow['documents'][number]>
      evidence_scores: Array<{ score: number; justification?: string }>
      impact_justifications: Array<{ score: number; justification?: string }>
    }>()

    const getDisplayValue = (value?: string) => {
      if (!value) return null
      const trimmed = value.trim()
      return trimmed && trimmed !== 'Unknown' ? trimmed : null
    }

    let unknownDocumentCounter = 0

    detailedInterventions.forEach((detail) => {
      const name = detail.name?.trim()
      if (!name) return

      if (!aggregated.has(name)) {
        aggregated.set(name, {
          name,
          types: new Set(),
          countries: new Set(),
          description: '',
          evidence_categories: new Set(),
          has_sr: false,
          has_non_sr: false,
          result_count: 0,
          results_summary: [],
          outcome_groups: new Map(),
          total_sample_size: null,
          documents: new Map(),
          evidence_scores: [],
          impact_justifications: [],
        })
      }

      const entry = aggregated.get(name)!
      const typeValue = getDisplayValue(detail.type)
      if (typeValue) entry.types.add(typeValue)
      const countryValue = getDisplayValue(detail.country)
      if (countryValue) entry.countries.add(countryValue)

      if (detail.description) {
        if (!entry.description || detail.description.length > entry.description.length) {
          entry.description = detail.description
        }
      }

      if (detail.evidence_category) {
        entry.evidence_categories.add(detail.evidence_category)
        if (detail.evidence_category === 'Systematic Review and Meta-Analysis') {
          entry.has_sr = true
        } else {
          entry.has_non_sr = true
        }
      }

      const results = detail.results || []
      const sourceDoc = detail.source_documents?.[0]
      const docKey = sourceDoc?.doc_id
        || sourceDoc?.landing_page_url
        || sourceDoc?.title
        || `${name}-unknown-${unknownDocumentCounter++}`
      const parseSampleSize = (value: unknown) => {
        if (typeof value === 'number' && value > 0) return value
        if (typeof value === 'string') {
          const cleaned = value.replace(/,/g, '').trim()
          const parsed = Number(cleaned)
          if (!Number.isNaN(parsed) && parsed > 0) return parsed
        }
        return 0
      }

      const reportedSampleSize = Math.max(
        parseSampleSize(detail.sample_size),
        ...results.map(result => result.sample_size || 0)
      )
      const document = {
        doc_id: sourceDoc?.doc_id || '',
        title: sourceDoc?.title || 'Unknown',
        source: sourceDoc?.source || 'Unknown',
        landing_page_url: sourceDoc?.landing_page_url || detail.document_url,
        evidence_category: sourceDoc?.evidence_category,
        reported_sample_size: reportedSampleSize > 0 ? reportedSampleSize : undefined,
      }

      if (!entry.outcome_groups.has(docKey)) {
        entry.outcome_groups.set(docKey, { document, results: [] })
      }
      const outcomeGroup = entry.outcome_groups.get(docKey)!

      entry.result_count += results.length
      const mappedResults = results.map(result => mapResultToSummary(result, detail.evidence_category))
      entry.results_summary.push(...mappedResults)
      outcomeGroup.results.push(...mappedResults)

      const docSampleSize = parseSampleSize(sourceDoc?.sample_size)
      if (docSampleSize > 0) {
        entry.total_sample_size = entry.total_sample_size === null
          ? docSampleSize
          : Math.max(entry.total_sample_size, docSampleSize)
      }

      detail.source_documents?.forEach(doc => {
        const docId = doc.doc_id || ''
        if (!docId) return
        if (!entry.documents.has(docId)) {
          entry.documents.set(docId, {
            doc_id: docId,
            title: doc.title || 'Unknown',
            source: doc.source || 'Unknown',
            landing_page_url: doc.landing_page_url || detail.document_url,
          })
        }
      })

      if (typeof detail.impact_score === 'number') {
        entry.impact_justifications.push({
          score: detail.impact_score,
          justification: detail.impact_justification,
        })
      }

      if (typeof detail.evidence_score === 'number') {
        entry.evidence_scores.push({
          score: detail.evidence_score,
          justification: detail.evidence_justification,
        })
      }
    })

    return Array.from(aggregated.values()).map((entry) => {
      const evidenceCategories = Array.from(entry.evidence_categories).sort((a, b) => {
        const rankA = categoryRank.get(a) ?? 999
        const rankB = categoryRank.get(b) ?? 999
        return rankA - rankB
      })
      const primaryCategory = evidenceCategories[0]
      const isSystematicReview = entry.has_sr && !entry.has_non_sr

      const evidenceScoreEntry = entry.evidence_scores.reduce<{ score?: number; justification?: string }>(
        (best, current) => {
          if (best.score === undefined || current.score > best.score) {
            return { score: current.score, justification: current.justification }
          }
          return best
        },
        {}
      )

      const impactScoreEntry = entry.impact_justifications.reduce<{ score?: number; justification?: string }>(
        (best, current) => {
          if (best.score === undefined || current.score > best.score) {
            return { score: current.score, justification: current.justification }
          }
          return best
        },
        {}
      )

      return {
        name: entry.name,
        type: entry.types.size > 0 ? Array.from(entry.types).join(', ') : 'Unknown',
        country: entry.countries.size > 0 ? Array.from(entry.countries).join(', ') : 'Unknown',
        description: entry.description,
        evidence_category: primaryCategory,
        evidence_categories: evidenceCategories.length > 0 ? evidenceCategories : undefined,
        is_systematic_review: isSystematicReview,
        result_count: entry.result_count,
        results_summary: entry.results_summary,
        outcome_groups: Array.from(entry.outcome_groups.values()),
        total_sample_size: entry.total_sample_size,
        documents: Array.from(entry.documents.values()),
        impact_score: impactScoreEntry.score,
        evidence_score: evidenceScoreEntry.score,
        impact_justification: impactScoreEntry.justification,
        evidence_justification: evidenceScoreEntry.justification,
      }
    })
  }, [])
  
  // Convert fallback interventions to navigator format
  const convertFallbackToNavigatorFormat = useCallback((interventions: InterventionData[]) => {
    return interventions.map((intervention) => ({
      name: intervention.name,
      type: intervention.type,
      country: intervention.country,
      description: intervention.description,
      evidence_category: intervention.evidence_category,
      is_systematic_review: intervention.is_systematic_review,
      result_count: intervention.result_count,
      results_summary: intervention.results_summary,
      total_sample_size: intervention.total_sample_size,
      documents: intervention.documents,
      // These fields might not be present in fallback data, but include them if available
      impact_score: undefined,
      evidence_score: undefined,
      impact_justification: undefined,
      evidence_justification: undefined,
    }))
  }, [])

  // Render evidence mix summary from backend-provided evidence_mix
  const renderEvidenceMix = useCallback((evidenceMix: Record<string, number> | undefined) => {
    const mixText = formatEvidenceMixCompact(evidenceMix)
    if (!mixText) return null
    return (
      <p className="text-sm text-slate-600">
        <span className="font-semibold">Evidence Mix: </span>
        {mixText}
      </p>
    )
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
              loadingFallback ? (
                <div className="flex items-center justify-center py-12">
                  <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-slate-600">Loading extracted interventions...</p>
                  </div>
                </div>
              ) : fallbackInterventions && fallbackInterventions.length > 0 ? (
                <div className="space-y-4">
                  <Card>
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 text-sm text-slate-600 mb-2">
                        <AlertTriangle className="h-4 w-4 text-amber-500" />
                        <span>Synthesis pending - showing extracted interventions (ungrouped)</span>
                      </div>
                    </CardContent>
                  </Card>
                  <NavigatorInterventionsTable 
                    interventions={convertFallbackToNavigatorFormat(fallbackInterventions)} 
                  />
                </div>
              ) : (
                <Card>
                  <CardContent className="p-8 text-center">
                    <AlertTriangle className="h-12 w-12 text-amber-400 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-slate-900 mb-2">No Interventions Found</h3>
                    <p className="text-slate-600">
                      This happens when documents are still being processed.
                    </p>
                  </CardContent>
                </Card>
              )
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
                              {renderEvidenceMix(intervention.display_evidence_mix || intervention.evidence_mix)}
                            </div>
                          )}
                        </div>

                        <div className="flex items-start gap-4 ml-4">
                          <div className="text-right">
                            <div className="text-xs text-slate-500">Evidence:</div>
                            {intervention.stars !== undefined ? (
                              <Tooltip content={getEvidenceScoreExplanation(intervention.stars, intervention.display_evidence_mix || intervention.evidence_mix, intervention.cap_message)}>
                                <div className="flex items-center cursor-help">
                                  {renderStars(intervention.stars, false)}
                                </div>
                              </Tooltip>
                            ) : (
                              renderStars(undefined, false)
                            )}
                          </div>
                          <div className="text-right">
                            <div className="text-xs text-slate-500">Impact:</div>
                            {renderStars(intervention.avg_impact_score, true)}
                          </div>
                          <div className="text-right">
                            <div className="text-xs text-slate-500">Frequency:</div>
                            <div className="flex items-center gap-1 justify-end">
                              <span className="text-xs text-slate-600 text-right">{intervention.detailed_interventions?.length || 0}</span>
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
                        <div className="space-y-3">
                          {/* Detailed Interventions */}
                          {intervention.detailed_interventions?.length ? (
                            <div>
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
                        </div>
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
                                      {renderEvidenceMix(intervention.issue_display_evidence_mix || intervention.issue_evidence_mix)}
                                    </div>
                                  )}
                                </div>

                                <div className="flex items-start gap-4 ml-4">
                                  <div className="text-right">
                                    <div className="text-xs text-slate-500">Evidence:</div>
                                    {intervention.issue_stars !== undefined ? (
                                      <Tooltip content={getEvidenceScoreExplanation(intervention.issue_stars, intervention.issue_display_evidence_mix || intervention.issue_evidence_mix, intervention.issue_cap_message)}>
                                        <div className="flex items-center cursor-help">
                                          {renderStars(intervention.issue_stars, false)}
                                        </div>
                                      </Tooltip>
                                    ) : (
                                      renderStars(undefined, false)
                                    )}
                                  </div>
                                  <div className="text-right">
                                    <div className="text-xs text-slate-500">Impact:</div>
                                    {renderStars(intervention.avg_impact_score, true)}
                                  </div>
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
                                <div className="space-y-3">
                                  {/* Detailed Interventions */}
                                  {intervention.detailed_interventions?.length ? (
                                    <div>
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
                                </div>
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
