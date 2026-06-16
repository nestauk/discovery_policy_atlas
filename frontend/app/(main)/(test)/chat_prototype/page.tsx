'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { useAPI } from '@/lib/api'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { Send, Loader2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UseCaseSelector, type UseCase } from '@/components/chat-prototype/UseCaseSelector'
import {
  ChatThread,
  type ChatMessage,
  type TextMessage,
} from '@/components/chat-prototype/ChatThread'
import { ProgressStepper, type PipelinePhase } from '@/components/chat-prototype/ProgressStepper'
import { FloatingChat, type FloatingMessage } from '@/components/chat-prototype/FloatingChat'
import { type FilterValues, type FilterSection } from '@/components/chat-prototype/FiltersCard'
import { type PreviewDocument } from '@/components/chat-prototype/DocumentPreviewCard'
import { ExecutiveBriefing } from '@/app/(main)/results/ExecutiveBriefing'
import { InterventionsNavigator } from '@/components/interventions/InterventionsNavigator'
import { PapersTable } from '@/components/documents/PapersTable'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExtractedParams {
  research_question: string
  population: string[]
  inner_setting: string[]
  outcome: string[]
  geography: string[]
  time_preset: string
  time_from?: string
  time_to?: string
  implementation_constraints?: {
    cost?: string
    staffing?: string
    implementation_complexity?: string
  } | null
  screening_factors: string[]
  sources: string[]
  max_results: number
}

interface ConversationEntry {
  role: 'user' | 'assistant'
  content: string
}

interface PreviewSummary {
  sourceCount: number
  academicCount: number
  greyCount: number
  showInternationalComparison?: boolean
}

interface InternationalComparisonSummary {
  country: string
  title: string
  abstract?: string
  whyItStandsOut: string
  ukRelevance: string
  resultsSummary: string
  url?: string
}

type Phase = 'chat' | 'running' | 'results'
type PendingAction = 'run_preview_search' | 'confirm_preview_sources' | 'run_full_analysis'

// ---------------------------------------------------------------------------
// Constants & Helpers
// ---------------------------------------------------------------------------

const DEFAULT_PARAMS: ExtractedParams = {
  research_question: '',
  population: [],
  inner_setting: [],
  outcome: [],
  geography: [],
  time_preset: 'LAST_10_YEARS',
  implementation_constraints: null,
  screening_factors: [],
  sources: ['openalex', 'overton'],
  max_results: 25,
}

const SESSION_KEY = 'chat-prototype-state'

interface PersistedState {
  phase: Phase
  useCase: UseCase | null
  messages: ChatMessage[]
  conversationHistory: ConversationEntry[]
  extractedParams: ExtractedParams
  projectId: string | null
  selectedOutputs: string[]
  summaryData: Record<string, unknown> | null
  documents: Record<string, unknown>[]
  resultsView: 'summary' | 'documents'
  previewSummary: PreviewSummary | null
  internationalComparison: InternationalComparisonSummary | null
  pendingAction: PendingAction | null
  pendingPreviewParams: ExtractedParams | null
  pendingOutputs: string[]
  pendingContextSummary: string | null
  msgCounter: number
}

function loadPersistedState(): PersistedState | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

let msgCounter = 0
function nextId() {
  return `msg-${++msgCounter}-${Date.now()}`
}

const TIME_PRESET_TO_DATES: Record<string, { from?: string; to?: string }> = {
  LAST_YEAR: { from: new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10) },
  LAST_2_YEARS: { from: new Date(Date.now() - 2 * 365 * 86400000).toISOString().slice(0, 10) },
  LAST_5_YEARS: { from: new Date(Date.now() - 5 * 365 * 86400000).toISOString().slice(0, 10) },
  LAST_10_YEARS: { from: new Date(Date.now() - 10 * 365 * 86400000).toISOString().slice(0, 10) },
  SINCE_2000: { from: '2000-01-01' },
  ANY: {},
}

const PRIMARY_CHIPS = new Set(['Start initial scan', 'These look right', 'Start full analysis'])
const SECONDARY_CHIPS = new Set(['Change scope', 'Refine search', 'Change outputs'])

const FILTER_CARD_TITLE = 'Recommended Search Scope'
const FILTER_CARD_DESCRIPTION =
  'These defaults give you a broad first pass. Adjust them if you want a narrower or wider scan before continuing.'
const FILTER_CARD_CONFIRM = 'Continue with this approach'
const OUTPUT_LABELS: Record<string, string> = {
  executive_summary: 'executive summary',
  interventions_glance: 'interventions at a glance',
  international_comparison: 'international comparison for UK context',
  detailed_reviews: 'detailed intervention reviews',
  recommendations: 'recommendations',
  success_factors: 'key success factors',
  challenges_risks: 'implementation challenges and risks',
  policy_blueprint: 'policy blueprint',
}

function formatList(items: string[]) {
  if (items.length === 0) return ''
  if (items.length === 1) return items[0]
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`
}

function buildIntentConfirmationMessage(params: ExtractedParams, useCase: UseCase) {
  const topic = params.research_question || 'this topic'
  const focusSuffix = getTopicFocusSuffix(params)

  const approachByUseCase: Record<UseCase, string> = {
    broad:
      'starting with a broad scan across academic and policy sources so we can identify the main themes quickly',
    landscape:
      'starting with a broad scan across academic and policy sources so we can map the main intervention approaches first',
    detailed:
      'starting with a broad scan across academic and policy sources so we can identify the main interventions before going deeper into implementation and risks',
  }

  return `I understand this as exploring **${topic}**${focusSuffix}.\n\nI recommend ${approachByUseCase[useCase]}. I’ve suggested a recommended search scope below, which you can adjust before continuing.`
}

function getTopicFocusSuffix(params: ExtractedParams) {
  const contextParts: string[] = []

  if (params.population.length > 0) {
    contextParts.push(`for ${formatList(params.population)}`)
  }
  if (params.inner_setting.length > 0) {
    contextParts.push(`in ${formatList(params.inner_setting)}`)
  }

  const focusTerms = [...params.outcome, ...params.screening_factors].filter(
    (item, index, list) => item && list.indexOf(item) === index
  )
  if (focusTerms.length > 0) {
    contextParts.push(`with a focus on ${formatList(focusTerms)}`)
  }

  if (params.implementation_constraints) {
    const constraints = [
      params.implementation_constraints.cost
        ? `cost tolerance: ${params.implementation_constraints.cost}`
        : null,
      params.implementation_constraints.staffing
        ? `staffing tolerance: ${params.implementation_constraints.staffing}`
        : null,
      params.implementation_constraints.implementation_complexity
        ? `complexity tolerance: ${params.implementation_constraints.implementation_complexity}`
        : null,
    ].filter(Boolean) as string[]

    if (constraints.length > 0) {
      contextParts.push(`taking into account ${formatList(constraints)}`)
    }
  }

  return contextParts.length > 0 ? `, ${contextParts.join(', ')}` : ''
}

function getSourceSummary(sources: string[]) {
  if (sources.includes('openalex') && sources.includes('overton')) {
    return 'academic and policy evidence'
  }
  if (sources.includes('openalex')) {
    return 'academic evidence'
  }
  return 'policy and grey literature'
}

const TIME_PRESET_DISPLAY: Record<string, string> = {
  LAST_YEAR: 'last year',
  LAST_2_YEARS: 'last 2 years',
  LAST_5_YEARS: 'last 5 years',
  LAST_10_YEARS: 'last 10 years',
  SINCE_2000: 'since 2000',
  ANY: 'any time period',
}

function getTimeSummary(filters: FilterValues) {
  if (filters.timePreset === 'CUSTOM') {
    const range =
      filters.customFrom || filters.customTo
        ? `from ${filters.customFrom || 'an earlier date'} to ${filters.customTo || 'now'}`
        : 'from a custom date range'
    return range
  }
  return `from the ${TIME_PRESET_DISPLAY[filters.timePreset] || 'selected time period'}`
}

function getGeographySummary(geography: string[]) {
  if (geography.includes('All')) {
    return 'without a geographic restriction'
  }

  return `with a focus on ${formatList(geography)}`
}

function buildExecutionMessage(params: ExtractedParams, filters: FilterValues, useCase: UseCase) {
  const topic = params.research_question || 'this topic'
  const topicFocus = getTopicFocusSuffix(params)
  const sourceSummary = getSourceSummary(filters.sources)
  const timeSummary = getTimeSummary(filters)
  const geographySummary = getGeographySummary(filters.geography)
  const breadthSummary = `screening up to ${filters.maxResults} sources per evidence type in this first pass`

  const outcomeByUseCase: Record<UseCase, string> = {
    broad: 'surface the main themes and the strongest starting points for further exploration',
    landscape: 'identify the main intervention themes first and then pull together the strongest supporting evidence',
    detailed: 'identify the main intervention themes first and then pull together the strongest evidence on implementation and risks',
  }

  return `I’ll start by scanning **${sourceSummary}** on **${topic}**${topicFocus} ${timeSummary}, ${geographySummary}, and ${breadthSummary}.\n\nFrom there I’ll ${outcomeByUseCase[useCase]}.`
}

function buildPreviewConfirmationMessage(params: ExtractedParams) {
  const topic = params.research_question || 'this topic'
  const topicFocus = getTopicFocusSuffix(params)
  return `If you want, I can run the initial scan on **${topic}**${topicFocus} now. If you have a question first or want to change the scope, say so before I continue.`
}

function buildOutputConfirmationMessage(outputs: string[]) {
  const selected = outputs.map((id) => OUTPUT_LABELS[id] || id.replaceAll('_', ' '))
  const summary = selected.length > 0 ? formatList(selected) : 'the selected outputs'
  return `I’m ready to generate **${summary}** next. If you want, I can start the full analysis now, or you can ask about any of these outputs before I continue.`
}

function buildAnalysisPlanSummary(params: ExtractedParams, outputs: string[]) {
  const sources = params.sources
    .map((source) => (source === 'openalex' ? 'academic literature' : 'policy and grey literature'))
    .join(' + ')
  const geography = params.geography.includes('All') || params.geography.length === 0
    ? 'any geography'
    : formatList(params.geography)
  const timeWindow = TIME_PRESET_DISPLAY[params.time_preset] || params.time_preset

  const selected = outputs.map((id) => OUTPUT_LABELS[id] || id.replaceAll('_', ' '))
  const outputSummary = selected.length > 0 ? formatList(selected) : 'the selected outputs'

  return `Here’s the plan I’ll follow if you want me to continue:\n\n- **Topic:** ${params.research_question}\n- **Evidence scope:** ${sources}, ${timeWindow}, ${geography}\n- **Outputs to generate:** ${outputSummary}\n- **Next:** gather the fuller evidence base, extract the intervention details, and draft the outputs you selected`
}

function buildAnalysisConfig(params: ExtractedParams, options: { abstractsOnly: boolean }) {
  const dates = TIME_PRESET_TO_DATES[params.time_preset] || {}
  return {
    query: params.research_question,
    search_context: {
      research_question: params.research_question,
      population: params.population,
      outcome: params.outcome,
      inner_setting: params.inner_setting,
      geography: params.geography.filter((g) => g !== 'All'),
      time_preset: params.time_preset,
      screening_factors: params.screening_factors,
      implementation_constraints: params.implementation_constraints || {},
      sources: params.sources,
      max_results: params.max_results,
    },
    sources: params.sources,
    date_from: params.time_from || dates.from,
    date_to: params.time_to || dates.to,
    limit: options.abstractsOnly
      ? params.max_results
      : params.max_results * params.sources.length,
    relevance_enabled: true,
    use_abstracts_only: options.abstractsOnly,
  }
}

function getFilterInitialValues(params: ExtractedParams) {
  return {
    sources: params.sources as ('openalex' | 'overton')[],
    maxResults: params.max_results,
    timePreset: params.time_preset as
      | 'LAST_YEAR'
      | 'LAST_2_YEARS'
      | 'LAST_5_YEARS'
      | 'LAST_10_YEARS'
      | 'SINCE_2000'
      | 'ANY'
      | 'CUSTOM',
    customFrom: params.time_from,
    customTo: params.time_to,
    geography: params.geography.length > 0 ? params.geography : ['All'],
  }
}

function getComparatorFocusTerms(params: ExtractedParams) {
  const stopWords = new Set([
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'about', 'your',
    'their', 'have', 'will', 'would', 'could', 'should', 'across', 'after', 'before',
    'policy', 'area', 'explore', 'exploring', 'intervention', 'interventions',
    'evidence', 'review', 'reviews', 'research', 'question', 'context', 'focus',
    'using', 'used', 'what', 'when', 'where', 'which', 'how', 'into', 'onto',
  ])

  const rawTerms = [
    params.research_question,
    ...params.population,
    ...params.inner_setting,
    ...params.outcome,
    ...params.screening_factors,
  ]
    .join(' ')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((term) => term.length > 2 && !stopWords.has(term))

  return rawTerms.filter((term, index) => rawTerms.indexOf(term) === index)
}

function extractInterestingAbstractLine(
  doc: Record<string, unknown>,
  focusTerms: string[]
) {
  const abstract = String(doc.abstract || '').replace(/\s+/g, ' ').trim()
  if (!abstract || abstract === 'No abstract available') {
    return null
  }

  const sentences = abstract
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= 60)

  if (sentences.length === 0) return null

  const priorityTerms = ['governance', 'risk', 'risks', 'safety', 'trust', 'trustworthy', 'explainable', 'implementation', 'barrier', 'barriers', 'adoption']
  const bestSentence = [...sentences]
    .map((sentence) => {
      const lower = sentence.toLowerCase()
      const focusMatches = focusTerms.filter((term) => lower.includes(term)).length
      const priorityMatches = priorityTerms.filter((term) => lower.includes(term)).length
      const startsWell = /^(this|the study|the review|findings|results|we found|authors)/i.test(sentence) ? 1 : 0
      return {
        sentence,
        score: focusMatches * 3 + priorityMatches * 4 + startsWell,
      }
    })
    .sort((a, b) => b.score - a.score)[0]

  if (!bestSentence || bestSentence.score <= 0) {
    return sentences[0]
  }

  return bestSentence.sentence
}

function buildInterestingComparatorText(
  doc: Record<string, unknown>,
  params: ExtractedParams,
  country: string
) {
  const focusTerms = getComparatorFocusTerms(params)
  const abstractLine = extractInterestingAbstractLine(doc, focusTerms)

  if (abstractLine) {
    const trimmed = abstractLine.length > 220 ? `${abstractLine.slice(0, 217)}...` : abstractLine
    return `The abstract highlights that ${trimmed}`
  }

  const topLine = String(doc.top_line || '').trim()
  if (topLine) {
    return topLine
  }

  const relevanceReason = String(doc.relevance_reason || '').trim()
  if (relevanceReason) {
    return relevanceReason
  }

  return `It emerged as one of the stronger non-UK sources in the first pass and offers a concrete comparator from ${country}.`
}

function getInternationalComparisonSummary(
  docs: Record<string, unknown>[],
  params: ExtractedParams
) : InternationalComparisonSummary | null {
  const getNonUkCountries = (value: unknown) => {
    const rawCountries = Array.isArray(value)
      ? value.map((item) => String(item))
      : String(value || '')
          .split(/[;,|]/)
          .map((item) => item.trim())
          .filter(Boolean)

    return rawCountries.filter(
      (country, index, list) =>
        country &&
        country !== 'UK' &&
        country !== 'United Kingdom' &&
        list.indexOf(country) === index
    )
  }

  const comparators = docs
    .map((doc) => {
      const countries = getNonUkCountries(doc.source_country)
      return { doc, countries }
    })
    .filter(({ countries }) => countries.length > 0)
    .sort((a, b) => {
      const rankA = Number(a.doc.evidence_category_rank) || 99
      const rankB = Number(b.doc.evidence_category_rank) || 99
      if (rankA !== rankB) return rankA - rankB
      if (a.countries.length !== b.countries.length) return a.countries.length - b.countries.length
      return (Number(b.doc.cited_by_count) || Number(b.doc.citation_count) || 0) - (Number(a.doc.cited_by_count) || Number(a.doc.citation_count) || 0)
    })

  const comparator = comparators[0]

  if (!comparator) return null

  const country = comparator.countries[0] || 'another country'
  const rawTitle = String(comparator.doc.title || 'Untitled source')
  const shortTitle = rawTitle.length > 100 ? `${rawTitle.slice(0, 97)}...` : rawTitle
  const whyItStandsOut = buildInterestingComparatorText(comparator.doc, params, country)
  const ukRelevant =
    params.geography.length === 0 ||
    params.geography.includes('All') ||
    params.geography.includes('UK') ||
    params.geography.includes('United Kingdom')

  return {
    country,
    title: shortTitle,
    abstract: String(comparator.doc.abstract || '').trim() || undefined,
    whyItStandsOut,
    ukRelevance: ukRelevant
      ? `For a UK policy context, this is interesting because it gives you a concrete international comparator to test against UK institutions, delivery constraints, and governance arrangements.`
      : `This is useful because it gives you a concrete international comparator to test alongside the rest of the evidence base.`,
    resultsSummary: ukRelevant
      ? `One of the strongest non-UK comparators in the scanned evidence came from ${country}: "${shortTitle}". For a UK audience, this is most useful as a transferability prompt: it may suggest an approach or delivery model worth testing against UK institutional constraints, rather than a directly transferable solution.`
      : `One of the strongest international comparators in the scanned evidence came from ${country}: "${shortTitle}". This is most useful as a comparison point alongside the rest of the evidence base, rather than a directly transferable solution.`,
    url: String(comparator.doc.landing_page_url || comparator.doc.doi || comparator.doc.overton_url || '') || undefined,
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChatPrototypePage() {
  // --- Restore persisted state ---
  const saved = useRef(loadPersistedState()).current

  // Restore msgCounter so IDs don't collide
  if (saved) msgCounter = saved.msgCounter

  // --- State ---
  const [phase, setPhase] = useState<Phase>(saved?.phase ?? 'chat')
  const [useCase, setUseCase] = useState<UseCase | null>(saved?.useCase ?? null)
  const [messages, setMessages] = useState<ChatMessage[]>(saved?.messages ?? [])
  const [conversationHistory, setConversationHistory] = useState<ConversationEntry[]>(saved?.conversationHistory ?? [])
  const [extractedParams, setExtractedParams] = useState<ExtractedParams>(saved?.extractedParams ?? DEFAULT_PARAMS)
  const [isLoading, setIsLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('Thinking...')
  const [inputValue, setInputValue] = useState('')
  const [projectId, setProjectId] = useState<string | null>(saved?.projectId ?? null)
  const [selectedOutputs, setSelectedOutputs] = useState<string[]>(saved?.selectedOutputs ?? [])

  // Pipeline progress
  const [currentPhase, setCurrentPhase] = useState<PipelinePhase>('searching')
  const [completedPhases, setCompletedPhases] = useState<PipelinePhase[]>([])

  // Results
  const [summaryData, setSummaryData] = useState<Record<string, unknown> | null>(saved?.summaryData ?? null)
  const [documents, setDocuments] = useState<Record<string, unknown>[]>(saved?.documents ?? [])
  const [resultsView, setResultsView] = useState<'summary' | 'documents'>(saved?.resultsView ?? 'summary')

  // Floating chat (Phase 3)
  const [floatingMessages, setFloatingMessages] = useState<FloatingMessage[]>([])
  const [floatingLoading, setFloatingLoading] = useState(false)
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(saved?.pendingAction ?? null)
  const [pendingPreviewParams, setPendingPreviewParams] = useState<ExtractedParams | null>(saved?.pendingPreviewParams ?? null)
  const [pendingOutputs, setPendingOutputs] = useState<string[]>(saved?.pendingOutputs ?? [])
  const [pendingContextSummary, setPendingContextSummary] = useState<string | null>(saved?.pendingContextSummary ?? null)
  const [previewSummary, setPreviewSummary] = useState<PreviewSummary | null>(saved?.previewSummary ?? null)
  const [internationalComparison, setInternationalComparison] = useState<InternationalComparisonSummary | null>(saved?.internationalComparison ?? null)

  const inputRef = useRef<HTMLInputElement>(null)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  const { fetchWithAuth, createAnalysisProject, runAnalysisForProject } = useAPI()
  const { setActiveProject } = useAnalysisProjectStore()

  const clearPendingAction = useCallback(() => {
    setPendingAction(null)
    setPendingPreviewParams(null)
    setPendingOutputs([])
    setPendingContextSummary(null)
  }, [])

  // --- Persist state to sessionStorage ---
  useEffect(() => {
    const state: PersistedState = {
      phase,
      useCase,
      messages,
      conversationHistory,
      extractedParams,
      projectId,
      selectedOutputs,
      summaryData,
      documents,
      resultsView,
      previewSummary,
      internationalComparison,
      pendingAction,
      pendingPreviewParams,
      pendingOutputs,
      pendingContextSummary,
      msgCounter,
    }
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(state))
    } catch {
      // sessionStorage full or unavailable — ignore
    }
  }, [
    phase, useCase, messages, conversationHistory, extractedParams,
    projectId, selectedOutputs, summaryData, documents, resultsView,
    previewSummary, internationalComparison, pendingAction,
    pendingPreviewParams, pendingOutputs, pendingContextSummary,
  ])

  const judgeInternationalComparison = useCallback(
    async (summary: InternationalComparisonSummary, params: ExtractedParams) => {
      try {
        const resp = await fetchWithAuth('api/chat-prototype/international-comparison', {
          method: 'POST',
          body: JSON.stringify({
            title: summary.title,
            abstract: summary.abstract || '',
            research_question: params.research_question,
            focus_terms: getComparatorFocusTerms(params),
            country: summary.country,
          }),
        })

        if (!resp) return summary

        const whyItStandsOut = (resp.why_interesting as string) || summary.whyItStandsOut
        const ukRelevance = (resp.uk_relevance as string) || summary.ukRelevance

        return {
          ...summary,
          whyItStandsOut,
          ukRelevance,
          resultsSummary: `${whyItStandsOut} ${ukRelevance}`,
        }
      } catch (err) {
        console.error('Failed to generate LLM international comparison summary:', err)
        return summary
      }
    },
    [fetchWithAuth]
  )

  const appendFilterMessage = useCallback(
    (
      visibleSections: FilterSection[],
      title: string,
      description: string,
      confirmLabel: string
    ) => {
      clearPendingAction()
      setMessages((prev) => [
        ...prev,
        {
          type: 'filters',
          id: nextId(),
          title,
          description,
          confirmLabel,
          visibleSections,
          initialValues: getFilterInitialValues(extractedParams),
        },
      ])
    },
    [clearPendingAction, extractedParams]
  )

  // --- Converse with backend ---
  const converse = useCallback(
    async (
      message: string,
      options?: {
        awaitingConfirmation?: boolean
        pendingAction?: PendingAction | null
        pendingContextSummary?: string | null
      }
    ) => {
      setLoadingMessage('Understanding your response and shaping the next step...')
      setIsLoading(true)
      try {
        const resp = await fetchWithAuth('api/chat-prototype/converse', {
          method: 'POST',
          body: JSON.stringify({
            message,
            conversation_history: conversationHistory,
            use_case: useCase || 'landscape',
            extracted_params: extractedParams,
            awaiting_confirmation: options?.awaitingConfirmation || false,
            pending_action: options?.pendingAction || undefined,
            pending_context_summary: options?.pendingContextSummary || undefined,
          }),
        })

        if (!resp) throw new Error('No response')

        const updatedParams = resp.extracted_params || extractedParams
        const assistantContent =
          resp.show_filters && (useCase || 'landscape')
            ? buildIntentConfirmationMessage(updatedParams, useCase || 'landscape')
            : resp.message

        // Update conversation history
        setConversationHistory((prev) => [
          ...prev,
          { role: 'user', content: message },
          { role: 'assistant', content: assistantContent },
        ])

        // Update extracted params
        if (resp.extracted_params) {
          setExtractedParams(resp.extracted_params)
        }

        // Add assistant message
        const assistantMsg: TextMessage = {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: assistantContent,
          chips: resp.show_filters ? [] : resp.chips || [],
        }
        setMessages((prev) => [...prev, assistantMsg])

        // Show filters card if ready
        if (resp.show_filters) {
          setMessages((prev) => [
            ...prev,
            {
              type: 'filters',
              id: nextId(),
              title: FILTER_CARD_TITLE,
              description: FILTER_CARD_DESCRIPTION,
              confirmLabel: FILTER_CARD_CONFIRM,
            },
          ])
        }

        if (options?.awaitingConfirmation && resp.requires_confirmation) {
          const chips =
            options.pendingAction === 'run_preview_search'
              ? ['Start initial scan', 'Change scope']
              : options.pendingAction === 'confirm_preview_sources'
                ? ['These look right', 'Refine search']
                : ['Start full analysis', 'Change outputs']

          setMessages((prev) => [
            ...prev.slice(0, -1),
            {
              ...assistantMsg,
              chips,
            },
          ])
        }

        // Ready for plan? Trigger preview search
        if (resp.ready_for_plan) {
          triggerPreviewSearch(resp.extracted_params || extractedParams)
        }

        if (options?.awaitingConfirmation && !resp.requires_confirmation) {
          clearPendingAction()
        }
      } catch (err) {
        console.error('Converse error:', err)
        setMessages((prev) => [
          ...prev,
          {
            type: 'text',
            id: nextId(),
            role: 'assistant',
            content: 'Sorry, something went wrong. Please try again.',
          },
        ])
      } finally {
        setIsLoading(false)
      }
    },
    [conversationHistory, useCase, extractedParams, fetchWithAuth, clearPendingAction]
  )

  // --- Send user message ---
  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim()) return

      const trimmed = text.trim()

      const userMsg: TextMessage = {
        type: 'text',
        id: nextId(),
        role: 'user',
        content: trimmed,
      }
      setMessages((prev) => [...prev, userMsg])
      setInputValue('')

      if (
        pendingAction &&
        /^(yes|yep|yeah|go ahead|proceed|continue|start|run it|do it|sounds good|ok|okay)$/i.test(trimmed)
      ) {
        await handleConfirmationPrimary()
        return
      }

      await converse(trimmed, pendingAction ? {
        awaitingConfirmation: true,
        pendingAction,
        pendingContextSummary,
      } : undefined)
    },
    [converse, pendingAction, pendingContextSummary]
  )

  // --- Handle chip selection ---
  const handleChipSelect = useCallback(
    (chip: string) => {
      if (PRIMARY_CHIPS.has(chip)) {
        void handleConfirmationPrimary()
        return
      }
      if (SECONDARY_CHIPS.has(chip)) {
        handleConfirmationSecondary()
        return
      }
      if (chip === 'Geography') {
        appendFilterMessage(
          ['geography'],
          'Refine geographic focus',
          'Adjust the geography only. Everything else in the current scope will stay the same.',
          'Apply geography change'
        )
        return
      }
      if (chip === 'Time window') {
        appendFilterMessage(
          ['time'],
          'Refine time window',
          'Adjust the evidence recency only. Everything else in the current scope will stay the same.',
          'Apply time window'
        )
        return
      }
      if (chip === 'Sources') {
        appendFilterMessage(
          ['sources', 'breadth'],
          'Refine evidence sources',
          'Adjust the source mix or how wide the first pass should be. The rest of the scope will stay the same.',
          'Apply source changes'
        )
        return
      }
      sendMessage(chip)
    },
    [sendMessage]
  )

  // --- Preview search ---
  const triggerPreviewSearch = useCallback(
    async (params: ExtractedParams) => {
      clearPendingAction()
      setLoadingMessage('Setting up your search plan...')
      setIsLoading(true)

      try {
        // Create project
        const project = await createAnalysisProject({
          title: params.research_question || 'Chat prototype project',
          query: params.research_question,
        })

        if (!project?.id) throw new Error('Failed to create project')

        const pid = project.id
        setProjectId(pid)
        setActiveProject(project)

        setLoadingMessage('Searching research and policy evidence for the most relevant sources...')

        await runAnalysisForProject(pid, buildAnalysisConfig(params, { abstractsOnly: true }))

        setLoadingMessage('Reviewing the most relevant sources and ranking the strongest studies...')

        // Poll for completion — the polling handles loading state from here
        pollProjectStatus(pid, 'preview')
      } catch (err) {
        console.error('Preview search error:', err)
        setIsLoading(false)
        setMessages((prev) => [
          ...prev,
          {
            type: 'text',
            id: nextId(),
            role: 'assistant',
            content: 'Sorry, the search failed. Please try adjusting your parameters.',
          },
        ])
      }
    },
    [createAnalysisProject, runAnalysisForProject, setActiveProject, clearPendingAction]
  )

  // --- Handle filters confirmation ---
  const handleFiltersConfirm = useCallback(
    async (filters: FilterValues) => {
      const updatedParams = {
        ...extractedParams,
        sources: filters.sources,
        max_results: filters.maxResults,
        time_preset: filters.timePreset,
        time_from: filters.customFrom,
        time_to: filters.customTo,
        geography: filters.geography,
      }
      setExtractedParams(updatedParams)

      const assistantMessage = buildExecutionMessage(updatedParams, filters, useCase || 'landscape')

      setConversationHistory((prev) => [
        ...prev,
        { role: 'user', content: `Confirmed search scope for ${updatedParams.research_question || 'this topic'}` },
        { role: 'assistant', content: assistantMessage },
      ])

      setMessages((prev) => [
        ...prev,
        {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: `${assistantMessage}\n\n${buildPreviewConfirmationMessage(updatedParams)}`,
          chips: ['Start initial scan', 'Change scope'],
        },
      ])
      setPendingAction('run_preview_search')
      setPendingPreviewParams(updatedParams)
      setPendingContextSummary(assistantMessage)
    },
    [extractedParams, useCase]
  )

  // --- Poll project status ---
  const pollProjectStatus = useCallback(
    (pid: string, mode: 'preview' | 'full') => {
      const poll = async () => {
        try {
          const resp = await fetchWithAuth(`api/analysis-projects/${pid}`)
          if (!resp) return

          // API returns { project: { status, ... } }
          const proj = resp.project || resp
          const status = proj.status

          if (mode === 'preview') {
            setLoadingMessage('Reviewing the most relevant sources and ranking the strongest studies...')
          } else if (mode === 'full') {
            // Update progress stepper based on status
            if (status === 'running') {
              setCurrentPhase('analysing')
              setCompletedPhases(['searching'])
              setLoadingMessage('Gathering full texts and extracting the key intervention details...')
            } else if (status === 'synthesising') {
              setCurrentPhase('theming')
              setCompletedPhases(['searching', 'analysing'])
              setLoadingMessage('Synthesising the evidence into intervention themes and a briefing...')
            }
          }

          if (status === 'completed' || status === 'failed') {
            if (pollingRef.current) {
              clearInterval(pollingRef.current)
              pollingRef.current = null
            }
            setIsLoading(false)

            if (status === 'failed') {
              setMessages((prev) => [
                ...prev,
                {
                  type: 'text',
                  id: nextId(),
                  role: 'assistant',
                  content: 'The analysis encountered an error. Please try again with different parameters.',
                },
              ])
              return
            }

            if (mode === 'preview') {
              // Fetch documents and show preview + research plan
              await showResearchPlan(pid)
            } else {
              // Full pipeline complete — transition to results
              setCompletedPhases(['searching', 'analysing', 'theming', 'briefing'])
              setMessages((prev) => [
                ...prev,
                {
                  type: 'text',
                  id: nextId(),
                  role: 'assistant',
                  content: 'Your analysis is ready! Switching to results view.',
                },
              ])

              // Load results
              await loadResults(pid)
              setPhase('results')
            }
          }
        } catch (err) {
          console.error('Polling error:', err)
        }
      }

      // Start polling interval (don't await — let it run in background)
      pollingRef.current = setInterval(poll, 3000)
      // Also do an immediate first check
      poll()
    },
    [fetchWithAuth]
  )

  // --- Show research plan ---
  const showResearchPlan = useCallback(
    async (pid: string) => {
      try {
        const docs = await fetchWithAuth(`api/analysis-projects/${pid}/documents`)
        if (!docs) return

        const docList = Array.isArray(docs) ? docs : docs.documents || []
        const relevantDocs = docList.filter((d: Record<string, unknown>) => d.is_relevant !== false)

        const academicCount = relevantDocs.filter((d: Record<string, unknown>) => d.source === 'openalex').length
        const greyCount = relevantDocs.filter((d: Record<string, unknown>) => d.source === 'overton').length

        // Map API field names to what PapersTable expects
        const mappedDocs = relevantDocs.map((d: Record<string, unknown>) => ({
          ...d,
          id: (d.id || d.doc_id) as string,
          publication_year: (d.year as number) || 0,
          cited_by_count: (d.cited_by_count as number) || (d.citation_count as number) || 0,
          authors: (d.authors as string[]) || [],
          doi: (d.doi as string) || '',
          is_relevant: d.is_relevant as boolean,
          confidence: d.relevance_confidence as number | undefined,
        }))

        // Sort by evidence category rank (lower = stronger) then citations
        const sortedDocs = [...mappedDocs].sort((a, b) => {
          const rankA = (a.evidence_category_rank as number) || 99
          const rankB = (b.evidence_category_rank as number) || 99
          if (rankA !== rankB) return rankA - rankB
          return (b.cited_by_count || 0) - (a.cited_by_count || 0)
        })

        // Top 5 for preview card and research plan
        const top5 = sortedDocs.slice(0, 5)

        const topDocs: PreviewDocument[] = top5.map((d) => ({
          id: d.id,
          title: (d.title as string) || 'Untitled',
          year: d.publication_year || undefined,
          source: d.source as string | undefined,
          evidence_category: d.evidence_category as string | undefined,
        }))

        const internationalComparisonCandidate = getInternationalComparisonSummary(
          relevantDocs,
          extractedParams
        )
        const internationalComparison = internationalComparisonCandidate
          ? await judgeInternationalComparison(internationalComparisonCandidate, extractedParams)
          : null

        // 1. Text message announcing the results
        const foundMsg: TextMessage = {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: `I found **${relevantDocs.length} relevant sources** (${academicCount} academic, ${greyCount} grey literature). Here are the strongest sources from the first pass, ranked by evidence category. This is a good point to review what turned up before deciding what to generate next.`,
        }

        // 2. Documents table showing top 5 (production PapersTable component)
        const previewMsg: ChatMessage = {
          type: 'document-preview',
          id: nextId(),
          documents: topDocs,
          papers: sortedDocs,
          totalCount: relevantDocs.length,
        }

        const internationalMsg: ChatMessage | null = internationalComparison
          ? {
              type: 'international-example',
              id: nextId(),
              data: {
                country: internationalComparison.country,
                title: internationalComparison.title,
                whyItStandsOut: internationalComparison.whyItStandsOut,
                ukRelevance: internationalComparison.ukRelevance,
                url: internationalComparison.url,
              },
            }
          : null

        const studiesCheckMsg: TextMessage = {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content:
            'Do these look like a good starting point? If so, I can help you choose which outputs to generate next. If not, we can refine the search first.',
          chips: ['These look right', 'Refine search'],
        }

        setPreviewSummary({
          sourceCount: relevantDocs.length,
          academicCount,
          greyCount,
          showInternationalComparison: Boolean(internationalComparison),
        })
        setInternationalComparison(internationalComparison)
        setPendingAction('confirm_preview_sources')
        setPendingContextSummary(foundMsg.content)

        setMessages((prev) => [
          ...prev,
          foundMsg,
          previewMsg,
          ...(internationalMsg ? [internationalMsg] : []),
          studiesCheckMsg,
        ])
      } catch (err) {
        console.error('Failed to load preview docs:', err)
      }
    },
    [fetchWithAuth, extractedParams, judgeInternationalComparison]
  )

  // --- Approve research plan ---
  const handleApproveResearchPlan = useCallback(
    async (outputs: string[]) => {
      setPendingAction('run_full_analysis')
      setPendingOutputs(outputs)
      setPendingContextSummary(buildOutputConfirmationMessage(outputs))
      setMessages((prev) => [
        ...prev,
        {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: `${buildAnalysisPlanSummary(extractedParams, outputs)}\n\nIf that plan looks right, I can start the full analysis now. If not, change the outputs or ask about the plan first.`,
          chips: ['Start full analysis', 'Change outputs'],
        },
      ])
    },
    [extractedParams]
  )

  const startFullAnalysis = useCallback(
    async (outputs: string[]) => {
      if (!projectId) return

      clearPendingAction()
      setSelectedOutputs(outputs)
      setPhase('running')
      setCurrentPhase('searching')
      setCompletedPhases([])

      setMessages((prev) => [
        ...prev,
        {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: 'I’m now moving from the initial scan into the full analysis you selected. This will take around 20 to 30 minutes, and I’ll keep you updated as the evidence is gathered and synthesised.',
        },
        {
          type: 'progress',
          id: nextId(),
          currentPhase: 'searching',
          completedPhases: [],
        },
      ])

      try {
        await runAnalysisForProject(projectId, buildAnalysisConfig(extractedParams, { abstractsOnly: false }))

        setTimeout(() => {
          setMessages((prev) => [
            ...prev,
            { type: 'text', id: nextId(), role: 'assistant', content: 'I’m gathering the full texts and pulling out the intervention and outcome details that matter most.' },
          ])
        }, 30000)

        setTimeout(() => {
          setMessages((prev) => [
            ...prev,
            { type: 'text', id: nextId(), role: 'assistant', content: 'I’m clustering the evidence into intervention themes and checking where the strongest support sits.' },
          ])
        }, 120000)

        await pollProjectStatus(projectId, 'full')
      } catch (err) {
        console.error('Full analysis error:', err)
        setMessages((prev) => [
          ...prev,
          { type: 'text', id: nextId(), role: 'assistant', content: 'Failed to start analysis. Please try again.' },
        ])
        setPhase('chat')
      }
    },
    [projectId, extractedParams, runAnalysisForProject, pollProjectStatus, clearPendingAction]
  )

  const handleConfirmationPrimary = useCallback(
    async () => {
      if (pendingAction === 'run_preview_search' && pendingPreviewParams) {
        await triggerPreviewSearch(pendingPreviewParams)
        return
      }

      if (pendingAction === 'confirm_preview_sources') {
        clearPendingAction()
        setMessages((prev) => [
          ...prev,
          {
            type: 'text',
            id: nextId(),
            role: 'assistant',
            content: 'Okay. Which outputs would you like me to generate from these studies?',
          },
          {
            type: 'research-plan',
            id: nextId(),
            data: {
              params: extractedParams,
              sourceCount: previewSummary?.sourceCount || 0,
              academicCount: previewSummary?.academicCount || 0,
              greyCount: previewSummary?.greyCount || 0,
              showInternationalComparison: previewSummary?.showInternationalComparison,
            },
          },
        ])
        return
      }

      if (pendingAction === 'run_full_analysis' && pendingOutputs.length > 0) {
        await startFullAnalysis(pendingOutputs)
      }
    },
    [pendingAction, pendingPreviewParams, pendingOutputs, triggerPreviewSearch, startFullAnalysis, clearPendingAction, extractedParams, previewSummary]
  )

  const handleConfirmationSecondary = useCallback(() => {
    clearPendingAction()

    if (pendingAction === 'run_preview_search' || pendingAction === 'confirm_preview_sources') {
      setMessages((prev) => [
        ...prev,
        {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: 'No problem. Which part of the search would you like to adjust?',
          chips: ['Geography', 'Time window', 'Sources'],
        },
      ])
      return
    }

    if (pendingAction === 'run_full_analysis') {
      setMessages((prev) => [
        ...prev,
        {
          type: 'text',
          id: nextId(),
          role: 'assistant',
          content: 'No problem. Update the output selection above, or ask me about any of the outputs before I start the full analysis.',
        },
      ])
    }
  }, [pendingAction, clearPendingAction])

  const handleOpenResultsPage = useCallback(() => {
    if (!projectId) return
    window.open(`/projects/${projectId}?tab=evidence&subtab=documents`, '_blank', 'noopener,noreferrer')
  }, [projectId])

  // --- Load results ---
  const loadResults = useCallback(
    async (pid: string) => {
      try {
        const [summary, docs] = await Promise.all([
          fetchWithAuth(`api/analysis-projects/${pid}/summary`),
          fetchWithAuth(`api/analysis-projects/${pid}/documents`),
        ])

        if (summary) setSummaryData(summary)
        if (docs) {
          const docList = Array.isArray(docs) ? docs : docs.documents || []
          setDocuments(docList)
        }
      } catch (err) {
        console.error('Failed to load results:', err)
      }
    },
    [fetchWithAuth]
  )

  // --- Adjust search (back to chat) ---
  const handleAdjustSearch = useCallback(() => {
    setMessages((prev) => [
      ...prev,
      {
        type: 'text',
        id: nextId(),
        role: 'assistant',
        content: 'No problem — what would you like to change? You can modify the population, setting, outcomes, or any of the search parameters.',
        chips: ['Change population', 'Change setting', 'Change outcomes', 'Broaden geography', 'Adjust time window'],
      },
    ])
  }, [])

  // --- Floating chat (RAG over results) ---
  const handleFloatingChatSend = useCallback(
    async (message: string) => {
      if (!projectId) return

      setFloatingMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'user', content: message },
      ])
      setFloatingLoading(true)

      try {
        const resp = await fetchWithAuth(`api/analysis-projects/${projectId}/chat`, {
          method: 'POST',
          body: JSON.stringify({
            message,
            recent_messages: floatingMessages.slice(-6),
          }),
        })

        if (resp) {
          setFloatingMessages((prev) => [
            ...prev,
            { id: nextId(), role: 'assistant', content: resp.message },
          ])
        }
      } catch (err) {
        console.error('Chat error:', err)
        setFloatingMessages((prev) => [
          ...prev,
          { id: nextId(), role: 'assistant', content: 'Sorry, I couldn\'t process that. Please try again.' },
        ])
      } finally {
        setFloatingLoading(false)
      }
    },
    [projectId, floatingMessages, fetchWithAuth]
  )

  // --- Reset ---
  const handleReset = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    setPhase('chat')
    setUseCase(null)
    setMessages([])
    setConversationHistory([])
    setExtractedParams({ ...DEFAULT_PARAMS })
    setInputValue('')
    setProjectId(null)
    setSelectedOutputs([])
    setSummaryData(null)
    setDocuments([])
    setFloatingMessages([])
    setPreviewSummary(null)
    setInternationalComparison(null)
    clearPendingAction()
    msgCounter = 0
    sessionStorage.removeItem(SESSION_KEY)
  }, [clearPendingAction])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  const internationalComparisonSummary = selectedOutputs.includes('international_comparison')
    ? internationalComparison
    : null

  // --- Render ---

  // Phase 3: Results
  if (phase === 'results') {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-1 overflow-auto">
          <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-slate-900">
                  {extractedParams.research_question || 'Analysis Results'}
                </h1>
                <p className="text-sm text-slate-500 mt-1">
                  {documents.length} sources analysed
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={handleReset} className="gap-2">
                <RotateCcw className="w-4 h-4" />
                Start again
              </Button>
            </div>

            {/* View tabs */}
            <div className="flex gap-2 border-b border-slate-200 pb-0">
              <button
                onClick={() => setResultsView('summary')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  resultsView === 'summary'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                Summary
              </button>
              <button
                onClick={() => setResultsView('documents')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  resultsView === 'documents'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                Documents ({documents.length})
              </button>
            </div>

            {/* Content */}
            {resultsView === 'summary' && (
              <div className="space-y-8">
                {/* AI Disclaimer */}
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
                  This analysis was generated by AI and should be reviewed critically. It is not a substitute for expert judgement.
                </div>

                {/* Executive summary */}
                {selectedOutputs.includes('executive_summary') && summaryData && (
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900 mb-4">Executive Summary</h2>
                    <ExecutiveBriefing
                      projectId={projectId || ''}
                      briefing={(summaryData as Record<string, unknown>).briefing as string || ''}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      structuredBriefing={(summaryData as any).structured_briefing}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      documents={documents as any}
                    />
                  </div>
                )}

                {selectedOutputs.includes('international_comparison') && internationalComparisonSummary && (
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900 mb-4">International Comparison for UK Context</h2>
                    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <p className="text-sm leading-7 text-slate-700">
                        {internationalComparisonSummary.resultsSummary}
                      </p>
                    </div>
                  </div>
                )}

                {/* Interventions */}
                {selectedOutputs.includes('interventions_glance') && projectId && (
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900 mb-4">Interventions at a Glance</h2>
                    <InterventionsNavigator showHeader={false} />
                  </div>
                )}
              </div>
            )}

            {resultsView === 'documents' && (
              <PapersTable
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                papers={documents as any}
                showAdditionalColumns={true}
                highlightNonRelevant={true}
              />
            )}
          </div>
        </div>

        {/* Floating chat */}
        <FloatingChat
          messages={floatingMessages}
          onSend={handleFloatingChatSend}
          isLoading={floatingLoading}
          contextLabel={extractedParams.research_question}
        />
      </div>
    )
  }

  // Phase 1 & 2: Chat
  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Progress stepper for Phase 2 */}
      {phase === 'running' && (
        <div className="px-4 py-2 border-b border-slate-200 bg-white">
          <div className="max-w-3xl mx-auto">
            <ProgressStepper currentPhase={currentPhase} completedPhases={completedPhases} />
          </div>
        </div>
      )}

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-h-0 max-w-3xl mx-auto w-full">
        {/* Use case selector (only when no messages) */}
        {messages.length === 0 && phase === 'chat' && (
          <div className="pt-12 pb-6 px-4 space-y-6">
            <div className="text-center space-y-2">
              <h1 className="text-2xl font-bold text-slate-900">What are you looking for?</h1>
              <p className="text-sm text-slate-500">
                Choose a starting point — you can always explore deeper later.
              </p>
              <p className="max-w-2xl mx-auto text-left text-sm text-slate-600">
                Policy Atlas is a powerful tool for policymakers that synthesises the
                global research landscape (OpenAlex) with the real-world policy
                footprint (Overton) to ensure your approach is grounded in evidence.
              </p>
            </div>
            <UseCaseSelector
              selected={useCase}
              onSelect={setUseCase}
              disabled={isLoading}
            />
          </div>
        )}

        {/* Chat thread */}
        {(messages.length > 0 || (useCase && phase === 'chat')) && (
          <ChatThread
            messages={messages}
            isLoading={isLoading}
            loadingMessage={loadingMessage}
            useCase={useCase}
            onChipSelect={handleChipSelect}
            onFiltersConfirm={handleFiltersConfirm}
            onApproveResearchPlan={handleApproveResearchPlan}
            onAdjustSearch={handleAdjustSearch}
            onOpenResultsPage={handleOpenResultsPage}
            disabled={isLoading || phase === 'running'}
          />
        )}

        {/* Input bar */}
        {phase === 'chat' && useCase && (
          <div className="px-4 py-4 border-t border-slate-200 bg-white">
            {messages.length === 0 && (
              <p className="mb-3 text-sm text-slate-600">
                Get started by typing a policy area or problem you are looking to
                explore. We will help you sharpen this into a specific question after
                you click submit.
              </p>
            )}
            {pendingAction && (
              <p className="mb-3 text-sm text-slate-600">
                Ask a question about the proposed next step, or tell me what you want
                to change before I continue.
              </p>
            )}
            <div className="flex gap-2">
              <input
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    sendMessage(inputValue)
                  }
                }}
                placeholder={
                  pendingAction
                    ? 'Ask a question or tell me what you want to change...'
                    : messages.length === 0
                    ? "E.g. I'm interested in reducing mental health waiting times in the NHS..."
                    : 'Type your response...'
                }
                className="flex-1 px-4 py-2.5 rounded-lg border border-slate-200 bg-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isLoading}
              />
              <Button
                onClick={() => sendMessage(inputValue)}
                disabled={isLoading || !inputValue.trim()}
                size="icon"
                className="flex-shrink-0"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
