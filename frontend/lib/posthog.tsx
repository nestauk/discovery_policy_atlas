'use client'

// Import to ensure PostHog is initialized and get config flags
import { POSTHOG_ANONYMOUS } from '../instrumentation-client'
import posthog from 'posthog-js'
import { useEffect, useRef } from 'react'
import { useUser } from '@clerk/nextjs'

/**
 * Wrapper component that identifies users in PostHog when they log in via Clerk.
 * Respects NEXT_PUBLIC_POSTHOG_ANONYMOUS env var — if true, users are never identified.
 */
export function PostHogUserIdentifier({ children }: { children: React.ReactNode }) {
  const { user, isLoaded } = useUser()
  const lastUserIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (!isLoaded) return
    
    const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY
    if (!posthogKey) return

    // If anonymous mode is enabled via env var, never identify users
    if (POSTHOG_ANONYMOUS) {
      return
    }

    const currentUserId = user?.id || null

    // Only call identify/reset if the user ID actually changed
    if (currentUserId === lastUserIdRef.current) {
      return
    }

    lastUserIdRef.current = currentUserId

    if (user) {
      posthog.identify(user.id, {
        email: user.emailAddresses[0]?.emailAddress,
        name: user.fullName || user.firstName || undefined,
      })
    } else {
      posthog.reset()
    }
  }, [user, isLoaded])

  return <>{children}</>
}

