'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MessageCircle, X, Send, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'

export interface FloatingMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

interface FloatingChatProps {
  messages: FloatingMessage[]
  onSend: (message: string) => Promise<void>
  isLoading?: boolean
  contextLabel?: string
}

export function FloatingChat({ messages, onSend, isLoading, contextLabel }: FloatingChatProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    const msg = input.trim()
    setInput('')
    await onSend(msg)
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-blue-600 text-white shadow-lg hover:bg-blue-700 transition-colors flex items-center justify-center"
      >
        <MessageCircle className="w-5 h-5" />
      </button>
    )
  }

  return (
    <div className="fixed bottom-0 right-0 z-50 w-[400px] h-full bg-white border-l border-slate-200 shadow-2xl flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Chat Assistant</h3>
          {contextLabel && <p className="text-xs text-slate-500">{contextLabel}</p>}
        </div>
        <Button variant="ghost" size="icon" onClick={() => setIsOpen(false)} className="h-7 w-7">
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              'max-w-[85%] rounded-xl px-3 py-2 text-sm',
              msg.role === 'user'
                ? 'ml-auto bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-800'
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
        ))}
        {isLoading && (
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <Loader2 className="w-3 h-3 animate-spin" />
            Thinking...
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-slate-200 bg-white">
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask about the results..."
            className="flex-1 text-sm"
          />
          <Button size="icon" onClick={handleSend} disabled={isLoading || !input.trim()}>
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
