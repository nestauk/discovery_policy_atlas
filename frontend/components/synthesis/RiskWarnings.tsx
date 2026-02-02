'use client'

import React from 'react'
import type { RiskTheme } from '@/types/search'

interface RiskWarningsProps {
  risks: RiskTheme[]
}

export function RiskWarnings({ risks }: RiskWarningsProps) {
  if (!risks.length) {
    return null
  }

  const sortedRisks = [...risks].sort((a, b) => (b.frequency || 0) - (a.frequency || 0))

  return (
    <div className="space-y-4">
      {sortedRisks.map((risk, idx) => (
        <div key={`${risk.theme_name}-${idx}`}>
          <div className="flex items-center gap-3 mb-2">
            <span className="font-medium text-gray-900">{risk.theme_name}</span>
            {risk.frequency && (
              <span className="text-sm text-gray-500">({risk.frequency} {risk.frequency === 1 ? 'source' : 'sources'})</span>
            )}
          </div>
          {risk.summary_description && (
            <p className="text-gray-700 leading-relaxed">{risk.summary_description}</p>
          )}
        </div>
      ))}
    </div>
  )
}
