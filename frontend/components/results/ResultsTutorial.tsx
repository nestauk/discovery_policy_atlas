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

const STORAGE_KEY = 'results_tutorial_seen'
const SPOTLIGHT_PADDING = 10
const CUTOUT_RADIUS = 8
const TOOLTIP_WIDTH = 320
const TOOLTIP_GAP = 16
const STEP_RENDER_DELAY_MS = 250
const STEP_TARGET_TIMEOUT_MS = 7000
const STEP_QUERY_INTERVAL_MS = 120

type Phase = 'idle' | 'intro' | 1 | 2 | 3 | 4
type Placement = 'below' | 'above'

interface StepConfig {
  selector: string
  fallbackSelector?: string
  placement: Placement
  body: string
  primaryLabel: string
  action?: (context: StepActionContext) => Promise<void>
}

interface StepActionContext {
  onShowSummary: () => void
  onShowEvidenceInterventions: () => void
  onShowEvidenceDocuments: () => void
}

interface ResultsTutorialProps {
  enabled: boolean
  onShowSummary: () => void
  onShowEvidenceInterventions: () => void
  onShowEvidenceDocuments: () => void
}

const STEPS: StepConfig[] = [
  {
    selector: '[data-tutorial="evidence-base-card"]',
    placement: 'below',
    body: 'This card summarises the evidence behind your briefing, including source volume, evidence types, and geographic coverage.',
    primaryLabel: 'Next',
    action: async ({ onShowSummary }) => {
      onShowSummary()
    },
  },
  {
    selector: '[data-tutorial="citation-context-panel"]',
    fallbackSelector: '[data-tutorial="citation-link"]',
    placement: 'below',
    body: 'Citations are clickable. We have opened one now so you can see its context panel, supporting quote, and source quality details.',
    primaryLabel: 'Next',
    action: async ({ onShowSummary }) => {
      onShowSummary()
      await sleep(STEP_RENDER_DELAY_MS)
      const inspectableCitation = document.querySelector(
        '[data-tutorial="citation-link"][data-citation-inspectable="true"]',
      ) as HTMLElement | null
      inspectableCitation?.click()
    },
  },
  {
    selector: '[data-tutorial="theme-detail-view"]',
    fallbackSelector: '[data-tutorial="interventions-list"]',
    placement: 'above',
    body: 'Intervention themes are clickable. We have opened one to show detailed outcomes, implementation considerations, and risk assessments.',
    primaryLabel: 'Next',
    action: async ({ onShowEvidenceInterventions }) => {
      onShowEvidenceInterventions()
      const firstTheme = (await waitForSelector(
        '[data-tutorial="intervention-theme-row"]',
        2500,
      )) as HTMLElement | null
      firstTheme?.click()
    },
  },
  {
    selector: '[data-tutorial="documents-table"]',
    placement: 'above',
    body: 'The Documents view contains the full evidence base, with relevance, evidence categories, and impact scores for each source.',
    primaryLabel: 'Done',
    action: async ({ onShowEvidenceDocuments }) => {
      onShowEvidenceDocuments()
    },
  },
]

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
    // Ignore storage failures
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForSelector(selector: string, timeoutMs: number = STEP_TARGET_TIMEOUT_MS): Promise<Element | null> {
  const startedAt = Date.now()
  while (Date.now() - startedAt <= timeoutMs) {
    const element = document.querySelector(selector)
    if (element) return element
    await sleep(STEP_QUERY_INTERVAL_MS)
  }
  return null
}

function buildClipPath(rect: DOMRect): string {
  const p = SPOTLIGHT_PADDING
  const r = CUTOUT_RADIUS
  const W = window.innerWidth
  const H = window.innerHeight
  const x = rect.left - p
  const y = rect.top - p
  const w = rect.width + 2 * p
  const h = rect.height + 2 * p
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

const TOOLTIP_HEIGHT_ESTIMATE = 140

function computeTooltipPosition(rect: DOMRect, placement: Placement): React.CSSProperties {
  const p = SPOTLIGHT_PADDING
  const w = TOOLTIP_WIDTH
  const minX = 16
  const maxX = window.innerWidth - w - 16
  const vh = window.innerHeight
  const centerX = Math.min(Math.max(rect.left + rect.width / 2 - w / 2, minX), maxX)
  const base = { position: 'fixed' as const, width: w, zIndex: 9999 }

  if (placement === 'below') {
    const top = rect.bottom + p + TOOLTIP_GAP
    if (top + TOOLTIP_HEIGHT_ESTIMATE > vh - 16) {
      return computeTooltipPosition(rect, 'above')
    }
    return { ...base, top, left: centerX }
  }

  const top = rect.top - p - TOOLTIP_GAP - TOOLTIP_HEIGHT_ESTIMATE
  return { ...base, top: Math.max(top, 16), left: centerX }
}

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

function useFocusTrap(ref: React.RefObject<HTMLElement | null>, active: boolean, onEscape: () => void) {
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
      const focusable = container.querySelectorAll<HTMLElement>('button, [href], [tabindex]:not([tabindex="-1"])')
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

export function ResultsTutorial({
  enabled,
  onShowSummary,
  onShowEvidenceInterventions,
  onShowEvidenceDocuments,
}: ResultsTutorialProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const currentStepConfig = typeof phase === 'number' ? STEPS[phase - 1] : null

  useEffect(() => {
    if (enabled && !getSeenFlag()) {
      setPhase('intro')
    }
  }, [enabled])

  const complete = useCallback(() => {
    setSeenFlag()
    setPhase('idle')
    setTargetRect(null)
  }, [])

  const prepareStepTarget = useCallback(
    async (step: 1 | 2 | 3 | 4): Promise<Element | null> => {
      const config = STEPS[step - 1]
      if (config.action) {
        await config.action({
          onShowSummary,
          onShowEvidenceInterventions,
          onShowEvidenceDocuments,
        })
      }
      await sleep(STEP_RENDER_DELAY_MS)
      const primaryTarget = await waitForSelector(config.selector)
      if (primaryTarget) return primaryTarget
      if (config.fallbackSelector) {
        return waitForSelector(config.fallbackSelector, 2000)
      }
      return null
    },
    [onShowSummary, onShowEvidenceInterventions, onShowEvidenceDocuments],
  )

  const advanceTo = useCallback(
    async (step: 1 | 2 | 3 | 4) => {
      const el = await prepareStepTarget(step)
      if (!el) {
        complete()
        return
      }

      await scrollToElement(el)
      setTargetRect(el.getBoundingClientRect())
      setPhase(step)
    },
    [complete, prepareStepTarget],
  )

  const handleNext = useCallback(() => {
    if (typeof phase === 'number' && phase < 4) {
      advanceTo((phase + 1) as 2 | 3 | 4)
    } else {
      complete()
    }
  }, [phase, advanceTo, complete])

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

  useFocusTrap(tooltipRef, typeof phase === 'number', complete)

  if (phase === 'idle') return null

  return (
    <>
      <Dialog
        open={phase === 'intro'}
        onOpenChange={(open) => {
          if (!open) complete()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>First time viewing results?</DialogTitle>
            <DialogDescription>
              Take a quick 4-step tour to understand the key outputs and where to inspect the evidence.
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

      {typeof phase === 'number' &&
        targetRect &&
        ReactDOM.createPortal(
          <>
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
            <div
              aria-hidden="true"
              onClick={(e) => e.stopPropagation()}
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 9997,
              }}
            />
            <div style={computeTooltipPosition(targetRect, currentStepConfig!.placement)}>
              <div
                ref={tooltipRef}
                role="dialog"
                aria-modal="true"
                aria-label={`Tutorial step ${phase} of 4`}
                className="rounded-xl border border-gray-200 bg-white p-4 shadow-xl"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Step {phase} of 4</p>
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
