'use client'

import React, { useState } from 'react'
import { ChevronRight, ChevronUp, ChevronDown } from 'lucide-react'
import { TierBadge, scoreToTier, tierToIndex } from '@/components/ui/tier-badge'

export interface ThemeListItem {
  theme_name: string
  description?: string
  frequency: number
  avg_impact_score?: number | null
  avg_evidence_score?: number | null
  detailed_interventions?: unknown[]
}

type SortColumn = 'theme' | 'impact' | 'evidence' | 'studies'
type SortDirection = 'asc' | 'desc'

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
  sortBy: initialSortBy = 'evidence',
  minImpact = 1,
  minEvidence = 1,
}: ThemeListProps) {
  const [sortColumn, setSortColumn] = useState<SortColumn>(
    initialSortBy === 'impact' ? 'impact' : 'evidence'
  )
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Toggle direction if clicking the same column
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      // Set new column, default to descending
      setSortColumn(column)
      setSortDirection('desc')
    }
  }

  const filteredAndSorted = React.useMemo(() => {
    const filtered = themes.filter(theme => {
      const impactTier = tierToIndex(scoreToTier(theme.avg_impact_score))
      const evidenceTier = tierToIndex(scoreToTier(theme.avg_evidence_score))
      return impactTier >= minImpact && evidenceTier >= minEvidence
    })
    
    filtered.sort((a, b) => {
      let comparison = 0
      
      switch (sortColumn) {
        case 'theme':
          comparison = a.theme_name.localeCompare(b.theme_name)
          break
        case 'impact':
          comparison = (b.avg_impact_score ?? 0) - (a.avg_impact_score ?? 0)
          break
        case 'evidence':
          comparison = (b.avg_evidence_score ?? 0) - (a.avg_evidence_score ?? 0)
          break
        case 'studies':
          const aStudies = a.detailed_interventions?.length ?? a.frequency ?? 0
          const bStudies = b.detailed_interventions?.length ?? b.frequency ?? 0
          comparison = bStudies - aStudies
          break
      }
      
      // Apply sort direction
      if (sortDirection === 'asc') {
        comparison = -comparison
      }
      
      return comparison
    })
    
    return filtered
  }, [themes, sortColumn, sortDirection, minImpact, minEvidence])
  
  if (filteredAndSorted.length === 0) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl px-6 py-8 text-center text-gray-500">
        No themes match your filters. Try adjusting the minimum impact or evidence levels.
      </div>
    )
  }
  
  const SortIcon = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) return null
    return sortDirection === 'asc' ? (
      <ChevronUp className="h-3 w-3 ml-1" />
    ) : (
      <ChevronDown className="h-3 w-3 ml-1" />
    )
  }

  return (
    <div data-tutorial="interventions-list" className="space-y-2">
      <div className="hidden md:grid grid-cols-12 gap-4 px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide border-b border-gray-100">
        <button
          onClick={() => handleSort('theme')}
          className="col-span-6 text-left flex items-center hover:text-gray-700 transition-colors cursor-pointer text-xs font-medium text-gray-500 uppercase tracking-wide"
        >
          THEME
          <SortIcon column="theme" />
        </button>
        <button
          onClick={() => handleSort('impact')}
          className="col-span-2 text-left flex items-center hover:text-gray-700 transition-colors cursor-pointer text-xs font-medium text-gray-500 uppercase tracking-wide"
        >
          IMPACT
          <SortIcon column="impact" />
        </button>
        <button
          onClick={() => handleSort('evidence')}
          className="col-span-2 text-left flex items-center hover:text-gray-700 transition-colors cursor-pointer text-xs font-medium text-gray-500 uppercase tracking-wide"
        >
          EVIDENCE
          <SortIcon column="evidence" />
        </button>
        <button
          onClick={() => handleSort('studies')}
          className="col-span-2 text-center flex items-center justify-center hover:text-gray-700 transition-colors cursor-pointer text-xs font-medium text-gray-500 uppercase tracking-wide"
        >
          STUDIES
          <SortIcon column="studies" />
        </button>
      </div>
      
      {filteredAndSorted.map(theme => (
        <div
          key={theme.theme_name}
          data-tutorial="intervention-theme-row"
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

