'use client'

import { cn } from '@/lib/utils'
import { Check } from 'lucide-react'

export type PipelinePhase = 'searching' | 'analysing' | 'theming' | 'briefing'

interface ProgressStepperProps {
  currentPhase: PipelinePhase
  completedPhases: PipelinePhase[]
}

const phases: { id: PipelinePhase; label: string }[] = [
  { id: 'searching', label: 'Searching' },
  { id: 'analysing', label: 'Analysing' },
  { id: 'theming', label: 'Theming' },
  { id: 'briefing', label: 'Briefing' },
]

export function ProgressStepper({ currentPhase, completedPhases }: ProgressStepperProps) {
  return (
    <div className="flex items-center gap-1 py-3 px-4 bg-slate-50 rounded-lg border border-slate-200">
      {phases.map((phase, idx) => {
        const isCompleted = completedPhases.includes(phase.id)
        const isCurrent = currentPhase === phase.id
        return (
          <div key={phase.id} className="flex items-center">
            {idx > 0 && (
              <div
                className={cn(
                  'w-6 h-px mx-1',
                  isCompleted || isCurrent ? 'bg-blue-400' : 'bg-slate-300'
                )}
              />
            )}
            <div className="flex items-center gap-1.5">
              <div
                className={cn(
                  'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold',
                  isCompleted && 'bg-green-500 text-white',
                  isCurrent && 'bg-blue-500 text-white animate-pulse',
                  !isCompleted && !isCurrent && 'bg-slate-200 text-slate-400'
                )}
              >
                {isCompleted ? <Check className="w-3 h-3" /> : idx + 1}
              </div>
              <span
                className={cn(
                  'text-xs font-medium',
                  isCompleted && 'text-green-700',
                  isCurrent && 'text-blue-700',
                  !isCompleted && !isCurrent && 'text-slate-400'
                )}
              >
                {phase.label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
