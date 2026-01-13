'use client'

import React, { useMemo, useState } from 'react'
import { ArrowLeft, ChevronRight } from 'lucide-react'
import { TierBadge } from '@/components/ui/tier-badge'
import { Badge } from '@/components/ui/badge'
import { InterventionCard, type InterventionCardData } from './InterventionCard'

interface DetailedIntervention {
  name: string
  description?: string
  type?: string
  country?: string
  study_type?: string
  sample_size?: number | string | null
  impact_score?: number
  evidence_score?: number
  impact_justification?: string
  evidence_justification?: string
  results?: Array<{
    outcome_variable?: string
    effect_direction?: string
    effect_size?: string
    p_value?: string
    uncertainty?: string
    result_text?: string
    population_measured?: string
    subgroup_or_dose?: string
  }>
  source_documents?: Array<{
    doc_id?: string
    title?: string
    source?: string
    landing_page_url?: string
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
}

function convertToCardData(detail: DetailedIntervention): InterventionCardData {
  return {
    name: detail.name,
    type: detail.type,
    country: detail.country,
    description: detail.description,
    study_type: detail.study_type,
    sample_size: detail.sample_size,
    impact_score: detail.impact_score,
    evidence_score: detail.evidence_score,
    results_summary: detail.results?.map(r => ({
      outcome: r.outcome_variable || '',
      direction: r.effect_direction || '',
      effect_size: r.effect_size,
      p_value: r.p_value,
      uncertainty: r.uncertainty,
      result_text: r.result_text,
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
}

export function ThemeDetailView({
  themeName,
  themeDescription,
  avgImpactScore,
  avgEvidenceScore,
  interventions,
  onBack,
}: ThemeDetailViewProps) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  
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
        })
      }
    }
    
    const result = Array.from(groupMap.values()).map(g => {
      const impactScores = g.items.map(i => i.impact_score).filter((s): s is number => s != null)
      const evidenceScores = g.items.map(i => i.evidence_score).filter((s): s is number => s != null)
      
      return {
        ...g,
        avgImpact: impactScores.length > 0 
          ? impactScores.reduce((a, b) => a + b, 0) / impactScores.length 
          : null,
        avgEvidence: evidenceScores.length > 0
          ? evidenceScores.reduce((a, b) => a + b, 0) / evidenceScores.length
          : null,
      }
    })
    
    result.sort((a, b) => {
      const aImpact = a.avgImpact ?? 0
      const bImpact = b.avgImpact ?? 0
      if (aImpact !== bImpact) return bImpact - aImpact
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
  
  return (
    <div className="space-y-6">
      <button
        className="flex items-center gap-2 text-gray-500 hover:text-gray-900 transition-colors"
        onClick={onBack}
        type="button"
      >
        <ArrowLeft size={16} />
        <span className="text-sm font-medium">Back to Themes</span>
      </button>
      
      <div className="pb-6 border-b border-gray-100">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">{themeName}</h2>
        <div className="flex items-center justify-between gap-6">
          {themeDescription && (
            <p className="text-gray-600 max-w-3xl">{themeDescription}</p>
          )}
          <div className="shrink-0 flex items-center gap-4">
            {avgImpactScore != null && (
              <TierBadge score={avgImpactScore} label="Impact" />
            )}
            {avgEvidenceScore != null && (
              <TierBadge score={avgEvidenceScore} label="Evidence" />
            )}
          </div>
        </div>
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
    </div>
  )
}

