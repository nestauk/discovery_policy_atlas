/**
 * Cognito configuration for the server-side (httpOnly cookie) auth flow.
 *
 * Phase 5 moved token handling server-side: Amplify's Next.js adapter performs
 * the OAuth code exchange in Route Handlers and stores tokens in httpOnly
 * cookies. The client no longer calls `Amplify.configure` or any client-side
 * Amplify API — it talks to our own `/api/auth/*` routes instead.
 *
 * This module builds the `ResourcesConfig` consumed by `createServerRunner`
 * from the `NEXT_PUBLIC_COGNITO_*` env vars (readable on both server and
 * client). OAuth redirect URLs are derived from `AMPLIFY_APP_ORIGIN` and point
 * at the callback routes Amplify generates (`/api/auth/sign-in-callback`,
 * `/api/auth/sign-out-callback`).
 */

import type { ResourcesConfig } from 'aws-amplify'

const PLACEHOLDER_USER_POOL_ID = 'us-east-1_xxxxxxxxx'
const PLACEHOLDER_CLIENT_ID = 'xxxxxxxxxxxxxxxxxxxxxxxxxx'
const PLACEHOLDER_DOMAIN = 'example.auth.us-east-1.amazoncognito.com'

/**
 * Returns the names of any required Cognito env vars that are unset.
 *
 * Used by the client adapter to render a configuration hint instead of
 * silently failing, and to skip session fetches when Cognito isn't set up.
 *
 * Each var must be read with a static `process.env.NEXT_PUBLIC_*` property —
 * Next.js only inlines `NEXT_PUBLIC_` values at compile time for static
 * access; dynamic `process.env[name]` is always undefined in the browser.
 *
 * Returns:
 *     list[str]: Missing env var names; empty when fully configured.
 */
export function getMissingCognitoEnv(): string[] {
  const missing: string[] = []
  if (!process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID?.trim()) {
    missing.push('NEXT_PUBLIC_COGNITO_USER_POOL_ID')
  }
  if (!process.env.NEXT_PUBLIC_COGNITO_USER_POOL_CLIENT_ID?.trim()) {
    missing.push('NEXT_PUBLIC_COGNITO_USER_POOL_CLIENT_ID')
  }
  if (!process.env.NEXT_PUBLIC_COGNITO_DOMAIN?.trim()) {
    missing.push('NEXT_PUBLIC_COGNITO_DOMAIN')
  }
  return missing
}

/**
 * Returns the app origin used to build OAuth redirect URLs.
 *
 * Falls back to the request origin on the client and localhost on the server
 * when `AMPLIFY_APP_ORIGIN` is unset (dev convenience).
 */
function getAppOrigin(): string {
  if (process.env.AMPLIFY_APP_ORIGIN?.trim()) {
    return process.env.AMPLIFY_APP_ORIGIN.trim().replace(/\/$/, '')
  }
  if (typeof window !== 'undefined') {
    return window.location.origin
  }
  return 'http://localhost:3000'
}

/**
 * Builds the Amplify `ResourcesConfig` for the Cognito server runner.
 *
 * When env vars are missing (e.g. running in Clerk mode), syntactically valid
 * placeholders are substituted so `createServerRunner` doesn't throw at module
 * load — the Cognito code paths are never exercised unless Cognito is active.
 *
 * Returns:
 *     ResourcesConfig: Config object accepted by `createServerRunner`.
 */
export function buildCognitoResourceConfig(): ResourcesConfig {
  const userPoolId =
    process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID?.trim() || PLACEHOLDER_USER_POOL_ID
  const userPoolClientId =
    process.env.NEXT_PUBLIC_COGNITO_USER_POOL_CLIENT_ID?.trim() || PLACEHOLDER_CLIENT_ID
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN?.trim() || PLACEHOLDER_DOMAIN

  const origin = getAppOrigin()

  return {
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        loginWith: {
          oauth: {
            domain,
            scopes: ['openid', 'email', 'profile'],
            redirectSignIn: [`${origin}/api/auth/sign-in-callback`],
            redirectSignOut: [`${origin}/api/auth/sign-out-callback`],
            responseType: 'code',
          },
        },
      },
    },
  }
}
