import posthog from 'posthog-js'

// Environment variable flags (set in .env.local)
// NEXT_PUBLIC_POSTHOG_SESSION_RECORDING=false -> Disable session recording
export const POSTHOG_SESSION_RECORDING = process.env.NEXT_PUBLIC_POSTHOG_SESSION_RECORDING !== 'false'

// Prevent multiple initializations if this module is imported multiple times
let initialized = false

// Only initialize on client-side (not during SSR)
if (typeof window !== 'undefined' && !initialized) {
  const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY
  const posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://eu.i.posthog.com'

  if (posthogKey) {
    initialized = true
    posthog.init(posthogKey, {
      api_host: posthogHost,
      defaults: '2025-11-30',
      person_profiles: 'always',
      autocapture: true,
      capture_pageview: true,
      capture_pageleave: true,
      disable_session_recording: !POSTHOG_SESSION_RECORDING,
      session_recording: {
        maskAllInputs: true,
        maskTextSelector: '*',
        maskTextFn: () => '●●●●●',
        blockSelector: '[data-posthog-block]',
        recordCrossOriginIframes: false,
      },
      loaded: () => {
        if (process.env.NODE_ENV === 'development') {
          console.log('[PostHog] Initialized', {
            sessionRecording: POSTHOG_SESSION_RECORDING,
          })
        }
      },
    })
  }
}

