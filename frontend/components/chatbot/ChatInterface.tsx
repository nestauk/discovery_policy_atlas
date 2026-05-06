'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Bot, User, ExternalLink, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import {
  useChatStore,
  AnswerMetadata,
  ChatMessage,
  ChatStep,
  ChatStreamEvent,
} from '@/lib/chatStore'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import ReactMarkdown from 'react-markdown'
import { useUser } from '@clerk/nextjs'
import Image from 'next/image'

const DOCUMENT_CITATION_BRACKET_RE = /\[([^\]]+)\]/g
const EMPTY_CHAT_MESSAGES: ChatMessage[] = []
const EMPTY_CHAT_STEPS: ChatStep[] = []

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

// Helper function to process in-text citations
function processInTextCitations(content: string, references: { url?: string }[]): string {
  // Replace [5], [Document 5], or grouped forms like [Documents 5 and 7]
  return content.replace(DOCUMENT_CITATION_BRACKET_RE, (match, bracketContent) => {
    const numbers = parseCitationGroup(bracketContent)
    if (numbers.length === 0) {
      return match
    }

    return numbers.map((number) => {
      const ref = references[number - 1]
      if (!ref) {
        return `[${number}]`
      }
      if (ref.url) {
        return `[[${number}]](${ref.url})`
      }
      return `[${number}]`
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
    clearMessages,
    getMessages,
    isLoading,
    error,
    addMessage,
    setLoading,
    setError,
    clearError
  } = useChatStore()
  
  const { activeProject } = useAnalysisProjectStore()
  const { user } = useUser()
  const [inputMessage, setInputMessage] = useState('')
  const [transientAssistantMessage, setTransientAssistantMessage] = useState<ChatMessage | null>(null)
  const [expandedActivityIds, setExpandedActivityIds] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { fetchWithAuth } = useAPI()
  const activeProjectId = activeProject?.id ?? null
  const messages = activeProjectId ? getMessages(activeProjectId) : EMPTY_CHAT_MESSAGES
  const displayMessages = (
    transientAssistantMessage &&
    !messages.some((message) => message.id === transientAssistantMessage.id)
  )
    ? [...messages, transientAssistantMessage]
    : messages

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, transientAssistantMessage])

  // Auto-focus input if requested
  useEffect(() => {
    if (autoFocus) {
      const input = document.querySelector('textarea') as HTMLTextAreaElement
      if (input) input.focus()
    }
  }, [autoFocus])

  useEffect(() => {
    setTransientAssistantMessage(null)
    setExpandedActivityIds([])
  }, [activeProjectId])

  const handleNewChat = () => {
    if (!activeProjectId) return

    clearMessages(activeProjectId)
    clearError()
    setLoading(false)
    setInputMessage('')
    setTransientAssistantMessage(null)
    setExpandedActivityIds([])
  }

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading || !activeProject) return
    const projectId = activeProject.id
    const projectMessages = getMessages(projectId)
    const now = Date.now()

    const userMessage: ChatMessage = {
      id: `${now}`,
      role: 'user',
      content: inputMessage.trim(),
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

    addMessage(projectId, userMessage)
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

      const lastAssistantMessage = [...projectMessages].reverse().find(m => m.role === 'assistant')
      const previousResponseId = lastAssistantMessage?.responseId ?? undefined

      const response = await fetchWithAuth(`/api/analysis-projects/${projectId}/chat/stream`, {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          recent_messages: recentMessages,
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

      addMessage(projectId, toPersistedAssistantMessage(streamingSnapshot))
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
        {displayMessages.length > 0 && (
          <div className="sticky top-0 z-10 flex justify-end bg-white/95 py-3 backdrop-blur-sm">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleNewChat}
              disabled={isLoading}
              className="text-xs"
            >
              New chat
            </Button>
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
                          {!message.isStreaming && !message.error && message.answerMetadata && (
                            <span className="text-gray-500 font-normal">
                              — {formatAnswerMetadata(message.answerMetadata)}
                            </span>
                          )}
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
                const followUpQuestions = message.role === 'assistant' && !message.isStreaming
                  ? extractFollowUpQuestions(message.content)
                  : []
                const displayContent = followUpQuestions.length > 0
                  ? message.content.replace(new RegExp(FOLLOW_UP_HEADING_RE.source + '[\\s\\S]*$', 'i'), '').trimEnd()
                  : message.content
                const processedContent = message.role === 'assistant' && message.references
                  ? processInTextCitations(displayContent, message.references)
                  : displayContent

                return (
                  <>
                    <div className="prose prose-sm max-w-none">
                      <ReactMarkdown
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
                        }}
                      >
                        {processedContent}
                      </ReactMarkdown>
                    </div>
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
        <div className="flex gap-2">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={placeholder}
            disabled={isLoading}
            className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100"
            rows={1}
            style={{ minHeight: '46px', maxHeight: '120px' }}
          />
          <Button
            onClick={handleSendMessage}
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
