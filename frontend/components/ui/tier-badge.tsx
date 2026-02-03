import * as React from "react"
import { cn } from "@/lib/utils"

type TierLevel = 'N/A' | 'Very low' | 'Low' | 'Moderate' | 'High' | 'Very high'

export function scoreToTier(score: number | null | undefined): TierLevel {
  if (score == null) return 'N/A'
  const s = Math.max(1, Math.min(5, score))
  if (s < 1.5) return 'Very low'
  if (s < 2.5) return 'Low'
  if (s < 3.5) return 'Moderate'
  if (s < 4.5) return 'High'
  return 'Very high'
}

export function tierToIndex(tier: TierLevel): number {
  switch (tier) {
    case 'N/A': return 0
    case 'Very low': return 1
    case 'Low': return 2
    case 'Moderate': return 3
    case 'High': return 4
    case 'Very high': return 5
  }
}

const tierColors: Record<TierLevel, string> = {
  'N/A': 'bg-slate-100 text-slate-600',
  'Very high': 'bg-green-500 text-white',
  'High': 'bg-lime-400 text-gray-900',
  'Moderate': 'bg-amber-300 text-gray-900',
  'Low': 'bg-orange-300 text-gray-900',
  'Very low': 'bg-rose-400 text-white',
}

interface TierBadgeProps {
  score?: number | null
  tier?: TierLevel
  label?: string
  showLabel?: boolean
  className?: string
}

export function TierBadge({ 
  score, 
  tier: tierProp, 
  label, 
  showLabel = true,
  className 
}: TierBadgeProps) {
  const tier = tierProp ?? scoreToTier(score)
  
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      {showLabel && label && (
        <span className="text-xs text-gray-500">{label}:</span>
      )}
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
          tierColors[tier]
        )}
      >
        {tier}
      </span>
    </span>
  )
}

