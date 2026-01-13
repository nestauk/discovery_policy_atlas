'use client'

import React from 'react'
import { ChevronRight } from 'lucide-react'
import { TierBadge, scoreToTier, tierToIndex } from '@/components/ui/tier-badge'

export interface ThemeListItem {
  theme_name: string
  description?: string
  frequency: number
  avg_impact_score?: number | null
  avg_evidence_score?: number | null
  detailed_interventions?: unknown[]
}

interface ThemeListProps {
  themes: ThemeListItem[]
  onSelectTheme: (theme: ThemeListItem) => void
  sortBy?: 'impact' | 'evidence'
  minImpact?: number
  minEvidence?: number
}

export function ThemeList({ 
  themes, 
  onSelectTheme,
  sortBy = 'evidence',
  minImpact = 1,
  minEvidence = 1,
}: ThemeListProps) {
  const filteredAndSorted = React.useMemo(() => {
    const filtered = themes.filter(theme => {
      const impactTier = tierToIndex(scoreToTier(theme.avg_impact_score))
      const evidenceTier = tierToIndex(scoreToTier(theme.avg_evidence_score))
      return impactTier >= minImpact && evidenceTier >= minEvidence
    })
    
    filtered.sort((a, b) => {
      const aStudies = a.detailed_interventions?.length ?? a.frequency ?? 0
      const bStudies = b.detailed_interventions?.length ?? b.frequency ?? 0
      
      if (sortBy === 'impact') {
        const impactDiff = (b.avg_impact_score ?? 0) - (a.avg_impact_score ?? 0)
        if (impactDiff !== 0) return impactDiff
      } else {
        const evidenceDiff = (b.avg_evidence_score ?? 0) - (a.avg_evidence_score ?? 0)
        if (evidenceDiff !== 0) return evidenceDiff
      }
      
      return bStudies - aStudies
    })
    
    return filtered
  }, [themes, sortBy, minImpact, minEvidence])
  
  if (filteredAndSorted.length === 0) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl px-6 py-8 text-center text-gray-500">
        No themes match your filters. Try adjusting the minimum impact or evidence levels.
      </div>
    )
  }
  
  return (
    <div className="space-y-2">
      <div className="hidden md:grid grid-cols-12 gap-4 px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
        <div className="col-span-6">Theme</div>
        <div className="col-span-2">Impact</div>
        <div className="col-span-2">Evidence</div>
        <div className="col-span-2 text-center">Studies</div>
      </div>
      
      {filteredAndSorted.map(theme => (
        <div
          key={theme.theme_name}
          className="bg-white border border-gray-100 rounded-xl px-6 py-5 hover:bg-gray-50 hover:border-gray-200 transition-colors cursor-pointer"
          onClick={() => onSelectTheme(theme)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onSelectTheme(theme)
            }
          }}
        >
          <div className="grid grid-cols-12 gap-4 items-center">
            <div className="col-span-12 md:col-span-6">
              <h3 className="text-base font-semibold text-gray-900">
                {theme.theme_name}
              </h3>
            </div>
            
            <div className="col-span-4 md:col-span-2">
              <TierBadge score={theme.avg_impact_score} showLabel={false} />
            </div>
            
            <div className="col-span-4 md:col-span-2">
              <TierBadge score={theme.avg_evidence_score} showLabel={false} />
            </div>
            
            <div className="col-span-3 md:col-span-2 flex items-center justify-center gap-2">
              <span className="text-sm font-semibold text-gray-900">
                {theme.detailed_interventions?.length ?? theme.frequency ?? 0}
              </span>
              <ChevronRight size={18} className="text-gray-300" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

