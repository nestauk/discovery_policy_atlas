import React from 'react'
import { cn } from '@/lib/utils'
import { Tooltip } from '@/components/ui/tooltip'
import { Star } from 'lucide-react'

type DisplayMode = 'badge' | 'icons' | 'icons-with-number'

interface StarRatingProps {
  stars: number | null | undefined
  maxStars?: number
  size?: 'sm' | 'md' | 'lg'
  className?: string
  tooltip?: string
  /** Display mode: 'badge' for X/5 format, 'icons' for star icons only, 'icons-with-number' for both */
  mode?: DisplayMode
}

export function StarRating({
  stars,
  maxStars = 5,
  size = 'sm',
  className,
  tooltip,
  mode = 'badge'
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

  const iconSize = size === 'sm' ? 'h-3 w-3' : size === 'md' ? 'h-4 w-4' : 'h-5 w-5'

  // Star icons component
  const StarIcons = () => (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: maxStars }, (_, i) => (
        <Star
          key={i}
          className={cn(
            iconSize,
            i < stars
              ? "fill-amber-400 text-amber-400"
              : "fill-gray-200 text-gray-200"
          )}
        />
      ))}
    </span>
  )

  let ratingDisplay: React.ReactNode

  if (mode === 'icons') {
    ratingDisplay = (
      <span className={cn("inline-flex items-center", className)}>
        <StarIcons />
      </span>
    )
  } else if (mode === 'icons-with-number') {
    ratingDisplay = (
      <span className={cn(
        "inline-flex items-center gap-1.5",
        size === 'sm' && "text-xs",
        size === 'md' && "text-sm",
        size === 'lg' && "text-base",
        className
      )}>
        <StarIcons />
        <span className="text-gray-600 font-medium">{stars}/{maxStars}</span>
      </span>
    )
  } else {
    // Badge mode (original behavior)
    ratingDisplay = (
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
  }

  if (tooltip) {
    return (
      <Tooltip content={tooltip}>
        {ratingDisplay}
      </Tooltip>
    )
  }

  return ratingDisplay
}