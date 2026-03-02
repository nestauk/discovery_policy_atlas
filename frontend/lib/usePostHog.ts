'use client'

import posthog from 'posthog-js'

/**
 * Hook for tracking custom events in PostHog.
 * 
 * Usage:
 *   const { trackEvent } = usePostHogTracking()
 *   trackEvent('button_clicked', { button_name: 'search' })
 */
export function usePostHogTracking() {
  const trackEvent = (eventName: string, properties?: Record<string, unknown>) => {
    // Only capture events on client-side (not during SSR)
    if (typeof window !== 'undefined') {
      posthog.capture(eventName, properties)
    }
  }

  return { trackEvent }
}

