/**
 * Single-shot Amplify configuration for the Cognito adapter.
 *
 * Reads `NEXT_PUBLIC_COGNITO_*` env vars and calls `Amplify.configure` exactly
 * once. Idempotent so hot-reloads and re-renders don't reconfigure.
 *
 * Tokens are stored in `localStorage` by default — this is the Phase 4 demo
 * setup. Phase 5 swaps this for an httpOnly cookie via Next.js Route
 * Handlers to limit XSS exposure.
 */

import { Amplify } from 'aws-amplify'

let configured = false

function parseRedirectList(
  value: string | undefined,
  fallback: string[]
): string[] {
  if (!value?.trim()) return fallback
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export interface CognitoConfigStatus {
  configured: boolean
  missing: string[]
}

export function configureAmplify(): CognitoConfigStatus {
  if (configured) {
    return { configured: true, missing: [] }
  }

  const userPoolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID
  const userPoolClientId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_CLIENT_ID
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN

  const missing: string[] = []
  if (!userPoolId) missing.push('NEXT_PUBLIC_COGNITO_USER_POOL_ID')
  if (!userPoolClientId) missing.push('NEXT_PUBLIC_COGNITO_USER_POOL_CLIENT_ID')
  if (!domain) missing.push('NEXT_PUBLIC_COGNITO_DOMAIN')
  if (missing.length > 0) {
    return { configured: false, missing }
  }

  const defaultRedirect =
    typeof window !== 'undefined' ? [`${window.location.origin}/`] : ['http://localhost:3000/']

  const redirectSignIn = parseRedirectList(
    process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN,
    defaultRedirect
  )
  const redirectSignOut = parseRedirectList(
    process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_OUT,
    redirectSignIn
  )

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: userPoolId!,
        userPoolClientId: userPoolClientId!,
        loginWith: {
          oauth: {
            domain: domain!,
            scopes: ['openid', 'email', 'profile'],
            redirectSignIn,
            redirectSignOut,
            responseType: 'code',
          },
        },
      },
    },
  })

  configured = true
  return { configured: true, missing: [] }
}
