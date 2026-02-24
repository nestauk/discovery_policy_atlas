'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import ReactDOM from 'react-dom'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useWizard } from './SearchWizard'

// ── Constants ──────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'refine_tutorial_seen'
const SPOTLIGHT_PADDING = 10
const CUTOUT_RADIUS = 8
const TOOLTIP_WIDTH = 288
const TOOLTIP_GAP = 16

type Phase = 'idle' | 'intro' | 1 | 2 | 3

type Placement = 'below' | 'above' | 'above-right'

interface StepConfig {
  selector: string
  placement: Placement
  body: string
  primaryLabel: string
  autoScroll: boolean
  earlyComplete: boolean
}

const STEPS: StepConfig[] = [
  {
    selector: '[data-tutorial="progress-bar"]',
    placement: 'below',
    body: 'Your previous search settings are pre-loaded. Click any step above to jump there and make changes.',
    primaryLabel: 'Next',
    autoScroll: false,
    earlyComplete: true,
  },
  {
    selector: '[data-tutorial="filters-section"]',
    placement: 'above-right',
    body: 'Click any section to edit it directly — try narrowing your geography or time window.',
    primaryLabel: 'Next',
    autoScroll: true,
    earlyComplete: true,
  },
  {
    selector: '[data-tutorial="run-button"]',
    placement: 'above',
    body: "When you're happy with your changes, hit Run to start a new search.",
    primaryLabel: 'Done',
    autoScroll: true,
    earlyComplete: false,
  },
]

// ── localStorage helpers ───────────────────────────────────────────────────────

function getSeenFlag(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function setSeenFlag(): void {
  try {
    localStorage.setItem(STORAGE_KEY, 'true')
  } catch {
    // Ignore — tutorial may re-show in private browsing
  }
}

// ── Clip-path builder ──────────────────────────────────────────────────────────

function buildClipPath(rect: DOMRect): string {
  const p = SPOTLIGHT_PADDING
  const r = CUTOUT_RADIUS
  const W = window.innerWidth
  const H = window.innerHeight

  // Inner rect with padding
  const x = rect.left - p
  const y = rect.top - p
  const w = rect.width + 2 * p
  const h = rect.height + 2 * p

  // Outer rect clockwise, inner rounded rect counter-clockwise → evenodd creates hole
  const outer = `M 0 0 L ${W} 0 L ${W} ${H} L 0 ${H} Z`
  const inner = [
    `M ${x + r} ${y}`,
    `L ${x + w - r} ${y}`,
    `A ${r} ${r} 0 0 1 ${x + w} ${y + r}`,
    `L ${x + w} ${y + h - r}`,
    `A ${r} ${r} 0 0 1 ${x + w - r} ${y + h}`,
    `L ${x + r} ${y + h}`,
    `A ${r} ${r} 0 0 1 ${x} ${y + h - r}`,
    `L ${x} ${y + r}`,
    `A ${r} ${r} 0 0 1 ${x + r} ${y}`,
    'Z',
  ].join(' ')

  return `path(evenodd, '${outer} ${inner}')`
}

// ── Tooltip positioning ────────────────────────────────────────────────────────

const TOOLTIP_HEIGHT_ESTIMATE = 140

function computeTooltipPosition(
  rect: DOMRect,
  placement: Placement,
): React.CSSProperties {
  const p = SPOTLIGHT_PADDING
  const w = TOOLTIP_WIDTH
  const minX = 16
  const maxX = window.innerWidth - w - 16
  const vh = window.innerHeight

  const centerX = Math.min(Math.max(rect.left + rect.width / 2 - w / 2, minX), maxX)

  const base = { position: 'fixed' as const, width: w, zIndex: 9999 }

  if (placement === 'below') {
    const top = rect.bottom + p + TOOLTIP_GAP
    // If tooltip would overflow bottom, switch to above
    if (top + TOOLTIP_HEIGHT_ESTIMATE > vh - 16) {
      return computeTooltipPosition(rect, 'above')
    }
    return { ...base, top, left: centerX }
  }

  if (placement === 'above') {
    const top = rect.top - p - TOOLTIP_GAP - TOOLTIP_HEIGHT_ESTIMATE
    return { ...base, top: Math.max(top, 16), left: centerX }
  }

  if (placement === 'above-right') {
    const top = rect.top - p - TOOLTIP_GAP - TOOLTIP_HEIGHT_ESTIMATE
    const left = Math.min(rect.right - w, maxX)
    return { ...base, top: Math.max(top, 16), left: Math.max(left, minX) }
  }

  // 'above' fallback
  const top = rect.top - p - TOOLTIP_GAP - TOOLTIP_HEIGHT_ESTIMATE
  return { ...base, top: Math.max(top, 16), left: centerX }
}

// ── Auto-scroll helper ─────────────────────────────────────────────────────────

function scrollToElement(element: Element): Promise<void> {
  return new Promise((resolve) => {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          observer.disconnect()
          clearTimeout(fallback)
          setTimeout(resolve, 50)
        }
      },
      { threshold: 0.8 },
    )
    observer.observe(element)

    const fallback = setTimeout(() => {
      observer.disconnect()
      resolve()
    }, 600)
  })
}

// ── Focus trap hook ─────────────────────────────────────────────────────────────

function useFocusTrap(
  ref: React.RefObject<HTMLElement | null>,
  active: boolean,
  onEscape: () => void,
) {
  useEffect(() => {
    if (!active || !ref.current) return
    const container = ref.current

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onEscape()
        return
      }
      if (e.key !== 'Tab') return
      const focusable = container.querySelectorAll<HTMLElement>(
        'button, [href], [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    container.querySelector<HTMLElement>('button')?.focus()
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [ref, active, onEscape])
}

// ── Component ──────────────────────────────────────────────────────────────────

export function RefineTutorial() {
  const parentProjectId = useWizard((s) => s.parentProjectId)
  const [phase, setPhase] = useState<Phase>('idle')
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const currentStepConfig = typeof phase === 'number' ? STEPS[phase - 1] : null

  // ── Trigger on mount ───────────────────────────────────────────────────────
  useEffect(() => {
    if (parentProjectId && !getSeenFlag()) {
      setPhase('intro')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Check only on mount

  // ── Complete/dismiss ───────────────────────────────────────────────────────
  const complete = useCallback(() => {
    setSeenFlag()
    setPhase('idle')
    setTargetRect(null)
  }, [])

  // ── Advance to a step ──────────────────────────────────────────────────────
  const advanceTo = useCallback(
    async (step: 1 | 2 | 3) => {
      const config = STEPS[step - 1]
      const el = document.querySelector(config.selector)

      if (!el) {
        // Target not in DOM — skip
        if (step < 3) advanceTo((step + 1) as 2 | 3)
        else complete()
        return
      }

      if (config.autoScroll) {
        await scrollToElement(el)
      }

      setTargetRect(el.getBoundingClientRect())
      setPhase(step)
    },
    [complete],
  )

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleNext = useCallback(() => {
    if (typeof phase === 'number' && phase < 3) advanceTo((phase + 1) as 2 | 3)
    else complete()
  }, [phase, advanceTo, complete])

  // ── Early completion: click on highlighted target ──────────────────────────
  useEffect(() => {
    if (typeof phase !== 'number') return
    const config = STEPS[phase - 1]
    if (!config.earlyComplete) return

    const el = document.querySelector(config.selector)
    if (!el) return

    const handler = () => complete()
    el.addEventListener('click', handler, { capture: true })
    return () => el.removeEventListener('click', handler, { capture: true })
  }, [phase, complete])

  // ── Update rect on scroll/resize ───────────────────────────────────────────
  useEffect(() => {
    if (typeof phase !== 'number' || !currentStepConfig) return

    const update = () => {
      const el = document.querySelector(currentStepConfig.selector)
      if (el) setTargetRect(el.getBoundingClientRect())
    }

    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, { passive: true })
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update)
    }
  }, [phase, currentStepConfig])

  // ── Focus trap: keep Tab within tooltip ────────────────────────────────────
  useFocusTrap(tooltipRef, typeof phase === 'number', complete)

  // ── Render nothing when idle ───────────────────────────────────────────────
  if (phase === 'idle') return null

  return (
    <>
      {/* Intro Dialog */}
      <Dialog
        open={phase === 'intro'}
        onOpenChange={(open) => {
          if (!open) complete()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>First time refining a search?</DialogTitle>
            <DialogDescription>
              Take a quick 3-step tour to learn how to tweak your search settings
              and re-run.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" onClick={complete}>
              No thanks
            </Button>
            <Button onClick={() => advanceTo(1)}>Show me</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Spotlight + Tooltip */}
      {typeof phase === 'number' &&
        targetRect &&
        ReactDOM.createPortal(
          <>
            {/* Dark overlay with spotlight cutout */}
            <div
              aria-hidden="true"
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 9998,
                backgroundColor: 'rgba(0, 0, 0, 0.5)',
                clipPath: buildClipPath(targetRect),
                pointerEvents: 'none',
              }}
            />

            {/* Clickable backdrop outside the cutout to prevent page interaction */}
            <div
              aria-hidden="true"
              onClick={(e) => e.stopPropagation()}
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 9997,
              }}
            />

            {/* Tooltip panel */}
            <div style={computeTooltipPosition(targetRect, currentStepConfig!.placement)}>
              <div
                ref={tooltipRef}
                role="dialog"
                aria-modal="true"
                aria-label={`Tutorial step ${phase} of 3`}
                className="rounded-xl border border-gray-200 bg-white p-4 shadow-xl"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Step {phase} of 3
                </p>
                <p className="mt-2 text-sm text-gray-900">{currentStepConfig!.body}</p>
                <div className="mt-4 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={complete}
                    className="text-xs text-gray-500 underline-offset-2 hover:underline"
                  >
                    Skip tutorial
                  </button>
                  <Button size="sm" onClick={handleNext}>
                    {currentStepConfig!.primaryLabel}
                  </Button>
                </div>
              </div>
            </div>
          </>,
          document.body,
        )}
    </>
  )
}
