import * as React from 'react'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'

export function Tooltip({ children, content, side = 'top', align = 'center' }: {
  children: React.ReactNode
  content: React.ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
}) {
  return (
    <TooltipPrimitive.Provider>
      <TooltipPrimitive.Root delayDuration={200}>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            align={align}
            className="z-50 max-w-xs rounded-md bg-neutral-900 px-3 py-2 text-xs text-white border border-neutral-700 shadow-lg break-words whitespace-pre-line"
            sideOffset={6}
          >
            {content}
            <TooltipPrimitive.Arrow className="fill-neutral-900" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
} 