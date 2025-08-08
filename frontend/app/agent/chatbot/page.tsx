'use client'

import { useEffect } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { useChatbotStore } from '@/lib/chatbotStore'
import { ChatInterface } from '@/components/chatbot/ChatInterface'

export default function ChatbotPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const query = searchParams.get('query') || ''
  const { 
    messages, 
    setMessages, 
    setResearchQuestion, 
    evidenceSearchReady
  } = useChatbotStore()

  // Set background color for the entire page
  useEffect(() => {
    document.body.style.backgroundColor = '#f8fafc' // slate-50
    return () => {
      document.body.style.backgroundColor = '' // Clean up on unmount
    }
  }, [])

  // Clear messages when query changes to ensure clean start
  useEffect(() => {
    if (query) {
      setMessages([])
      setResearchQuestion(query)
    }
  }, [query, setMessages, setResearchQuestion])

  // Show start search button when evidence search is ready OR after first chatbot response
  const showStartSearch = evidenceSearchReady || messages.length >= 2

  const handleStartSearch = () => {
    router.push(`/agent/results?query=${encodeURIComponent(query)}`)
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Tooltip content="Back to search">
                <Link href="/agent">
                  <Button variant="ghost" size="sm" className="p-2">
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                </Link>
              </Tooltip>
              
              <div>
                <h1 className="text-lg font-semibold text-slate-900">Policy Research Assistant</h1>
                <p className="text-sm text-slate-600">Refine your research question and scope</p>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              {query && (
                <Badge variant="outline" className="text-xs max-w-xs truncate">
                  {query}
                </Badge>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Interface */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-6">
        <div className="flex flex-col space-y-6">
          <ChatInterface 
            autoStartQuery={query || undefined}
            showStartSearchButton={showStartSearch}
            onStartSearch={handleStartSearch}
            autoFocus={true}
            placeholder="Describe your policy research question in detail..."
            className="flex-1 min-h-0"
          />
        </div>
      </main>
    </div>
  )
}