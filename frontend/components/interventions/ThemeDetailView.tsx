'use client'

import React, { useMemo, useState } from 'react'
import { ArrowLeft, ChevronRight, ChevronDown, Globe, Users, Building2, DollarSign, UserCheck, Cog } from 'lucide-react'
import { TierBadge } from '@/components/ui/tier-badge'
import { Badge } from '@/components/ui/badge'
import { InterventionCard, type InterventionCardData } from './InterventionCard'
import { ImpactProfileCard } from '@/components/synthesis/ImpactProfileCard'
import { RiskWarnings } from '@/components/synthesis/RiskWarnings'
import type { OutcomeTheme, RiskTheme, TransferabilityBreakdown } from '@/types/search'
import { formatEvidenceMixCompact, getEvidenceScoreExplanation, getEvidenceCategoryRank } from '@/lib/evidenceCategories'

interface DetailedIntervention {
  name: string
  description?: string
  type?: string
  country?: string
  study_type?: string
  evidence_category?: string
  evidence_category_reasoning?: string
  sample_size?: number | string | null
  impact_score?: number
  evidence_score?: number
  impact_score_label?: string
  impact_score_breakdown?: Record<string, unknown> | null
  transferability_score?: number
  transferability_breakdown?: Record<string, unknown> | null
  impact_justification?: string
  evidence_justification?: string
  supporting_quote?: string
  results?: Array<{
    outcome_variable?: string
    effect_direction?: string
    effect_size?: string
    effect_size_type?: string
    p_value?: string
    uncertainty?: string
    result_text?: string
    supporting_quote?: string
    population_measured?: string
    subgroup_or_dose?: string
  }>
  source_documents?: Array<{
    doc_id?: string
    title?: string
    source?: string
    landing_page_url?: string
    evidence_category?: string
  }>
}

interface InterventionTheme {
  theme_name: string
  description?: string
  impact_summary?: string
  frequency: number
  avg_impact_score?: number
  avg_evidence_score?: number
  detailed_interventions?: DetailedIntervention[]
}

interface ThemeDetailViewProps {
  themeName: string
  themeDescription?: string
  avgImpactScore?: number
  avgEvidenceScore?: number
  interventions: InterventionTheme[]
  onBack: () => void
  impactSummary?: string
  outcomeThemes?: OutcomeTheme[]
  riskThemes?: RiskTheme[]
  transferabilityRating?: string | null
  transferabilityNote?: string | null
  transferabilityBreakdown?: TransferabilityBreakdown | null
  displayEvidenceMix?: Record<string, number>
  evidenceStars?: number
  capMessage?: string | null
  isPublic?: boolean
  projectId?: string
}

function convertToCardData(detail: DetailedIntervention): InterventionCardData {
  // Get evidence category from the intervention or from the first source document
  const evidenceCategory = detail.evidence_category || detail.source_documents?.[0]?.evidence_category

  return {
    name: detail.name,
    type: detail.type,
    country: detail.country,
    description: detail.description,
    study_type: detail.study_type,
    evidence_category: evidenceCategory,
    evidence_category_reasoning: detail.evidence_category_reasoning,
    sample_size: detail.sample_size,
    impact_score: detail.impact_score,
    evidence_score: detail.evidence_score,
    impact_score_label: detail.impact_score_label,
    impact_score_breakdown: detail.impact_score_breakdown,
    transferability_score: detail.transferability_score,
    transferability_breakdown: detail.transferability_breakdown,
    impact_justification: detail.impact_justification,
    supporting_quote: detail.supporting_quote,
    results_summary: detail.results?.map(r => ({
      outcome: r.outcome_variable || '',
      direction: r.effect_direction || '',
      effect_size: r.effect_size,
      effect_size_type: r.effect_size_type,
      p_value: r.p_value,
      uncertainty: r.uncertainty,
      result_text: r.result_text,
      supporting_quote: r.supporting_quote,
      population_measured: r.population_measured,
      subgroup_or_dose: r.subgroup_or_dose,
    })),
    documents: detail.source_documents?.map(d => ({
      doc_id: d.doc_id || '',
      title: d.title || '',
      source: d.source || '',
      landing_page_url: d.landing_page_url,
    })),
    population_measured: detail.results?.[0]?.population_measured,
  }
}

interface InterventionGroup {
  key: string
  title: string
  category?: string
  items: DetailedIntervention[]
  avgImpact: number | null
  avgEvidence: number | null
  bestEvidenceRank: number
}

const toLabel = (value?: string) =>
  value ? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''

const contextFitStyles: Record<string, string> = {
  'Excellent Fit': 'text-green-700 bg-green-50',
  'Good Fit': 'text-green-700 bg-green-50',
  'Moderate Fit': 'text-yellow-700 bg-yellow-50',
  'Limited Fit': 'text-orange-700 bg-orange-50',
  'Poor Fit': 'text-red-700 bg-red-50',
  'Unknown': 'text-slate-600 bg-slate-50',
}

const requirementsStyles: Record<string, string> = {
  'Low': 'text-green-700 bg-green-50',
  'Medium': 'text-yellow-700 bg-yellow-50',
  'High': 'text-red-700 bg-red-50',
  'Unknown': 'text-slate-600 bg-slate-50',
}

interface ContextFitSectionProps {
  breakdown?: TransferabilityBreakdown | null
  rating?: string | null
  note?: string | null
}

function ContextFitCard({ breakdown, rating, note }: ContextFitSectionProps) {
  if (!breakdown && !rating) return null

  const contextRating = breakdown?.context_fit_rating || rating || 'Unknown'

  const contextDimensions = [
    { key: 'inner_setting', label: 'Setting', icon: Building2 },
    { key: 'population', label: 'Population', icon: Users },
    { key: 'geography', label: 'Geography', icon: Globe },
  ] as const

  const hasAnyContextInfo = breakdown && contextDimensions.some(({ key }) => 
    breakdown?.[key] || breakdown?.notes?.[key]
  )

  if (!hasAnyContextInfo && !note) return null

  return (
    <section className="bg-white border border-gray-100 rounded-xl p-6 space-y-6">
      <div>
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-xl font-bold text-gray-900">Context fit</h3>
          <span className={`inline-flex items-center px-3 py-1 rounded-lg text-sm ${contextFitStyles[contextRating] || contextFitStyles.Unknown}`}>
            {contextRating}
          </span>
        </div>
        {note && (
          <p className="text-gray-700 leading-relaxed">{note}</p>
        )}
      </div>

      {breakdown && (
        <div className="space-y-4">
          {contextDimensions.map(({ key, label, icon: Icon }) => {
            const value = breakdown?.[key]
            const dimensionNote = breakdown?.notes?.[key]
            if (!value && !dimensionNote) return null
            
            return (
              <div key={key}>
                <div className="flex items-center gap-3 mb-2">
                  <Icon className="h-4 w-4 text-gray-500" />
                  <span className="font-medium text-gray-900">{label}</span>
                  {value && (
                    <Badge variant="outline" className="text-xs">
                      {toLabel(value)}
                    </Badge>
                  )}
                </div>
                {dimensionNote && (
                  <p className="text-gray-700 leading-relaxed ml-7">{dimensionNote}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function ImplementationCard({ breakdown }: { breakdown?: TransferabilityBreakdown | null }) {
  if (!breakdown) return null

  const requirementsRating = breakdown?.implementation_requirements_rating || 'Unknown'
  const hasAnyToleranceExceeded = Object.values(breakdown?.implementation_exceeds_tolerance || {}).some(Boolean)

  const implementationDimensions = [
    { key: 'cost', label: 'Cost', icon: DollarSign },
    { key: 'staffing', label: 'Staffing', icon: UserCheck },
    { key: 'implementation_complexity', label: 'Complexity', icon: Cog },
  ] as const

  const hasAnyImplementationInfo = implementationDimensions.some(({ key }) => 
    breakdown?.implementation_evidence?.[key] || breakdown?.notes?.[key]
  )

  if (!hasAnyImplementationInfo) return null

  return (
    <section className="bg-white border border-gray-100 rounded-xl p-6 space-y-6">
      <div>
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-xl font-bold text-gray-900">Implementation requirements</h3>
          <span className={`inline-flex items-center px-3 py-1 rounded-lg text-sm ${requirementsStyles[requirementsRating] || requirementsStyles.Unknown}`}>
            {requirementsRating}{hasAnyToleranceExceeded ? ' ⚠️' : ''}
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {implementationDimensions.map(({ key, label, icon: Icon }) => {
          const evidenceValue = breakdown?.implementation_evidence?.[key]
          const exceedsTolerance = breakdown?.implementation_exceeds_tolerance?.[key]
          const dimensionNote = breakdown?.notes?.[key]
          if (!evidenceValue && !dimensionNote) return null
          
          return (
            <div key={key}>
              <div className="flex items-center gap-3 mb-2">
                <Icon className={`h-4 w-4 ${exceedsTolerance ? 'text-red-500' : 'text-gray-500'}`} />
                <span className={`font-medium ${exceedsTolerance ? 'text-red-900' : 'text-gray-900'}`}>{label}</span>
                {evidenceValue && (
                  <Badge 
                    variant="outline" 
                    className={`text-xs ${exceedsTolerance ? 'border-red-200 text-red-700' : ''}`}
                  >
                    {toLabel(evidenceValue)}{exceedsTolerance ? ' ⚠️' : ''}
                  </Badge>
                )}
              </div>
              {dimensionNote && (
                <p className={`leading-relaxed ml-7 ${exceedsTolerance ? 'text-red-700' : 'text-gray-700'}`}>
                  {dimensionNote}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

export function ThemeDetailView({
  themeName,
  themeDescription,
  avgImpactScore,
  avgEvidenceScore,
  interventions,
  onBack,
  impactSummary,
  outcomeThemes,
  riskThemes,
  transferabilityRating,
  transferabilityNote,
  transferabilityBreakdown,
  displayEvidenceMix,
  evidenceStars,
  capMessage,
  isPublic,
  projectId,
}: ThemeDetailViewProps) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [showInsufficientOutcomes, setShowInsufficientOutcomes] = useState(false)
  
  const groups = useMemo(() => {
    const allDetailed: DetailedIntervention[] = []
    const seenKeys = new Set<string>()
    
    interventions.forEach(theme => {
      if (theme.detailed_interventions) {
        theme.detailed_interventions.forEach(detail => {
          const docId = detail.source_documents?.[0]?.doc_id || ''
          const docTitle = detail.source_documents?.[0]?.title || ''
          const uniqueKey = `${detail.name}||${docId}||${docTitle}`
          
          if (!seenKeys.has(uniqueKey)) {
            seenKeys.add(uniqueKey)
            allDetailed.push(detail)
          }
        })
      }
    })
    
    const groupMap = new Map<string, InterventionGroup>()
    
    for (const detail of allDetailed) {
      const key = detail.name || 'unknown'
      const existing = groupMap.get(key)
      
      if (existing) {
        existing.items.push(detail)
      } else {
        groupMap.set(key, {
          key,
          title: detail.name,
          category: detail.type,
          items: [detail],
          avgImpact: null,
          avgEvidence: null,
          bestEvidenceRank: 999,
        })
      }
    }
    
    const result = Array.from(groupMap.values()).map(g => {
      const impactScores = g.items.map(i => i.impact_score).filter((s): s is number => s != null)
      const evidenceScores = g.items.map(i => i.evidence_score).filter((s): s is number => s != null)
      
      // Get best (lowest rank = strongest) evidence category rank
      const evidenceCategoryRanks = g.items
        .map(i => {
          const category = i.evidence_category || i.source_documents?.[0]?.evidence_category
          return category ? getEvidenceCategoryRank(category) : 999
        })
        .filter((rank): rank is number => rank !== 999)
      
      const bestEvidenceRank = evidenceCategoryRanks.length > 0 
        ? Math.min(...evidenceCategoryRanks)
        : 999
      
      return {
        ...g,
        avgImpact: impactScores.length > 0 
          ? impactScores.reduce((a, b) => a + b, 0) / impactScores.length 
          : null,
        avgEvidence: evidenceScores.length > 0
          ? evidenceScores.reduce((a, b) => a + b, 0) / evidenceScores.length
          : null,
        bestEvidenceRank,
      }
    })
    
    result.sort((a, b) => {
      // Primary sort: by evidence score (descending - higher is better)
      const aEvidence = a.avgEvidence ?? 0
      const bEvidence = b.avgEvidence ?? 0
      if (aEvidence !== bEvidence) return bEvidence - aEvidence
      
      // Secondary sort: by evidence category rank (ascending - lower rank = stronger evidence)
      if (a.bestEvidenceRank !== b.bestEvidenceRank) {
        return a.bestEvidenceRank - b.bestEvidenceRank
      }
      
      // Tertiary sort: by number of items (descending)
      return b.items.length - a.items.length
    })
    
    return result
  }, [interventions])
  
  const toggleGroup = (key: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  // Split outcomes into primary and insufficient evidence
  const { primaryOutcomes, insufficientOutcomes } = useMemo(() => {
    if (!outcomeThemes) return { primaryOutcomes: [], insufficientOutcomes: [] }
    
    const sorted = [...outcomeThemes].sort(
      (a, b) => (b.positive_count + b.negative_count + b.null_count) -
                (a.positive_count + a.negative_count + a.null_count)
    )
    
    return {
      primaryOutcomes: sorted.filter(o => o.verdict_label !== 'insufficient_evidence'),
      insufficientOutcomes: sorted.filter(o => o.verdict_label === 'insufficient_evidence'),
    }
  }, [outcomeThemes])

  const evidenceMixText = formatEvidenceMixCompact(displayEvidenceMix)
  const evidenceExplanation = evidenceStars !== undefined 
    ? getEvidenceScoreExplanation(evidenceStars, displayEvidenceMix, capMessage)
    : undefined

  const hasImpactProfile = primaryOutcomes.length > 0
  const hasRisks = riskThemes && riskThemes.length > 0
  
  return (
    <div data-tutorial="theme-detail-view" className="space-y-6">
      {/* Back button */}
      <div className="pb-1">
        <button
          className="flex items-center gap-2 text-gray-500 hover:text-gray-900 transition-colors"
          onClick={onBack}
          type="button"
        >
          <ArrowLeft size={16} />
          <span className="text-sm font-medium">Back to all interventions</span>
        </button>
      </div>
      
      {/* Main card with title, description, and evidence base */}
      <section className="bg-white border border-gray-100 rounded-xl p-6 space-y-6">
        {/* Header with title */}
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-3">{themeName}</h2>
          {themeDescription && (
            <p className="text-gray-700 leading-relaxed">{themeDescription}</p>
          )}
        </div>

        {/* Impact overview with badge */}
        {impactSummary && (
          <div>
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-3">
              Impact 
              {avgImpactScore != null && (
                <TierBadge score={avgImpactScore} showLabel={false} />
              )}
            </h3>
            <p className="text-gray-700 leading-relaxed">{impactSummary}</p>
          </div>
        )}

        {/* Evidence Base with badge */}
        {evidenceMixText && (
          <div>
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-3">
              Evidence
              {avgEvidenceScore != null && (
                <TierBadge score={avgEvidenceScore} showLabel={false} />
              )}
            </h3>
            {evidenceExplanation && (
              <p className="text-gray-700 leading-relaxed">{evidenceExplanation}</p>
            )}
          </div>
        )}
      </section>

      {/* Section 3: Key Outcomes */}
      {hasImpactProfile && (
        <section className="bg-white border border-gray-100 rounded-xl p-6 space-y-4">
          <h3 className="text-xl font-bold text-gray-900">Key outcomes</h3>
          
          <div className="grid gap-3">
            {primaryOutcomes.map((outcome) => (
              <ImpactProfileCard
                key={outcome.outcome_name}
                outcome={outcome}
                isPublic={isPublic}
                projectId={projectId}
              />
            ))}
          </div>
          
          {insufficientOutcomes.length > 0 && (
            <div className="pt-2">
              <button
                type="button"
                className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900"
                onClick={() => setShowInsufficientOutcomes(!showInsufficientOutcomes)}
              >
                {showInsufficientOutcomes ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
                {showInsufficientOutcomes 
                  ? `Hide ${insufficientOutcomes.length} outcomes with insufficient evidence`
                  : `Show ${insufficientOutcomes.length} outcomes with insufficient evidence`
                }
              </button>
              
              {showInsufficientOutcomes && (
                <div className="grid gap-3 mt-3">
                  {insufficientOutcomes.map((outcome) => (
                    <ImpactProfileCard
                      key={outcome.outcome_name}
                      outcome={outcome}
                      isPublic={isPublic}
                      projectId={projectId}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Section 4: Context Fit */}
      <ContextFitCard 
        breakdown={transferabilityBreakdown}
        rating={transferabilityRating}
        note={transferabilityNote}
      />

      {/* Section 5: Implementation Requirements */}
      <ImplementationCard breakdown={transferabilityBreakdown} />

      {/* Section 6: Risk Warnings */}
      {hasRisks && (
        <section className="bg-white border border-gray-100 rounded-xl p-6 space-y-6">
          <h3 className="text-xl font-bold text-gray-900">Risk warnings</h3>
          <RiskWarnings risks={riskThemes!} />
        </section>
      )}

      {/* Section 7: Detailed Studies */}
      <section className="bg-white border border-gray-100 rounded-xl p-6 space-y-6">
        <div>
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            Studies & evidence ({groups.reduce((sum, g) => sum + g.items.length, 0)})
          </h3>
          <p className="text-gray-700 leading-relaxed">
            Individual studies and interventions that contribute to this theme.
          </p>
        </div>
        
        <div className="space-y-3">
          {groups.map(group => {
            const isMulti = group.items.length > 1
            const isExpanded = expandedGroups.has(group.key)
            
            if (!isMulti) {
              const item = group.items[0]
              return (
                <InterventionCard
                  key={group.key}
                  intervention={convertToCardData(item)}
                  studyCount={1}
                />
              )
            }
            
            return (
              <div 
                key={group.key} 
                className="bg-white border border-gray-100 rounded-xl overflow-hidden"
              >
                <div
                  className="p-5 hover:bg-gray-50 transition-colors cursor-pointer"
                  onClick={() => toggleGroup(group.key)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      toggleGroup(group.key)
                    }
                  }}
                >
                  <div className="flex justify-between items-start gap-4 mb-3">
                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                      <h3 className="text-base font-semibold text-gray-900">
                        {group.title}
                      </h3>
                      {group.category && group.category !== 'Unknown' && (
                        <Badge 
                          variant="outline" 
                          className="shrink-0 text-xs font-medium uppercase tracking-wide text-gray-500 bg-gray-50"
                        >
                          {group.category}
                        </Badge>
                      )}
                    </div>
                    
                    <div className="shrink-0 flex items-center gap-3">
                      {group.avgImpact != null && (
                        <TierBadge score={group.avgImpact} label="Impact" />
                      )}
                      {group.avgEvidence != null && (
                        <TierBadge score={group.avgEvidence} label="Evidence" />
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-1 text-blue-600 text-sm font-medium">
                    <span className="text-gray-400 mr-2">{group.items.length} studies</span>
                    {isExpanded ? 'Hide' : 'View'}
                    <ChevronRight 
                      size={16} 
                      className={`transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                    />
                  </div>
                </div>
                
                {isExpanded && (
                  <div className="px-5 pb-5 border-t border-gray-100">
                    <div className="pt-4 space-y-3">
                      {group.items.map((item, idx) => (
                        <InterventionCard
                          key={`${group.key}-${idx}`}
                          intervention={convertToCardData(item)}
                          studyCount={1}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          
          {groups.length === 0 && (
            <div className="bg-gray-50 border border-gray-100 rounded-xl p-8 text-center text-gray-500">
              No intervention details available for this theme.
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
