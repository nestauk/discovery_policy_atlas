'use client'

import { Button } from '@/components/ui/button'
import { CircleHelp } from 'lucide-react'

interface ConfirmationCardProps {
  title: string
  description: string
  primaryLabel: string
  secondaryLabel: string
  onPrimary: () => void
  onSecondary: () => void
  disabled?: boolean
}

export function ConfirmationCard({
  title,
  description,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
  disabled,
}: ConfirmationCardProps) {
  return (
    <div className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-start gap-2">
        <CircleHelp className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">{title}</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
          <p className="mt-2 text-xs text-slate-500">
            Ask a question below if you want to check something before deciding.
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={onPrimary} disabled={disabled} className="rounded-full px-4">
          {primaryLabel}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onSecondary}
          disabled={disabled}
          className="rounded-full px-4"
        >
          {secondaryLabel}
        </Button>
      </div>
    </div>
  )
}
