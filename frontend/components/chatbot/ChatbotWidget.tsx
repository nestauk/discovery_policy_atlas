'use client'

import { useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tooltip } from '@/components/ui/tooltip'
import { 
  MessageCircle, 
  Minimize2, 
  Bot
} from 'lucide-react'
import { useChatbotStore } from '@/lib/chatbotStore'
import { ChatInterface } from '@/components/chatbot/ChatInterface'

interface ChatbotWidgetProps {
  isOpen: boolean
  onToggle: () => void
  researchQuestion?: string
}

export function ChatbotWidget({ isOpen, onToggle, researchQuestion }: ChatbotWidgetProps) {
  const { 
    messages, 
    setMessages, 
    setResearchQuestion,
    evidenceSearchReady
  } = useChatbotStore()

  // Initialize with welcome message if research question is provided
  useEffect(() => {
    if (researchQuestion && messages.length === 0) {
      setResearchQuestion(researchQuestion)
      setMessages([
        {
          id: '1',
          role: 'assistant',
          content: `I'm here to help you explore evidence for your research question: "${researchQuestion}". What specific aspects would you like to investigate?`,
          timestamp: new Date()
        }
      ])
    }
  }, [researchQuestion, messages.length, setMessages, setResearchQuestion])

  return (
    <>
      <style jsx>{`
        .hide-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
        .hide-scrollbar::-webkit-scrollbar {
          display: none;
        }
      `}</style>
      
      {/* Floating Minimized Button */}
      <AnimatePresence>
        {!isOpen && (
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            className="fixed bottom-6 right-6 z-50"
          >
            <Tooltip content="Open Policy Assistant">
              <Button
                onClick={onToggle}
                className="h-14 w-14 rounded-full bg-blue-600 hover:bg-blue-700 shadow-lg"
              >
                <MessageCircle className="h-6 w-6 text-white" />
              </Button>
            </Tooltip>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Expanded Chatbot */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ scale: 0.8, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.8, opacity: 0, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="fixed bottom-6 right-6 z-50 w-100 h-[480px] max-w-[calc(100vw-3rem)]"
          >
            <Card className="h-full shadow-2xl border-0">
              <CardHeader className="py-0 px-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 bg-blue-600 rounded-md flex items-center justify-center">
                      <Bot className="h-3 w-3 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-900">Policy Assistant</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {evidenceSearchReady && (
                      <Tooltip content="Evidence search is ready">
                        <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                      </Tooltip>
                    )}
                    <Tooltip content="Minimize chat">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={onToggle}
                        className="h-7 w-7 p-0 hover:bg-slate-100"
                      >
                        <Minimize2 className="h-3 w-3" />
                      </Button>
                    </Tooltip>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent className="p-0 h-[420px]">
                <ChatInterface 
                  enableAutoScroll={isOpen} // Only auto-scroll when widget is open
                  placeholder="Ask about policy evidence, research findings, or specific interventions..."
                  className="h-full"
                />
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}