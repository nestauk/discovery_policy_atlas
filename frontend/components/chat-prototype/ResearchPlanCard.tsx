'use client'

import { useState, useEffect, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { ClipboardList } from 'lucide-react'
import type { UseCase } from './UseCaseSelector'

export interface OutputSection {
  id: string
  label: string
  description: string
  minutes: number
}

const OUTPUT_SECTIONS: OutputSection[] = [
  { id: 'executive_summary', label: 'Executive summary', description: 'Policy area state, intervention landscape, remaining challenges', minutes: 15 },
  { id: 'interventions_glance', label: 'Interventions at a glance', description: 'Table with evidence quality + impact ratings', minutes: 5 },
  { id: 'international_comparison', label: 'International comparison for UK context', description: 'What the strongest non-UK evidence could mean for UK policymakers', minutes: 3 },
  { id: 'detailed_reviews', label: 'Detailed intervention reviews', description: 'Per-intervention: outcomes, implementation, risks, evidence base', minutes: 5 },
  { id: 'recommendations', label: 'Recommendations', description: 'Prioritised policy recommendations with implementation options', minutes: 3 },
  { id: 'success_factors', label: 'Key success factors', description: 'Critical enablers for effective implementation', minutes: 2 },
  { id: 'challenges_risks', label: 'Implementation challenges & risks', description: 'Barriers, feasibility risks, mitigations', minutes: 2 },
  { id: 'policy_blueprint', label: 'Policy blueprint', description: 'Actionable implementation roadmap with phased options', minutes: 5 },
]

const DEFAULT_SELECTIONS: Record<UseCase, string[]> = {
  broad: ['executive_summary'],
  landscape: ['executive_summary', 'interventions_glance'],
  detailed: ['executive_summary', 'interventions_glance', 'detailed_reviews', 'recommendations', 'success_factors', 'challenges_risks'],
}

const VISIBLE_SECTIONS_BY_USE_CASE: Record<UseCase, string[]> = {
  broad: ['executive_summary', 'interventions_glance', 'international_comparison'],
  landscape: ['executive_summary', 'interventions_glance', 'international_comparison', 'detailed_reviews', 'recommendations'],
  detailed: OUTPUT_SECTIONS.map((section) => section.id),
}

interface SearchParams {
  research_question: string
  population: string[]
  inner_setting: string[]
  outcome: string[]
  sources: string[]
  time_preset: string
  geography: string[]
}

interface ResearchPlanCardProps {
  useCase: UseCase
  params: SearchParams
  sourceCount: number
  academicCount: number
  greyCount: number
  showInternationalComparison?: boolean
  onApprove: (selectedOutputs: string[]) => void
  onAdjustSearch: () => void
  disabled?: boolean
}

export function ResearchPlanCard({
  useCase,
  params,
  sourceCount,
  academicCount,
  greyCount,
  showInternationalComparison = false,
  onApprove,
  onAdjustSearch,
  disabled,
}: ResearchPlanCardProps) {
  const visibleSectionIds = useMemo(
    () =>
      VISIBLE_SECTIONS_BY_USE_CASE[useCase].filter(
        (id) => showInternationalComparison || id !== 'international_comparison'
      ),
    [useCase, showInternationalComparison]
  )
  const visibleSections = useMemo(
    () => OUTPUT_SECTIONS.filter((section) => visibleSectionIds.includes(section.id)),
    [visibleSectionIds]
  )

  const [selectedOutputs, setSelectedOutputs] = useState<Set<string>>(
    new Set(DEFAULT_SELECTIONS[useCase].filter((id) => visibleSectionIds.includes(id)))
  )

  useEffect(() => {
    setSelectedOutputs(new Set(DEFAULT_SELECTIONS[useCase].filter((id) => visibleSectionIds.includes(id))))
  }, [useCase, visibleSectionIds])

  const toggleOutput = (id: string) => {
    setSelectedOutputs((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const totalMinutes = visibleSections
    .filter((s) => selectedOutputs.has(s.id))
    .reduce((sum, s) => sum + s.minutes, 0)

  return (
    <div className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-start gap-2">
        <ClipboardList className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">Choose what to generate next</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            I&apos;ve completed a first pass on <span className="font-medium text-slate-900">{params.research_question}</span> and found{' '}
            <span className="font-medium text-slate-900">{sourceCount}</span> relevant sources
            {academicCount > 0 && greyCount > 0 && (
              <span> ({academicCount} academic, {greyCount} grey literature)</span>
            )}.
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {useCase === 'broad'
              ? 'For this lighter-touch route, I’ve kept the menu focused on overview outputs. If this first pass surfaces something worth pursuing, you can still take it further from here with a deeper analysis.'
              : useCase === 'landscape'
                ? 'I’ve prioritised outputs that help compare and assess intervention options. If you want to adjust the search instead, do that before I start the longer run.'
                : 'Pick only the outputs you want from here. If you want to adjust the search instead, do that before I start the longer run.'}
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {visibleSections.map((section) => (
          <label
            key={section.id}
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 px-3 py-3 transition-colors hover:border-slate-300 hover:bg-slate-50"
          >
            <input
              type="checkbox"
              checked={selectedOutputs.has(section.id)}
              onChange={() => toggleOutput(section.id)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-slate-900">{section.label}</span>
                <span className="flex-shrink-0 text-xs text-slate-400">~{section.minutes} min</span>
              </div>
              <p className="mt-0.5 text-xs leading-5 text-slate-500">{section.description}</p>
            </div>
          </label>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <div>
          <p className="text-slate-500">Estimated total</p>
          <p className="text-xs text-slate-400">Documents table and methodology stay included.</p>
        </div>
        <span className="font-semibold text-slate-900">~{totalMinutes} min</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onAdjustSearch}
          disabled={disabled}
          className="rounded-full px-4"
        >
          Refine search
        </Button>
        <Button
          size="sm"
          onClick={() => onApprove(Array.from(selectedOutputs))}
          disabled={disabled}
          className="rounded-full px-4"
        >
          Confirm selected outputs
        </Button>
      </div>
    </div>
  )
}
