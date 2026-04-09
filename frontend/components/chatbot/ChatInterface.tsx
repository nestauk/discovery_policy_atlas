'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Bot, User, ExternalLink, Loader2, AlertCircle, CheckCircle2, Compass } from 'lucide-react'
import {
  useChatStore,
  chatStorageKey,
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

const DOCUMENT_CITATION_BRACKET_RE = /\[([^\]]+)\]/g
const CHIP_LINE_RE = /\[chips:\s*((?:"[^"]*"(?:\s*\|\s*"[^"]*")*))\s*\]/g
const CHIP_VALUE_RE = /"([^"]*)"/g
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

function parseCitationGroup(bracketContent: string): number[] {
  const cleaned = bracketContent
    .replace(/\bdocuments?\b/gi, '')
    .replace(/&/g, ',')
    .replace(/\band\b/gi, ',')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^,+|,+$/g, '')

  if (!cleaned || !/^\d+(?:\s*,\s*\d+)*$/.test(cleaned)) {
    return []
  }

  return cleaned.split(',').map((part) => parseInt(part.trim(), 10))
}

function buildCitationLabelMap(content: string, references: { url?: string }[]): Map<number, number> {
  const labelMap = new Map<number, number>()
  let match: RegExpExecArray | null

  DOCUMENT_CITATION_BRACKET_RE.lastIndex = 0
  while ((match = DOCUMENT_CITATION_BRACKET_RE.exec(content)) !== null) {
    for (const rawNumber of parseCitationGroup(match[1])) {
      if (labelMap.has(rawNumber)) {
        continue
      }

      const nextLabel = labelMap.size + 1
      if (nextLabel > references.length) {
        continue
      }
      labelMap.set(rawNumber, nextLabel)
    }
  }

  return labelMap
}

// Helper function to process in-text citations
function processInTextCitations(content: string, references: { url?: string }[]): string {
  const labelMap = buildCitationLabelMap(content, references)

  // Replace [5], [Document 5], or grouped forms like [Documents 5 and 7]
  return content.replace(DOCUMENT_CITATION_BRACKET_RE, (match, bracketContent) => {
    const numbers = parseCitationGroup(bracketContent)
    if (numbers.length === 0) {
      return match
    }

    return numbers.map((number) => {
      const label = labelMap.get(number)
      if (!label) {
        return `[${number}]`
      }

      const refIndex = label - 1
      if (refIndex >= 0 && refIndex < references.length) {
        const ref = references[refIndex]
        if (ref.url) {
          return `[[${label}]](${ref.url})`
        }
      }
      return `[${label}]`
    }).join('')
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
      error: undefined,
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
      // Prepare recent messages for context (last 5 messages, excluding current)
      const recentMessages = projectMessages.slice(-5).map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp
      }))

      // Call the v2 chat API
      const contextHintToSend = activeContextHint?.contextHint ?? undefined
      setActiveContextHint(null) // one-shot: clear after sending

      const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/chat/stream`, {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          recent_messages: recentMessages,
          ...(contextHintToSend ? { context_hint: contextHintToSend } : {}),
          ...(activeMode && activeMode !== 'default' ? { mode: activeMode } : {}),
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
      forecastContext?.geography ? `Geography: ${forecastContext.geography}` : null,
      forecastContext?.population ? `Population: ${forecastContext.population}` : null,
      forecastContext?.setting ? `Setting: ${forecastContext.setting}` : null,
      forecastContext?.outcomes ? `Outcomes: ${forecastContext.outcomes}` : null,
    ].filter(Boolean).join('. ')
    const msg = parts
      ? `My context is confirmed: ${parts}. Please proceed with the transferability assessment.`
      : 'Please proceed with the transferability assessment.'
    handleSendMessage(msg)
  }

  const handleEditContext = () => {
    const lines = [
      `Geography: ${forecastContext?.geography || '(e.g. UK, OECD countries)'}`,
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
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <Compass className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <div>
              <span className="font-medium">Transferability Forecast</span>
              <span className="text-amber-600"> — This is an assessment tool to support deliberation, not a recommendation.</span>
            </div>
          </div>
        )}
        {/* Forecast context card — shown before any messages */}
        {activeMode === 'forecast' && displayMessages.length === 0 && !isLoading && forecastContext && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
            <div className="text-sm font-medium text-gray-900">Your Project Context</div>
            <p className="text-xs text-gray-500">This is what I know from your search. Confirm or edit before we start.</p>
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
              <span className="text-gray-500">Geography</span>
              <span className="text-gray-800">{forecastContext.geography || <span className="italic text-gray-400">Where are you implementing? e.g. UK, OECD</span>}</span>
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
                (() => {
                  const hasActivity = Boolean(
                    message.isStreaming ||
                    message.error ||
                    message.activitySummary ||
                    (message.steps && message.steps.length > 0)
                  )
                  const isActivityExpanded = expandedActivityIds.includes(message.id)
                  const shouldShowSteps = Boolean(
                    message.steps &&
                    message.steps.length > 0 &&
                    (message.isStreaming || isActivityExpanded)
                  )

                  if (!hasActivity) {
                    return null
                  }

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
                        </div>

                        {!message.isStreaming && message.steps && message.steps.length > 0 && (
                          <button
                            type="button"
                            onClick={() => {
                              setExpandedActivityIds((current) => (
                                current.includes(message.id)
                                  ? current.filter((id) => id !== message.id)
                                  : [...current, message.id]
                              ))
                            }}
                            className="text-xs text-gray-500 hover:text-gray-700"
                          >
                            {isActivityExpanded ? 'Hide workings' : 'Show workings'}
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
                })()
              )}

              {message.content && (() => {
                const processed = message.role === 'assistant' && message.references
                  ? processInTextCitations(message.content, message.references)
                  : message.content
                const { cleanContent, chipGroups } = message.role === 'assistant'
                  ? parseChips(processed)
                  : { cleanContent: processed, chipGroups: [] as string[][] }
                const isLastAssistant = message.role === 'assistant' &&
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
                          td: ({ children, ...props }) => (
                            <td className="border border-gray-200 px-2 py-1.5 text-gray-600" {...props}>{children}</td>
                          ),
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
                  </>
                )
              })()}

              {/* Show references for assistant messages */}
              {message.role === 'assistant' && message.references && message.references.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="space-y-2">
                    {message.references.map((ref, idx) => {
                      // Helper function to process and truncate authors
                      const formatAuthors = (authors: string[] | string) => {
                        if (!authors) return ''
                        
                        let authorText = ''
                        
                        if (Array.isArray(authors)) {
                          authorText = authors.join(', ')
                        } else {
                          authorText = String(authors)
                        }
                        
                        // Simple approach: strip all brackets, quotes, and extra spaces
                        authorText = authorText
                          .replace(/[\[\]'"]/g, '') // Remove all brackets and quotes
                          .replace(/,\s*,/g, ',') // Fix double commas
                          .replace(/^\s*,|,\s*$/g, '') // Remove leading/trailing commas
                          .trim()
                        
                        // Truncate if too long
                        if (authorText.length <= 60) return authorText
                        
                        // Find the last complete author name within ~50 chars
                        const truncated = authorText.substring(0, 50)
                        const lastComma = truncated.lastIndexOf(', ')
                        if (lastComma > 20) {
                          return truncated.substring(0, lastComma) + ' et al.'
                        }
                        return truncated + '...'
                      }

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
