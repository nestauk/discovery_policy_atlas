'use client'

import { useEffect } from 'react'
import { Bot, X, MessageCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AnimatePresence, motion } from 'framer-motion'
import { ChatInterface } from './ChatInterface'
import { useChatStore } from '@/lib/chatStore'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'

/** Sidebar width in pixels — import this where you need a matching margin. */
export const CHAT_SIDEBAR_WIDTH = 400

interface ChatbotWidgetProps {
  className?: string
}

export function ChatbotWidget({ className = "" }: ChatbotWidgetProps) {
  const {
    activeProjectId,
    clearError,
    isOpen,
    setActiveProjectId,
    setIsOpen,
    setLoading
  } = useChatStore()
  const { activeProject } = useAnalysisProjectStore()
  const currentProjectId = activeProject?.id ?? null
  const isProjectInSync = currentProjectId === activeProjectId

  useEffect(() => {
    setActiveProjectId(currentProjectId)
    clearError()
    setLoading(false)
    setIsOpen(false)
  }, [clearError, currentProjectId, setActiveProjectId, setIsOpen, setLoading])

  if (!activeProject) {
    return null
  }

  return (
    <>
      {/* Floating Chat Button */}
      <AnimatePresence>
        {(!isOpen || !isProjectInSync) && (
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            className={`fixed bottom-6 right-6 z-50 ${className}`}
          >
            <Button
              onClick={() => setIsOpen(true)}
              className="w-14 h-14 rounded-full bg-blue-600 hover:bg-blue-700 text-white shadow-lg hover:shadow-xl transition-all duration-200"
            >
              <MessageCircle className="h-6 w-6" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Backdrop (overlay mode — below 2xl) */}
      <AnimatePresence>
        {isOpen && isProjectInSync && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-black/20 2xl:hidden"
            onClick={() => setIsOpen(false)}
            aria-hidden
          />
        )}
      </AnimatePresence>

      {/* Sidebar Panel */}
      <AnimatePresence>
        {isOpen && isProjectInSync && (
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'tween', duration: 0.25 }}
            className="fixed inset-y-0 right-0 z-50 flex flex-col bg-white border-l border-slate-200 shadow-xl w-full sm:w-[400px]"
            style={{ maxWidth: CHAT_SIDEBAR_WIDTH }}
          >
            {/* Header */}
            <div className="flex-shrink-0 p-3 bg-blue-600 text-white">
              <div className="flex items-center justify-between">
                <div className="flex items-end gap-2">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center">
                    <Bot className="h-6 w-6" />
                  </div>
                  <h3 className="text-base font-medium">Policy Assistant</h3>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsOpen(false)}
                  className="text-white hover:bg-white/20 h-8 w-8 p-0"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Chat */}
            <div className="flex-1 min-h-0">
              <ChatInterface
                placeholder="Ask about the evidence..."
                className="h-full"
                showHeader={false}
                autoFocus
              />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
