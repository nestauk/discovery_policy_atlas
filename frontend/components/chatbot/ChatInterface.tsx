'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Bot, User, Search } from 'lucide-react'
import { useChatbotStore } from '@/lib/chatbotStore'
import { useProjectStore } from '@/lib/projectStore'
import { useAPI } from '@/lib/api'
import ReactMarkdown from 'react-markdown'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface ChatInterfaceProps {
  className?: string
  placeholder?: string
  autoFocus?: boolean
  autoStartQuery?: string
  showStartSearchButton?: boolean
  onStartSearch?: () => void
  enableAutoScroll?: boolean
  onAutoStartComplete?: () => void
}

export function ChatInterface({ 
  className = "",
  placeholder = "Ask about policy evidence, research findings, or specific interventions...",
  autoFocus = false,
  autoStartQuery,
  showStartSearchButton = false,
  onStartSearch,
  enableAutoScroll = true,
  onAutoStartComplete
}: ChatInterfaceProps) {
  const {
    messages, 
    addMessage, 
    conversationId,
    setConversationId,
    conversationState,
    setConversationState,
    searchQuery,
    setSearchQuery,
    setEvidenceSearchReady,
    setOutcomesDefined,
    setScopeDefined
  } = useChatbotStore()
  const { activeProject } = useProjectStore()
  
  const [inputMessage, setInputMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isAutoStarting, setIsAutoStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const autoStartedRef = useRef<string | null>(null)
  const { fetchWithAuth } = useAPI()

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (enableAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, enableAutoScroll])

  // Auto-focus input if requested
  useEffect(() => {
    if (autoFocus) {
      const input = document.querySelector('textarea') as HTMLTextAreaElement
      if (input) input.focus()
    }
  }, [autoFocus])

  // Auto-start conversation with query
  useEffect(() => {
    if (autoStartQuery && autoStartQuery !== autoStartedRef.current) {
      autoStartedRef.current = autoStartQuery
      
      // Add user message first
      const userMessage = {
        id: `user-${Date.now()}`,
        role: 'user' as const,
        content: autoStartQuery,
        timestamp: new Date()
      }
      
      addMessage(userMessage)
      
      // Auto-send the query to get AI response
      const autoSendQuery = async () => {
        setIsAutoStarting(true)
        try {
          const response = await fetchWithAuth('api/agent/chat', {
            method: 'POST',
            body: JSON.stringify({
              message: autoStartQuery,
              conversation_id: conversationId,
              project_id: activeProject?.id,
              state: conversationState
            })
          })

          if (!response) {
            throw new Error('No response from server')
          }

          // Update conversation state
          if (response.conversation_id && response.conversation_id !== conversationId) {
            setConversationId(response.conversation_id)
          }

          if (response.state) {
            setConversationState(response.state)
          }

          if (response.search_query) {
            setSearchQuery(response.search_query)
          }

          if (response.evidence_search_ready !== undefined) {
            setEvidenceSearchReady(response.evidence_search_ready)
          }

          if (response.outcomes_defined !== undefined) {
            setOutcomesDefined(response.outcomes_defined)
          }

          if (response.scope_defined !== undefined) {
            setScopeDefined(response.scope_defined)
          }

          // Add assistant response
          const assistantMessage = {
            id: `assistant-${Date.now()}`,
            role: 'assistant' as const,
            content: response.message,
            timestamp: new Date()
          }
          addMessage(assistantMessage)

          // Show search query if available and different from previous
          if (response.search_query && response.search_query !== searchQuery && response.search_query !== 'No research question defined yet') {
            const queryMessage = {
              id: `query-${Date.now()}`,
              role: 'assistant' as const,
              content: `📝 Current research focus: ${response.search_query}`,
              timestamp: new Date()
            }
            addMessage(queryMessage)
          }

        } catch (error) {
          console.error('Auto-start chat error:', error)
          const errorMessage = error instanceof Error ? error.message : 'Failed to start conversation'
          if (errorMessage.includes('Authentication failed') || errorMessage.includes('authentication token')) {
            setError('Please refresh the page and sign in again to start the conversation.')
          } else {
            setError('Failed to start conversation. Please try again.')
          }
        } finally {
          setIsAutoStarting(false)
          onAutoStartComplete?.()
        }
      }
      
      setTimeout(() => { autoSendQuery() }, 100)
    }
  }, [autoStartQuery, conversationId, conversationState, searchQuery, addMessage, setConversationId, setConversationState, setSearchQuery, setEvidenceSearchReady, setOutcomesDefined, setScopeDefined, fetchWithAuth, onAutoStartComplete])

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage.trim(),
      timestamp: new Date()
    }

    addMessage(userMessage)
    setInputMessage('')
    setIsLoading(true)
    setError(null)

    try {
      // Call the backend chat API
      const response = await fetchWithAuth('api/agent/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          conversation_id: conversationId,
          project_id: activeProject?.id,
          state: conversationState
        })
      })

      if (!response) {
        throw new Error('No response from server')
      }

      // Update conversation state
      if (response.conversation_id && response.conversation_id !== conversationId) {
        setConversationId(response.conversation_id)
      }

      if (response.state) {
        setConversationState(response.state)
      }

      if (response.search_query) {
        setSearchQuery(response.search_query)
      }

      if (response.evidence_search_ready !== undefined) {
        setEvidenceSearchReady(response.evidence_search_ready)
      }

      if (response.outcomes_defined !== undefined) {
        setOutcomesDefined(response.outcomes_defined)
      }

      if (response.scope_defined !== undefined) {
        setScopeDefined(response.scope_defined)
      }

      // Add assistant response
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: new Date()
      }
      addMessage(assistantMessage)

      // Show search query if available and different from previous
      if (response.search_query && response.search_query !== searchQuery && response.search_query !== 'No research question defined yet') {
        const queryMessage: Message = {
          id: (Date.now() + 2).toString(),
          role: 'assistant',
          content: `📝 Current research focus: ${response.search_query}`,
          timestamp: new Date()
        }
        addMessage(queryMessage)
      }

    } catch (error) {
      console.error('Chat API error:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to send message'
      
      if (errorMessage.includes('Authentication failed') || errorMessage.includes('authentication token')) {
        setError('Please refresh the page and sign in again to continue the conversation.')
        const authErrorMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'I apologize, but your session has expired. Please refresh the page and sign in again to continue our conversation.',
          timestamp: new Date()
        }
        addMessage(authErrorMessage)
      } else {
        setError('Failed to send message. Please try again.')
        const errorMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'I apologize, but I encountered an issue. Please try again.',
          timestamp: new Date()
        }
        addMessage(errorMessage)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* State Indicator */}
      {conversationState === 'chat' && (
        <div className="bg-green-50 border-b border-green-200 px-4 py-2">
          <div className="flex items-center gap-2 text-sm text-green-700">
            <Bot className="h-4 w-4" />
            <span className="font-medium">Evidence Mode:</span>
            <span>I can now answer questions about your collected research evidence</span>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <Bot className="h-12 w-12 text-slate-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">Policy Research Assistant</h3>
            <p className="text-slate-600 mb-4">I&apos;m here to help you refine your policy research question and find relevant evidence.</p>
            <div className="text-sm text-slate-500 bg-slate-50 rounded-lg p-4 max-w-md mx-auto">
              <p className="mb-2"><strong>I can help you:</strong></p>
              <ul className="list-disc list-inside space-y-1 text-left">
                <li>Clarify your research outcomes</li>
                <li>Define your scope and demographics</li>
                <li>Suggest related policy areas to explore</li>
                <li>Discuss the evidence we found</li>
              </ul>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-900'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                {message.role === 'user' ? (
                  <User className="h-3 w-3" />
                ) : (
                  <Bot className="h-3 w-3" />
                )}
                <span className="text-xs opacity-70">
                  {(() => {
                    try {
                      const timestamp = message.timestamp instanceof Date 
                        ? message.timestamp 
                        : new Date(message.timestamp);
                      return timestamp.toLocaleTimeString([], { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                      });
                    } catch {
                      return new Date().toLocaleTimeString([], { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                      });
                    }
                  })()}
                </span>
              </div>
              <div className="text-sm prose prose-sm max-w-none">
                <ReactMarkdown 
                  components={{
                    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                    ul: ({ children }) => <ul className="mb-2 pl-4 list-disc">{children}</ul>,
                    ol: ({ children }) => <ol className="mb-2 pl-4 list-decimal">{children}</ol>,
                    li: ({ children }) => <li className="mb-1">{children}</li>,
                    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                    em: ({ children }) => <em className="italic">{children}</em>,
                    code: ({ children }) => <code className="bg-gray-100 px-1 py-0.5 rounded text-sm font-mono">{children}</code>,
                    blockquote: ({ children }) => <blockquote className="border-l-4 border-gray-300 pl-3 italic">{children}</blockquote>,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
        
        {/* Loading indicator */}
        {(isLoading || isAutoStarting) && (
          <div className="flex justify-start">
            <div className="bg-slate-100 text-slate-900 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
              </div>
            </div>
          </div>
        )}

        {/* Start Search Button */}
        {showStartSearchButton && messages.length >= 4 && (
          <div className="flex justify-center py-4">
            <Button 
              onClick={onStartSearch}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2"
            >
              <Search className="h-4 w-4 mr-2" />
              Start Evidence Search
            </Button>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-red-50 border-t border-red-200">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-slate-200 p-4 bg-white">
        <div className="flex gap-3">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isAutoStarting ? "Processing..." : placeholder}
            disabled={isAutoStarting}
            className="flex-1 min-h-[44px] max-h-32 p-3 text-sm border border-slate-200 rounded-lg focus:border-blue-500 focus:ring-blue-500 resize-none"
            style={{ resize: 'none' }}
          />
          <Button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || isLoading || isAutoStarting}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}