'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Bot, User, ExternalLink } from 'lucide-react'
import { useV2ChatStore, ChatMessage } from '@/lib/v2ChatStore'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'
import ReactMarkdown from 'react-markdown'
import { useUser } from '@clerk/nextjs'
import Image from 'next/image'

// Helper function to process in-text citations
function processInTextCitations(content: string, references: { url?: string }[]): string {
  // Replace [Document X] with clickable [X] links
  return content.replace(/\[Document (\d+)\]/g, (match, docNum) => {
    const refIndex = parseInt(docNum) - 1
    if (refIndex >= 0 && refIndex < references.length) {
      const ref = references[refIndex]
      const url = ref.url
      if (url) {
        return `[[${docNum}]](${url})`
      }
    }
    return `[${docNum}]`
  })
}

interface V2ChatInterfaceProps {
  className?: string
  placeholder?: string
  autoFocus?: boolean
  showHeader?: boolean
}

export function V2ChatInterface({ 
  className = "",
  placeholder = "Ask about the evidence in this project...",
  autoFocus = false,
  showHeader = false
}: V2ChatInterfaceProps) {
  const {
    messages, 
    isLoading,
    error,
    addMessage, 
    setLoading,
    setError,
    clearError
  } = useV2ChatStore()
  
  const { activeProject } = useAnalysisProjectStore()
  const { user } = useUser()
  const [inputMessage, setInputMessage] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { fetchWithAuth } = useAPI()

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-focus input if requested
  useEffect(() => {
    if (autoFocus) {
      const input = document.querySelector('textarea') as HTMLTextAreaElement
      if (input) input.focus()
    }
  }, [autoFocus])

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading || !activeProject) return

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage.trim(),
      timestamp: new Date()
    }

    addMessage(userMessage)
    setInputMessage('')
    setLoading(true)
    clearError()

    try {
      // Prepare recent messages for context (last 5 messages, excluding current)
      const recentMessages = messages.slice(-5).map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp
      }))

      // Call the v2 chat API
      const response = await fetchWithAuth(`/api/analysis-projects/${activeProject.id}/chat`, {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          recent_messages: recentMessages
        })
      })

      if (!response) {
        throw new Error('No response from server')
      }

      // Add assistant response with references
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: new Date()
      }
      
      // Store references in the message for later display
      if (response.references && response.references.length > 0) {
        assistantMessage.references = response.references
      }
      
      addMessage(assistantMessage)

    } catch (error) {
      console.error('Chat error:', error)
      setError(error instanceof Error ? error.message : 'Failed to send message')
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
        {messages.length === 0 && (
          <div className="text-center py-8">
            <Bot className="h-8 w-8 text-gray-400 mx-auto mb-2" />
            <p className="text-gray-600 text-sm">
              Ask me about the evidence - I will help you understand details on interventions, methodologies, and results.
            </p>
          </div>
        )}

        {messages.map((message, index) => (
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
                  {message.role === 'assistant' && message.references
                    ? processInTextCitations(message.content, message.references)
                    : message.content
                  }
                </ReactMarkdown>
              </div>
              
              {/* Show references for assistant messages */}
              {message.role === 'assistant' && message.references && (
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

        {isLoading && (
          <div className="flex gap-3 justify-start">
            <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
              <Bot className="h-4 w-4 text-blue-600" />
            </div>
            <div className="bg-gray-100 rounded-lg p-3">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
              </div>
            </div>
          </div>
        )}

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