'use client'

import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Star } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FeedbackData {
  rating: number
  comment: string
}

interface FeedbackModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (feedback: FeedbackData) => void
  projectTitle: string
  existingFeedback?: FeedbackData | null
  isLoading?: boolean
}

export function FeedbackModal({
  isOpen,
  onClose,
  onSubmit,
  projectTitle,
  existingFeedback,
  isLoading = false
}: FeedbackModalProps) {
  const [rating, setRating] = useState(0)
  const [hoveredRating, setHoveredRating] = useState(0)
  const [comment, setComment] = useState('')

  // Load existing feedback when modal opens
  useEffect(() => {
    if (isOpen && existingFeedback) {
      setRating(existingFeedback.rating)
      setComment(existingFeedback.comment)
    } else if (isOpen && !existingFeedback) {
      setRating(0)
      setComment('')
    }
  }, [isOpen, existingFeedback])

  const handleSubmit = () => {
    if (rating === 0) return // Require at least 1 star
    
    onSubmit({
      rating,
      comment: comment.trim()
    })
  }

  const handleClose = () => {
    setRating(0)
    setHoveredRating(0)
    setComment('')
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold">
            {existingFeedback ? 'Update your feedback' : 'Share your feedback'}
          </DialogTitle>
          <p className="text-sm mt-1">
            How useful were the results for &quot;{projectTitle}&quot;?
          </p>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Star Rating */}
          <div className="space-y-3">
            <div className="flex justify-between gap-2">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  className="flex-1 p-2 rounded transition-colors hover:bg-muted flex justify-center"
                  onMouseEnter={() => setHoveredRating(star)}
                  onMouseLeave={() => setHoveredRating(0)}
                  onClick={() => setRating(star)}
                >
                  <Star
                    className={cn(
                      "h-8 w-8 transition-colors",
                      (hoveredRating >= star || (hoveredRating === 0 && rating >= star))
                        ? "fill-yellow-400 text-yellow-400"
                        : "text-muted-foreground"
                    )}
                  />
                </button>
              ))}
            </div>
            {rating > 0 && (
              <p className="text-xs text-muted-foreground text-center">
                {rating === 1 && "Not useful"}
                {rating === 2 && "Somewhat useful"}
                {rating === 3 && "Moderately useful"}
                {rating === 4 && "Very useful"}
                {rating === 5 && "Extremely useful"}
              </p>
            )}
          </div>

          {/* Comment */}
          <div className="space-y-3">
            <label className="text-sm font-medium pb-1 block">
              Comments (optional)
            </label>
            <Textarea
              placeholder=""
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={4}
              className="resize-none"
            />
            <p className="text-xs text-muted-foreground mt-3 pt-2">
              {comment.length}/500 characters
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={rating === 0 || isLoading || comment.length > 500}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {isLoading ? 'Saving...' : existingFeedback ? 'Update Feedback' : 'Submit Feedback'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}