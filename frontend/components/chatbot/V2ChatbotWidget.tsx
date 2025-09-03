'use client'

import { Bot, X, MessageCircle } from 'lucide-react'
import { Card, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { AnimatePresence, motion } from 'framer-motion'
import { V2ChatInterface } from './V2ChatInterface'
import { useV2ChatStore } from '@/lib/v2ChatStore'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'


interface V2ChatbotWidgetProps {
  className?: string
}

export function V2ChatbotWidget({ className = "" }: V2ChatbotWidgetProps) {
  const { isOpen, setIsOpen } = useV2ChatStore()
  const { activeProject } = useAnalysisProjectStore()

  if (!activeProject) {
    return null // Don't show widget if no project is selected
  }

  return (
    <>
      {/* Floating Chat Button */}
      <AnimatePresence>
        {!isOpen && (
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

      {/* Chat Widget */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ scale: 0, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0, opacity: 0, y: 20 }}
            className={`fixed bottom-6 right-6 z-50 ${className}`}
          >
            <Card className="w-96 h-[500px] shadow-xl border-0">
              <CardHeader className="p-3 bg-blue-600 text-white">
                <div className="flex items-center justify-between">
                  <div className="flex items-end gap-2">
                    <div className="w-10 h-10 bg-white/0 rounded-full flex items-center justify-center">
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
              </CardHeader>
              
              <div className="h-[420px]">
                <V2ChatInterface 
                  placeholder="Ask about the evidence..."
                  className="h-full"
                  showHeader={false}
                />
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}