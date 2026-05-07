'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Bot, User, ExternalLink, Loader2, AlertCircle, CheckCircle2, Compass } from 'lucide-react'
import {
  useChatStore,
  chatStorageKey,
  AnswerMetadata,
  ChatMessage,
  ChatStep,
  ChatStreamEvent,
} from '@/lib/chatStore'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useUser } from '@clerk/nextjs'
import Image from 'next/image'
import { getEvidenceBadgeColors, buildEvidenceBadgeRegex } from '@/lib/evidenceCategories'

const SIMPLE_CITATION_RE = /\[(\d+)\]/g
const CHIP_LINE_RE = /\[chips:\s*((?:"[^"]*"(?:\s*\|\s*"[^"]*")*))\s*\]/g
const CHIP_VALUE_RE = /"([^"]*)"/g

// Evidence badge colours from the shared module (canonical + chatbot aliases)
const EVIDENCE_BADGE_COLORS = getEvidenceBadgeColors()
const EVIDENCE_BADGE_RE = buildEvidenceBadgeRegex(Object.keys(EVIDENCE_BADGE_COLORS))

function renderEvidenceBadges(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  EVIDENCE_BADGE_RE.lastIndex = 0
  while ((match = EVIDENCE_BADGE_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    const name = match[1]
    const count = match[2]
    const colors = EVIDENCE_BADGE_COLORS[name]
    parts.push(
      <span
        key={match.index}
        className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium leading-tight whitespace-nowrap"
        style={{ backgroundColor: colors.bg, color: colors.text }}
      >
        {name} ({count})
      </span>
    )
    lastIndex = EVIDENCE_BADGE_RE.lastIndex
  }

  if (parts.length === 0) return null
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  return <span className="inline-flex flex-wrap gap-1 items-center">{parts}</span>
}
const EMPTY_CHAT_MESSAGES: ChatMessage[] = []
const EMPTY_CHAT_STEPS: ChatStep[] = []

function parseChips(content: string): { cleanContent: string; chipGroups: string[][] } {
  const chipGroups: string[][] = []
  const cleanContent = content.replace(CHIP_LINE_RE, (match, inner: string) => {
    const values: string[] = []
    let m: RegExpExecArray | null
    CHIP_VALUE_RE.lastIndex = 0
    while ((m = CHIP_VALUE_RE.exec(inner)) !== null) {
      if (m[1]) values.push(m[1])
    }
    if (values.length > 0) chipGroups.push(values)
    return ''
  }).trimEnd()
  return { cleanContent, chipGroups }
}

// Server-side `_compact_cited_references` rewrites all citations to `[N]`
// form, where N is 1-indexed into the references list. We only need to wrap
// each [N] in a markdown link if the referenced source has a URL.
function processInTextCitations(content: string, references: { url?: string }[]): string {
  return content.replace(SIMPLE_CITATION_RE, (match, numStr: string) => {
    const number = parseInt(numStr, 10)
    const ref = references[number - 1]
    return ref?.url ? `[[${number}]](${ref.url})` : match
  })
}

function upsertStep(existingSteps: ChatStep[] | undefined, nextStep: ChatStep): ChatStep[] {
  const steps = existingSteps ?? []
  const existingIndex = steps.findIndex((step) => step.id === nextStep.id)

  if (existingIndex === -1) {
    return [...steps, nextStep]
  }

  return steps.map((step, index) => (
    index === existingIndex ? nextStep : step
  ))
}

function getCurrentStep(steps: ChatStep[] | undefined): ChatStep | undefined {
  const availableSteps = steps ?? EMPTY_CHAT_STEPS

  for (let index = availableSteps.length - 1; index >= 0; index -= 1) {
    const step = availableSteps[index]
    if (step.status === 'running' || step.status === 'pending') {
      return step
    }
  }

  return undefined
}

function extractText(node: React.ReactNode): string {
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    const el = node as React.ReactElement<{ children?: React.ReactNode }>
    return extractText(el.props.children)
  }
  return ''
}

function formatAuthors(authors: string[] | string | undefined): string {
  if (!authors) return ''
  let authorText = Array.isArray(authors) ? authors.join(', ') : String(authors)
  authorText = authorText
    .replace(/[\[\]'"]/g, '')
    .replace(/,\s*,/g, ',')
    .replace(/^\s*,|,\s*$/g, '')
    .trim()
  if (authorText.length <= 60) return authorText
  const truncated = authorText.substring(0, 50)
  const lastComma = truncated.lastIndexOf(', ')
  if (lastComma > 20) {
    return truncated.substring(0, lastComma) + ' et al.'
  }
  return truncated + '...'
}

function formatAnswerMetadata(metadata: AnswerMetadata): string {
  const parts: string[] = []
  if (metadata.evidence_source_count > 0) {
    parts.push(`${metadata.evidence_source_count} evidence source${metadata.evidence_source_count !== 1 ? 's' : ''}`)
  }
  if (metadata.parliament_source_count > 0) {
    parts.push(`${metadata.parliament_source_count} parliamentary record${metadata.parliament_source_count !== 1 ? 's' : ''}`)
  }
  if (parts.length === 0 && metadata.source_count > 0) {
    parts.push(`${metadata.source_count} source${metadata.source_count !== 1 ? 's' : ''}`)
  }
  let result = parts.join(', ')
  if (metadata.date_range) {
    result += ` | Evidence from ${metadata.date_range}`
  }
  return result
}

const FOLLOW_UP_HEADING_RE = /\*\*Follow-up questions:?\*\*\s*/i
const FOLLOW_UP_ITEM_RE = /^[-*]\s+(.+)/gm

function extractFollowUpQuestions(content: string): string[] {
  const headingMatch = content.match(FOLLOW_UP_HEADING_RE)
  if (!headingMatch || headingMatch.index === undefined) return []

  const afterHeading = content.slice(headingMatch.index + headingMatch[0].length)
  const questions: string[] = []
  let match: RegExpExecArray | null
  while ((match = FOLLOW_UP_ITEM_RE.exec(afterHeading)) !== null) {
    const q = match[1].trim()
    if (q) questions.push(q)
  }
  return questions
}

interface ActivityCardProps {
  message: ChatMessage
  isExpanded: boolean
  onToggleExpand: () => void
}

function ActivityCard({ message, isExpanded, onToggleExpand }: ActivityCardProps) {
  const hasActivity = Boolean(
    message.isStreaming ||
    message.error ||
    message.activitySummary ||
    (message.steps && message.steps.length > 0)
  )
  if (!hasActivity) return null

  const shouldShowSteps = Boolean(
    message.steps &&
    message.steps.length > 0 &&
    (message.isStreaming || isExpanded)
  )

  return (
    <div className={`mb-3 rounded-md border px-3 py-2 ${
      message.error
        ? 'border-red-200 bg-red-50'
        : 'border-gray-200 bg-white/70'
    }`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-medium text-gray-700">
          {message.error ? (
            <AlertCircle className="h-3.5 w-3.5 text-red-600" />
          ) : message.isStreaming ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
          )}
          <span>{getActivityHeader(message)}</span>
          {!message.isStreaming && !message.error && message.answerMetadata && (
            <span className="text-gray-500 font-normal">
              — {formatAnswerMetadata(message.answerMetadata)}
            </span>
          )}
        </div>

        {!message.isStreaming && message.steps && message.steps.length > 0 && (
          <button
            type="button"
            onClick={onToggleExpand}
            className="text-xs font-medium text-gray-700 hover:text-gray-900"
          >
            {isExpanded ? 'Hide workings' : 'Show workings'}
          </button>
        )}
      </div>

      {shouldShowSteps && message.steps && (
        <div className="mt-2 border-t border-gray-200 pt-2 space-y-1.5">
          {message.steps.map((step) => (
            <div key={step.id} className="flex items-start gap-2 text-xs text-gray-600">
              <span
                className={`mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full ${
                  step.status === 'failed'
                    ? 'bg-red-500'
                    : step.status === 'running'
                      ? 'bg-blue-500'
                      : 'bg-gray-400'
                }`}
              />
              <div className="min-w-0">
                <span className={step.status === 'running' ? 'font-medium text-gray-800' : ''}>
                  {step.label}
                </span>
                {step.summary && !message.isStreaming && (
                  <span className="text-gray-500">: {step.summary}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function getActivityHeader(message: ChatMessage): string {
  if (message.error) {
    return message.error
  }

  if (message.isStreaming) {
    return getCurrentStep(message.steps)?.label ?? 'Working'
  }

  return message.activitySummary ?? 'Workings available'
}

function markStreamingMessageFailed(message: ChatMessage, error: string): ChatMessage {
  return {
    ...message,
    isStreaming: false,
    activitySummary: 'Chat failed',
    error,
  }
}

function toPersistedAssistantMessage(message: ChatMessage): ChatMessage {
  return {
    id: message.id,
    role: 'assistant',
    content: message.content,
    timestamp: message.timestamp,
    references: message.references,
    steps: message.steps,
    activitySummary: message.activitySummary,
    answerMetadata: message.answerMetadata,
    responseId: message.responseId,
  }
}

function applyChatStreamEvent(message: ChatMessage, event: ChatStreamEvent): ChatMessage {
  if (event.type === 'message.completed') {
    return {
      ...message,
      content: event.message ?? message.content,
      references: event.references ?? message.references,
      isStreaming: false,
      activitySummary: event.activity_summary ?? message.activitySummary,
      answerMetadata: event.answer_metadata ?? message.answerMetadata,
      responseId: event.response_id ?? message.responseId,
      error: undefined,
    }
  }

  if (event.type === 'message.delta') {
    return {
      ...message,
      content: message.content + (event.message ?? ''),
    }
  }

  if (event.type === 'message.failed') {
    return markStreamingMessageFailed(
      message,
      event.error ?? 'Chat request failed. Please try again.'
    )
  }

  if (!event.step) {
    return message
  }

  return {
    ...message,
    steps: upsertStep(message.steps, event.step),
    activitySummary: message.activitySummary,
    error: undefined,
  }
}

async function consumeChatStream(
  response: Response,
  onEvent: (event: ChatStreamEvent) => void
) {
  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Streaming response body is unavailable')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })

    let newlineIndex = buffer.indexOf('\n')
    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim()
      buffer = buffer.slice(newlineIndex + 1)

      if (line) {
        onEvent(JSON.parse(line) as ChatStreamEvent)
      }

      newlineIndex = buffer.indexOf('\n')
    }
  }

  const trailing = buffer.trim()
  if (trailing) {
    onEvent(JSON.parse(trailing) as ChatStreamEvent)
  }
}

interface ChatInterfaceProps {
  className?: string
  placeholder?: string
  autoFocus?: boolean
  showHeader?: boolean
}

export function ChatInterface({
  className = "",
  placeholder = "Ask about the evidence in this project...",
  autoFocus = false,
  showHeader = false
}: ChatInterfaceProps) {
  const {
    getMessages,
    isLoading,
    error,
    addMessage,
    setLoading,
    setError,
    clearError,
    chatLaunchIntent,
    consumeChatLaunchIntent,
    startNewConversation,
    activeMode,
  } = useChatStore()

  const { activeProject } = useAnalysisProjectStore()
  const { user } = useUser()
  const [inputMessage, setInputMessage] = useState('')
  const [activeContextHint, setActiveContextHint] = useState<{ sectionTitle: string; contextHint: string } | null>(null)
  const [transientAssistantMessage, setTransientAssistantMessage] = useState<ChatMessage | null>(null)
  const [expandedActivityIds, setExpandedActivityIds] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const hasScrolledInitially = useRef(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const { fetchWithAuth } = useAPI()
  const activeProjectId = activeProject?.id ?? null
  const chatKey = activeProjectId ? chatStorageKey(activeProjectId, activeMode) : null
  const messages = chatKey ? getMessages(chatKey) : EMPTY_CHAT_MESSAGES
  const displayMessages = (
    transientAssistantMessage &&
    !messages.some((message) => message.id === transientAssistantMessage.id)
  )
    ? [...messages, transientAssistantMessage]
    : messages

  // Scroll to bottom: instantly on first mount, smoothly on subsequent updates
  useEffect(() => {
    if (!hasScrolledInitially.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' })
      hasScrolledInitially.current = true
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, transientAssistantMessage])

  // Auto-focus input if requested
  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus()
    }
  }, [autoFocus])

  useEffect(() => {
    setTransientAssistantMessage(null)
    setExpandedActivityIds([])
  }, [chatKey])

  // Consume chat launch intent: prefill input and set context
  useEffect(() => {
    if (!chatLaunchIntent) return

    consumeChatLaunchIntent(chatLaunchIntent.intentId)

    // Forecast mode: always start a fresh conversation
    if (chatLaunchIntent.mode === 'forecast' && chatKey) {
      startNewConversation(chatKey)
    }

    setActiveContextHint({
      sectionTitle: chatLaunchIntent.sectionTitle,
      contextHint: chatLaunchIntent.contextHint,
    })

    // Only prefill if input is empty (don't overwrite user's draft)
    if (chatLaunchIntent.prefillQuestion && !inputMessage.trim()) {
      setInputMessage(chatLaunchIntent.prefillQuestion)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatLaunchIntent?.intentId])


  const handleChipClick = useCallback((chipText: string) => {
    setInputMessage(chipText)
    inputRef.current?.focus()
  }, [])

  // Forecast context card: build context summary from search_query
  const forecastContext = useMemo(() => {
    const sq = activeProject?.search_query
    if (!sq) return null
    return {
      geography: sq.geography?.join(', ') || null,
      population: sq.population?.join(', ') || null,
      setting: sq.inner_setting?.join(', ') || null,
      outcomes: sq.outcome?.join(', ') || null,
    }
  }, [activeProject?.search_query])

  const handleSendMessage = async (overrideMessage?: string) => {
    const messageText = overrideMessage ?? inputMessage
    if (!messageText.trim() || isLoading || !activeProject || !chatKey) return
    const projectId = activeProject.id
    const projectMessages = getMessages(chatKey)
    const now = Date.now()

    const userMessage: ChatMessage = {
      id: `${now}`,
      role: 'user',
      content: messageText.trim(),
      timestamp: new Date()
    }

    const assistantMessageId = `${now + 1}`
    const assistantPlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      steps: [],
      activitySummary: 'Working'
    }

    addMessage(chatKey, userMessage)
    setTransientAssistantMessage(assistantPlaceholder)
    setInputMessage('')
    setLoading(true)
    clearError()

    try {
      const recentMessages = projectMessages.slice(-5).map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp
      }))

      // Call the v2 chat API
      const contextHintToSend = activeContextHint?.contextHint ?? undefined
      setActiveContextHint(null) // one-shot: clear after sending
      const lastAssistantMessage = [...projectMessages].reverse().find(m => m.role === 'assistant')
      const previousResponseId = lastAssistantMessage?.responseId ?? undefined

      const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/chat/stream`, {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          recent_messages: recentMessages,
          ...(contextHintToSend ? { context_hint: contextHintToSend } : {}),
          ...(activeMode && activeMode !== 'default' ? { mode: activeMode } : {}),
          previous_response_id: previousResponseId,
        })
      }, true)

      if (!response) {
        throw new Error('No response from server')
      }
      if (!(response instanceof Response)) {
        throw new Error('Expected a streaming response from the server')
      }

      let sawTerminalEvent = false
      let streamFailureMessage: string | null = null
      let streamingSnapshot = assistantPlaceholder

      await consumeChatStream(response, (event) => {
        if (event.type === 'message.completed') {
          sawTerminalEvent = true
        }

        if (event.type === 'message.failed') {
          sawTerminalEvent = true
          streamFailureMessage = event.error ?? 'Chat request failed. Please try again.'
          setError(streamFailureMessage)
        }

        streamingSnapshot = applyChatStreamEvent(streamingSnapshot, event)
        setTransientAssistantMessage(streamingSnapshot)
      })

      if (!sawTerminalEvent) {
        throw new Error('Chat response ended unexpectedly')
      }

      if (streamFailureMessage) {
        throw new Error(streamFailureMessage)
      }

      addMessage(chatKey, toPersistedAssistantMessage(streamingSnapshot))
      setTransientAssistantMessage(null)

    } catch (error) {
      console.error('Chat error:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to send message'
      setError(errorMessage)
      setTransientAssistantMessage((currentMessage) => (
        markStreamingMessageFailed(currentMessage ?? assistantPlaceholder, errorMessage)
      ))
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmContext = () => {
    const parts = [
      'Geography: UK',
      forecastContext?.population ? `Population: ${forecastContext.population}` : null,
      forecastContext?.setting ? `Setting: ${forecastContext.setting}` : null,
      forecastContext?.outcomes ? `Outcomes: ${forecastContext.outcomes}` : null,
    ].filter(Boolean).join('. ')
    const msg = `My context is confirmed: ${parts}. Please proceed with the transferability assessment.`
    handleSendMessage(msg)
  }

  const handleEditContext = () => {
    const lines = [
      `Geography: UK`,
      `Population: ${forecastContext?.population || '(e.g. children, older adults, knowledge workers)'}`,
      `Setting: ${forecastContext?.setting || '(e.g. NHS trust, local council, schools)'}`,
      `Outcomes: ${forecastContext?.outcomes || '(e.g. reduced waiting times, improved attendance)'}`,
    ].join('\n')
    setInputMessage(lines)
    inputRef.current?.focus()
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  if (!activeProject) {
    return (
      <div className={`flex items-center justify-center h-full bg-gray-50 rounded-lg ${className}`}>
        <div className="text-center p-8">
          <Bot className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Project Selected</h3>
          <p className="text-gray-600">Select a project to start chatting about its evidence.</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`flex flex-col h-full bg-white ${className}`}>
      {/* Header */}
      {showHeader && (
        <div className="flex-shrink-0 border-b border-gray-200 p-4">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-blue-600" />
            <h3 className="font-medium text-gray-900">Policy Assistant</h3>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
        {/* Forecast mode banner */}
        {activeMode === 'forecast' && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
            <Compass className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <span className="font-medium">Transferability Forecast</span>
              <span className="text-amber-600">: an assessment tool to support deliberation, not a recommendation. The more context you share (setting, population, constraints) the sharper the assessment.</span>
            </div>
          </div>
        )}
        {/* Forecast context card — shown before any messages */}
        {activeMode === 'forecast' && displayMessages.length === 0 && !isLoading && forecastContext && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
            <div className="text-sm font-medium text-gray-900">Your Implementation Context</div>
            <p className="text-xs text-gray-500">Pre-filled from your search with a UK implementation target assumed. Edit anything that differs from your context.</p>
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
              <span className="text-gray-500">Geography</span>
              <span className="text-gray-800">UK <span className="text-gray-400">(assumed — edit if different)</span></span>
              <span className="text-gray-500">Population</span>
              <span className="text-gray-800">{forecastContext.population || <span className="italic text-gray-400">Who is this for? e.g. children, older adults</span>}</span>
              <span className="text-gray-500">Setting</span>
              <span className="text-gray-800">{forecastContext.setting || <span className="italic text-gray-400">Where exactly? e.g. NHS trust, local council</span>}</span>
              <span className="text-gray-500">Outcomes</span>
              <span className="text-gray-800">{forecastContext.outcomes || <span className="italic text-gray-400">What result are you looking for?</span>}</span>
            </div>
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={handleConfirmContext}>
                Looks right
              </Button>
              <Button size="sm" variant="outline" onClick={handleEditContext}>
                Edit details
              </Button>
            </div>
          </div>
        )}

        {displayMessages.length === 0 && (
          <div className="text-center py-8">
            <Bot className="h-8 w-8 text-gray-400 mx-auto mb-2" />
            <p className="text-gray-600 text-sm">
              Ask me about the evidence - I will help you understand details on interventions, methodologies, and results.
            </p>
          </div>
        )}

        {displayMessages.map((message, index) => (
          <div
            key={message.id}
            className={`flex gap-3 ${
              message.role === 'user' ? 'justify-end' : 'justify-start'
            } ${index === 0 ? 'mt-4' : ''}`}
          >
            {message.role === 'assistant' && (
              <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                <Bot className="h-4 w-4 text-blue-600" />
              </div>
            )}

            <div
              className={`max-w-[80%] rounded-lg p-3 ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {message.role === 'assistant' && (
                <ActivityCard
                  message={message}
                  isExpanded={expandedActivityIds.includes(message.id)}
                  onToggleExpand={() => setExpandedActivityIds((current) => (
                    current.includes(message.id)
                      ? current.filter((id) => id !== message.id)
                      : [...current, message.id]
                  ))}
                />
              )}

              {message.content && (() => {
                const isAssistant = message.role === 'assistant'
                const withCitations = isAssistant && message.references
                  ? processInTextCitations(message.content, message.references)
                  : message.content
                const followUpQuestions = isAssistant && !message.isStreaming
                  ? extractFollowUpQuestions(withCitations)
                  : []
                const afterFollowUpStrip = followUpQuestions.length > 0
                  ? withCitations.replace(new RegExp(FOLLOW_UP_HEADING_RE.source + '[\\s\\S]*$', 'i'), '').trimEnd()
                  : withCitations
                const { cleanContent, chipGroups } = isAssistant
                  ? parseChips(afterFollowUpStrip)
                  : { cleanContent: afterFollowUpStrip, chipGroups: [] as string[][] }
                const isLastAssistant = isAssistant &&
                  index === displayMessages.length - 1

                return (
                  <>
                    <div className="prose prose-sm max-w-none">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ href, children, ...props }) => (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:text-blue-800 hover:underline"
                              {...props}
                            >
                              {children}
                            </a>
                          ),
                          table: ({ children, ...props }) => (
                            <div className="overflow-x-auto my-2">
                              <table className="min-w-full text-xs border-collapse border border-gray-200" {...props}>{children}</table>
                            </div>
                          ),
                          th: ({ children, ...props }) => (
                            <th className="border border-gray-200 bg-gray-50 px-2 py-1.5 text-left font-medium text-gray-700" {...props}>{children}</th>
                          ),
                          td: ({ children, ...props }) => {
                            const text = extractText(children)
                            const badges = text ? renderEvidenceBadges(text) : null
                            return (
                              <td className="border border-gray-200 px-2 py-1.5 text-gray-600" {...props}>
                                {badges || children}
                              </td>
                            )
                          },
                        }}
                      >
                        {cleanContent}
                      </ReactMarkdown>
                    </div>
                    {isLastAssistant && chipGroups.length > 0 && !message.isStreaming && !isLoading && (
                      <div className="mt-3 space-y-2">
                        {chipGroups.map((group, groupIdx) => (
                          <div key={groupIdx} className="flex flex-wrap gap-1.5">
                            {group.map((chip) => (
                              <button
                                key={chip}
                                type="button"
                                onClick={() => handleChipClick(chip)}
                                className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors cursor-pointer"
                              >
                                {chip}
                              </button>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                    {followUpQuestions.length > 0 && (
                      <div className="mt-3 pt-2 border-t border-gray-200">
                        <p className="text-xs font-medium text-gray-500 mb-1.5">Follow-up questions</p>
                        <div className="flex flex-wrap gap-1.5">
                          {followUpQuestions.map((q) => (
                            <button
                              key={q}
                              type="button"
                              onClick={() => {
                                setInputMessage(q)
                              }}
                              disabled={isLoading}
                              className="text-xs text-left px-2.5 py-1.5 rounded-full border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50 transition-colors"
                            >
                              {q}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )
              })()}

              {/* Show references for assistant messages */}
              {message.role === 'assistant' && message.references && message.references.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="space-y-2">
                    {message.references.map((ref, idx) => {
                      return (
                        <div key={ref.document_id} className="text-xs">
                          <div className="font-medium text-gray-800">
                            [{idx + 1}]{' '}
                            {ref.url ? (
                              <a
                                href={ref.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1"
                              >
                                {ref.title}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            ) : (
                              ref.title
                            )}
                            {(ref.published_date || ref.year) && (
                              <span className="font-normal text-gray-600">
                                {' '}({
                                  ref.published_date
                                    ? new Date(ref.published_date).getFullYear()
                                    : ref.year
                                })
                              </span>
                            )}
                          </div>
                          {ref.authors && (
                            <div className="text-gray-600">
                              {formatAuthors(ref.authors)}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>

            {message.role === 'user' && (
              user?.imageUrl ? (
                <Image
                  src={user.imageUrl}
                  alt="User avatar"
                  width={32}
                  height={32}
                  className="w-8 h-8 rounded-full flex-shrink-0 object-cover"
                />
              ) : (
                <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center flex-shrink-0">
                  <User className="h-4 w-4 text-gray-600" />
                </div>
              )
            )}
          </div>
        ))}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-gray-200 p-4">
        {activeContextHint && (
          <div className="flex items-center gap-2 mb-2 px-1">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-full">
              Context: {activeContextHint.sectionTitle}
            </span>
            <button
              type="button"
              onClick={() => setActiveContextHint(null)}
              className="text-xs text-slate-400 hover:text-slate-600"
              aria-label="Remove context"
            >
              &times;
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={placeholder}
            disabled={isLoading}
            className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100"
            rows={1}
            style={{ minHeight: '46px', maxHeight: '200px' }}
          />
          <Button
            onClick={() => handleSendMessage()}
            disabled={!inputMessage.trim() || isLoading}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white disabled:bg-gray-400"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
