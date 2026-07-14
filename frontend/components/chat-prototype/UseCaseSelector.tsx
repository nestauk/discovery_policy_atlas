'use client'

import { cn } from '@/lib/utils'
import { Compass, LayoutList, Search } from 'lucide-react'

export type UseCase = 'broad' | 'landscape' | 'detailed'

interface UseCaseSelectorProps {
  selected: UseCase | null
  onSelect: (useCase: UseCase) => void
  disabled?: boolean
}

const useCases: { id: UseCase; title: string; description: string; icon: typeof Compass }[] = [
  {
    id: 'broad',
    title: 'Get a sense of a broad or new policy area',
    description: 'Quick landscape overview with minimal questions',
    icon: Compass,
  },
  {
    id: 'landscape',
    title: 'Review the landscape of potential interventions',
    description: 'Intervention themes with evidence quality ratings',
    icon: LayoutList,
  },
  {
    id: 'detailed',
    title: 'Explore intervention evidence, implementation and risks',
    description: 'Full briefing with implementation details and policy blueprint',
    icon: Search,
  },
]

export function UseCaseSelector({ selected, onSelect, disabled }: UseCaseSelectorProps) {
  return (
    <div className="grid grid-cols-1 gap-3 w-full max-w-2xl mx-auto">
      {useCases.map((uc) => (
        <button
          key={uc.id}
          onClick={() => onSelect(uc.id)}
          disabled={disabled}
          className={cn(
            'flex items-start gap-4 p-4 rounded-xl border-2 text-left transition-all',
            'hover:border-blue-400 hover:bg-blue-50/50',
            selected === uc.id
              ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-200'
              : 'border-slate-200 bg-white',
            disabled && 'opacity-50 cursor-not-allowed hover:border-slate-200 hover:bg-white'
          )}
        >
          <div
            className={cn(
              'mt-0.5 flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center',
              selected === uc.id ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-500'
            )}
          >
            <uc.icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm text-slate-900">{uc.title}</p>
            <p className="text-xs text-slate-500 mt-0.5">{uc.description}</p>
          </div>
        </button>
      ))}
    </div>
  )
}
