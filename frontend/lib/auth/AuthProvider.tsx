'use client'

import { ReactNode } from 'react'
import { AUTH_PROVIDER } from './config'
import { ClerkAdapter } from './adapters/clerk/ClerkAdapter'

interface AuthProviderProps {
  children: ReactNode
}

/**
 * Picks the configured adapter and wraps the rest of the app in it.
 *
 * The selector reads `NEXT_PUBLIC_AUTH_PROVIDER` once at module load via
 * `./config`. Adapters are responsible for their own provider SDK setup;
 * nothing else in the app should import from `@clerk/nextjs` or
 * `aws-amplify`.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  if (AUTH_PROVIDER === 'clerk') {
    return <ClerkAdapter>{children}</ClerkAdapter>
  }
  // Cognito adapter lands in Phase 4. Treat unknown values as a build error.
  throw new Error(
    `Unsupported NEXT_PUBLIC_AUTH_PROVIDER: ${AUTH_PROVIDER}. Set it to "clerk".`
  )
}
