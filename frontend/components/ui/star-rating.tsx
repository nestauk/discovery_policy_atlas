import React from 'react'
import { cn } from '@/lib/utils'
import { Tooltip } from '@/components/ui/tooltip'

interface StarRatingProps {
  stars: number | null | undefined
  maxStars?: number
  size?: 'sm' | 'md' | 'lg'
  className?: string
  tooltip?: string
}

export function StarRating({ 
  stars, 
  maxStars = 5, 
  size = 'sm', 
  className,
  tooltip
}: StarRatingProps) {
  if (stars == null) {
    const naDisplay = (
      <span className={cn(
        "text-slate-400",
        size === 'sm' && "text-xs",
        size === 'md' && "text-sm", 
        size === 'lg' && "text-base",
        className
      )}>
        N/A
      </span>
    )

    if (tooltip) {
      return (
        <Tooltip content={tooltip || "Insufficient evidence for assessment"}>
          {naDisplay}
        </Tooltip>
      )
    }

    return naDisplay
  }

  const ratingDisplay = (
    <span className={cn(
      "inline-block px-2 py-1 rounded text-center font-medium bg-blue-100 text-blue-800",
      size === 'sm' && "text-xs min-w-[2rem]",
      size === 'md' && "text-sm min-w-[2.5rem]",
      size === 'lg' && "text-base min-w-[3rem]",
      className
    )}>
      {stars}/{maxStars}
    </span>
  )

  if (tooltip) {
    return (
      <Tooltip content={tooltip}>
        {ratingDisplay}
      </Tooltip>
    )
  }

  return ratingDisplay
}