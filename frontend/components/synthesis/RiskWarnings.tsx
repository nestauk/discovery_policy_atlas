'use client'

import React from 'react'
import { Badge } from '@/components/ui/badge'
import type { RiskTheme } from '@/types/search'

interface RiskWarningsProps {
  risks: RiskTheme[]
}

export function RiskWarnings({ risks }: RiskWarningsProps) {
  if (!risks.length) {
    return null
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-3 space-y-3">
      <div className="text-sm font-medium text-slate-900">Risk Warnings</div>
      <div className="space-y-2">
        {risks.map((risk, idx) => (
          <div key={`${risk.theme_name}-${idx}`} className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm text-slate-800">{risk.theme_name}</div>
              {risk.summary_description && (
                <div className="text-xs text-slate-600 mt-1">{risk.summary_description}</div>
              )}
              <div className="text-xs text-slate-500 mt-1">
                Frequency: {risk.frequency}
                {risk.linked_intervention_theme_id ? ' · Linked to intervention' : ''}
              </div>
            </div>
            {risk.has_harm_warning && (
              <Badge variant="outline" className="text-xs bg-red-50 text-red-700 border-red-200">
                Harm warning
              </Badge>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
