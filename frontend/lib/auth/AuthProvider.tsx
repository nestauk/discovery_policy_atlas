'use client'

import { ReactNode } from 'react'
import dynamic from 'next/dynamic'
import { AUTH_PROVIDER } from './config'

/**
 * Picks the configured adapter and wraps the rest of the app in it.
 *
 * The selector reads `NEXT_PUBLIC_AUTH_PROVIDER` once at module load via
 * `./config`. Each adapter is lazy-loaded so the inactive provider's SDK
 * never runs (e.g. Clerk's React SDK doesn't try to read a publishable
 * key when we're in Cognito mode).
 */

const ClerkAdapter = dynamic(
  () => import('./adapters/clerk/ClerkAdapter').then((m) => m.ClerkAdapter),
  { ssr: true }
)

const CognitoAdapter = dynamic(
  () => import('./adapters/cognito/CognitoAdapter').then((m) => m.CognitoAdapter),
  { ssr: false }
)

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  if (AUTH_PROVIDER === 'clerk') {
    return <ClerkAdapter>{children}</ClerkAdapter>
  }
  if (AUTH_PROVIDER === 'cognito') {
    return <CognitoAdapter>{children}</CognitoAdapter>
  }
  throw new Error(
    `Unsupported NEXT_PUBLIC_AUTH_PROVIDER: ${AUTH_PROVIDER}. Set it to "clerk" or "cognito".`
  )
}
