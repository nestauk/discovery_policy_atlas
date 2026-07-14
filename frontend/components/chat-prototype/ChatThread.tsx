'use client'

import { useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { SuggestionChips } from './SuggestionChips'
import {
  FiltersCard,
  type FilterValues,
  type FilterCardInitialValues,
  type FilterSection,
} from './FiltersCard'
import { ResearchPlanCard } from './ResearchPlanCard'
import { ProgressStepper, type PipelinePhase } from './ProgressStepper'
import { type PreviewDocument } from './DocumentPreviewCard'
import { PreviewDocumentsTable } from './PreviewDocumentsTable'
import { InternationalExampleCard } from './InternationalExampleCard'
import type { UseCase } from './UseCaseSelector'

// ---------------------------------------------------------------------------
// Message types
// ---------------------------------------------------------------------------

export interface TextMessage {
  type: 'text'
  id: string
  role: 'user' | 'assistant'
  content: string
  chips?: string[]
}

export interface FiltersMessage {
  type: 'filters'
  id: string
  title?: string
  description?: string
  confirmLabel?: string
  visibleSections?: FilterSection[]
  initialValues?: FilterCardInitialValues
}

export interface ResearchPlanMessage {
  type: 'research-plan'
  id: string
  data: {
    params: {
      research_question: string
      population: string[]
      inner_setting: string[]
      outcome: string[]
      sources: string[]
      time_preset: string
      geography: string[]
    }
    sourceCount: number
    academicCount: number
    greyCount: number
    showInternationalComparison?: boolean
  }
}

export interface InternationalExampleMessage {
  type: 'international-example'
  id: string
  data: {
    country: string
    title: string
    whyItStandsOut: string
    ukRelevance: string
    url?: string
  }
}

export interface DocumentPreviewMessage {
  type: 'document-preview'
  id: string
  documents: PreviewDocument[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  papers: any[]
  totalCount: number
}

export interface ProgressMessage {
  type: 'progress'
  id: string
  currentPhase: PipelinePhase
  completedPhases: PipelinePhase[]
}

export type ChatMessage =
  | TextMessage
  | FiltersMessage
  | ResearchPlanMessage
  | DocumentPreviewMessage
  | InternationalExampleMessage
  | ProgressMessage

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChatThreadProps {
  messages: ChatMessage[]
  isLoading: boolean
  loadingMessage?: string
  useCase: UseCase | null
  onChipSelect: (chip: string) => void
  onFiltersConfirm: (filters: FilterValues) => void
  onApproveResearchPlan: (selectedOutputs: string[]) => void
  onAdjustSearch: () => void
  onOpenResultsPage: () => void
  disabled?: boolean
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChatThread({
  messages,
  isLoading,
  loadingMessage,
  useCase,
  onChipSelect,
  onFiltersConfirm,
  onApproveResearchPlan,
  onAdjustSearch,
  onOpenResultsPage,
  disabled,
}: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="flex-1 overflow-auto px-4 py-6 space-y-4">
      {messages.map((msg, idx) => {
        const isLastAssistant =
          msg.type === 'text' &&
          msg.role === 'assistant' &&
          idx === messages.length - 1

        switch (msg.type) {
          case 'text':
            return (
              <div key={msg.id}>
                <div
                  className={cn(
                    'max-w-[85%] rounded-xl px-4 py-2.5 text-sm',
                    msg.role === 'user'
                      ? 'ml-auto bg-blue-600 text-white'
                      : 'bg-slate-50 text-slate-800 border border-slate-200'
                  )}
                >
                  {msg.role === 'assistant' ? (
                    <div className="prose prose-sm max-w-none prose-p:my-1 prose-li:my-0">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    msg.content
                  )}
                </div>
                {/* Show chips only on the last assistant message */}
                {isLastAssistant && msg.chips && msg.chips.length > 0 && !disabled && (
                  <SuggestionChips
                    chips={msg.chips}
                    onSelect={onChipSelect}
                    disabled={disabled}
                  />
                )}
              </div>
            )

          case 'filters':
            return (
              <div key={msg.id} className="w-full">
                <FiltersCard
                  title={msg.title}
                  description={msg.description}
                  confirmLabel={msg.confirmLabel}
                  visibleSections={msg.visibleSections}
                  initialValues={msg.initialValues}
                  onConfirm={onFiltersConfirm}
                  disabled={disabled}
                />
              </div>
            )

          case 'research-plan':
            return (
              <div key={msg.id} className="w-full">
                <ResearchPlanCard
                  useCase={useCase || 'landscape'}
                  params={msg.data.params}
                  sourceCount={msg.data.sourceCount}
                  academicCount={msg.data.academicCount}
                  greyCount={msg.data.greyCount}
                  showInternationalComparison={msg.data.showInternationalComparison}
                  onApprove={onApproveResearchPlan}
                  onAdjustSearch={onAdjustSearch}
                  disabled={disabled}
                />
              </div>
            )

          case 'document-preview':
            return (
              <div key={msg.id} className="w-full">
                <PreviewDocumentsTable
                  papers={msg.papers}
                  totalCount={msg.totalCount}
                  onOpenResultsPage={onOpenResultsPage}
                />
              </div>
            )

          case 'progress':
            return (
              <div key={msg.id} className="w-full">
                <ProgressStepper
                  currentPhase={msg.currentPhase}
                  completedPhases={msg.completedPhases}
                />
              </div>
            )

          case 'international-example':
            return (
              <div key={msg.id} className="w-full">
                <InternationalExampleCard
                  country={msg.data.country}
                  title={msg.data.title}
                  whyItStandsOut={msg.data.whyItStandsOut}
                  ukRelevance={msg.data.ukRelevance}
                  url={msg.data.url}
                />
              </div>
            )

          default:
            return null
        }
      })}

      {isLoading && (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-2 bg-slate-50 rounded-lg px-3 py-2 border border-slate-200 max-w-[85%]">
          <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
          {loadingMessage || 'Thinking...'}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
