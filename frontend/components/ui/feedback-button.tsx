'use client'

import { Button } from '@/components/ui/button'
import { MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FeedbackButtonProps {
  onClick: () => void
  hasFeedback?: boolean
  className?: string
}

export function FeedbackButton({ onClick, hasFeedback = false, className }: FeedbackButtonProps) {
  return (
    <Button
      onClick={onClick}
      className={cn(
        "w-full justify-start h-auto p-3 text-left relative overflow-hidden",
        "bg-blue-600 hover:bg-blue-700 text-white",
        "before:absolute before:inset-0 before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent",
        "before:translate-x-[-100%] before:animate-[shimmer_2s_ease-in-out_infinite]",
        "transition-all duration-200",
        hasFeedback && "ring-2 ring-blue-300 ring-offset-2",
        className
      )}
    >
      <MessageSquare className="mr-3 h-4 w-4" />
      <div className="font-medium text-sm">
        {hasFeedback ? 'Update Feedback' : 'Share Feedback'}
      </div>
      {hasFeedback && (
        <div className="ml-auto">
          <div className="w-2 h-2 bg-blue-200 rounded-full" />
        </div>
      )}
    </Button>
  )
}