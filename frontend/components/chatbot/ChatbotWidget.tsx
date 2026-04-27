'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Bot, X, MessageCircle, History, SquarePen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AnimatePresence, motion } from 'framer-motion'
import { ChatInterface } from './ChatInterface'
import { ChatHistoryList } from './ChatHistoryList'
import { useChatStore, chatStorageKey, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from '@/lib/chatStore'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'

const KEYBOARD_RESIZE_STEP = 20

interface ChatbotWidgetProps {
  className?: string
}

export function ChatbotWidget({ className = "" }: ChatbotWidgetProps) {
  const {
    activeProjectId,
    activeMode,
    clearError,
    isOpen,
    isLoading,
    setActiveProjectId,
    setIsOpen,
    setLoading,
    startNewConversation,
  } = useChatStore()
  const sidebarWidth = useChatStore((s) => s.sidebarWidth)
  const setSidebarWidth = useChatStore((s) => s.setSidebarWidth)
  const { activeProject } = useAnalysisProjectStore()
  const currentProjectId = activeProject?.id ?? null
  // Prevents showing a stale chat from the previous project during the tick
  // between the project store updating and the useEffect syncing activeProjectId.
  const isProjectInSync = currentProjectId === activeProjectId

  const chatKey = currentProjectId ? chatStorageKey(currentProjectId, activeMode) : null

  const [showHistory, setShowHistory] = useState(false)
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    setActiveProjectId(currentProjectId)
    clearError()
    setLoading(false)
    setIsOpen(false)
  }, [clearError, currentProjectId, setActiveProjectId, setIsOpen, setLoading])

  // Close history panel when sidebar closes or project changes
  useEffect(() => {
    setShowHistory(false)
  }, [isOpen, currentProjectId])

  // Cleanup drag listeners on unmount
  useEffect(() => {
    return () => cleanupRef.current?.()
  }, [])

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const target = e.currentTarget
    target.setPointerCapture(e.pointerId)

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handlePointerMove = (ev: PointerEvent) => {
      setSidebarWidth(window.innerWidth - ev.clientX)
    }

    const cleanup = () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      target.releasePointerCapture(e.pointerId)
      target.removeEventListener('pointermove', handlePointerMove)
      target.removeEventListener('pointerup', cleanup)
      target.removeEventListener('pointercancel', cleanup)
      window.removeEventListener('blur', cleanup)
      cleanupRef.current = null
    }

    cleanupRef.current = cleanup

    target.addEventListener('pointermove', handlePointerMove)
    target.addEventListener('pointerup', cleanup)
    target.addEventListener('pointercancel', cleanup)
    window.addEventListener('blur', cleanup)
  }, [setSidebarWidth])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setSidebarWidth(sidebarWidth + KEYBOARD_RESIZE_STEP)
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      setSidebarWidth(sidebarWidth - KEYBOARD_RESIZE_STEP)
    } else if (e.key === 'Home') {
      e.preventDefault()
      setSidebarWidth(SIDEBAR_MAX_WIDTH)
    } else if (e.key === 'End') {
      e.preventDefault()
      setSidebarWidth(SIDEBAR_MIN_WIDTH)
    }
  }, [setSidebarWidth, sidebarWidth])

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
              aria-label="Open chat"
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
            className="fixed inset-y-0 right-0 z-50 flex flex-col bg-white border-l border-slate-200 shadow-xl"
            style={{ width: sidebarWidth, maxWidth: '100vw' }}
            role="complementary"
            aria-label="Chat sidebar"
          >
            {/* Resize handle — visible strip is narrow, hit area is wider */}
            <div
              onPointerDown={handlePointerDown}
              onKeyDown={handleKeyDown}
              role="separator"
              aria-orientation="vertical"
              aria-valuenow={sidebarWidth}
              aria-valuemin={SIDEBAR_MIN_WIDTH}
              aria-valuemax={SIDEBAR_MAX_WIDTH}
              aria-label="Resize chat sidebar"
              tabIndex={0}
              className="absolute inset-y-0 -left-1.5 w-3 cursor-col-resize z-10 group"
            >
              <div className="absolute inset-y-0 left-1.5 w-0.5 group-hover:bg-blue-400/60 group-active:bg-blue-500/80 transition-colors" />
            </div>

            {/* Header */}
            <div className="flex-shrink-0 p-3 bg-blue-600 text-white">
              <div className="flex items-center justify-between">
                <div className="flex items-end gap-2">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center">
                    <Bot className="h-6 w-6" />
                  </div>
                  <h3 className="text-base font-medium">Policy Assistant</h3>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (chatKey) startNewConversation(chatKey)
                    }}
                    disabled={isLoading || !chatKey}
                    aria-label="New chat"
                    className="text-white hover:bg-white/20 h-auto px-2 py-1 text-xs font-medium gap-1 disabled:opacity-40"
                  >
                    <SquarePen className="h-3.5 w-3.5" />
                    New chat
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowHistory((prev) => !prev)}
                    disabled={isLoading}
                    aria-label="Chat history"
                    className={`text-white h-8 w-8 p-0 disabled:opacity-40 ${showHistory ? 'bg-white/20' : 'hover:bg-white/20'}`}
                  >
                    <History className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsOpen(false)}
                    aria-label="Close chat"
                    className="text-white hover:bg-white/20 h-8 w-8 p-0"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>

            {/* History panel — inline collapsible between header and chat */}
            <AnimatePresence>
              {showHistory && chatKey && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: 'easeInOut' }}
                  className="flex-shrink-0 overflow-hidden border-b border-gray-200 bg-gray-50"
                >
                  <ChatHistoryList
                    chatKey={chatKey}
                    onClose={() => setShowHistory(false)}
                  />
                </motion.div>
              )}
            </AnimatePresence>

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
