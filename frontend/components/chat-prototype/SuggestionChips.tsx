'use client'

import { cn } from '@/lib/utils'

interface SuggestionChipsProps {
  chips: string[]
  onSelect: (chip: string) => void
  disabled?: boolean
}

export function SuggestionChips({ chips, onSelect, disabled }: SuggestionChipsProps) {
  if (!chips.length) return null

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {chips.map((chip) => (
        <button
          key={chip}
          onClick={() => onSelect(chip)}
          disabled={disabled}
          className={cn(
            'px-3 py-1.5 text-sm rounded-full border transition-colors',
            'bg-white border-slate-200 text-slate-700',
            'hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          {chip}
        </button>
      ))}
    </div>
  )
}
