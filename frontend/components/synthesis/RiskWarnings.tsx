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
    <div className="rounded border border-slate-200 bg-white p-3 space-y-3">
      <div className="text-sm font-medium text-slate-900">Risk Warnings</div>
      <div className="space-y-2">
        {sortedRisks.map((risk, idx) => (
          <div key={`${risk.theme_name}-${idx}`} className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm text-slate-800">{risk.theme_name}</div>
              {risk.summary_description && (
                <div className="text-xs text-slate-600 mt-1">{risk.summary_description}</div>
              )}
              <div className="text-xs text-slate-500 mt-1">
                Frequency: {risk.frequency}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
