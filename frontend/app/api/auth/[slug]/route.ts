/**
 * Cognito auth Route Handlers (server-side httpOnly flow).
 *
 * Amplify generates the sign-in / sign-out / callback endpoints under this
 * dynamic segment:
 *   /api/auth/sign-in            -> redirect to Cognito Managed Login
 *   /api/auth/sign-in-callback   -> exchange code, set httpOnly token cookies
 *   /api/auth/sign-out           -> revoke tokens, clear cookies
 *   /api/auth/sign-out-callback  -> finalise sign-out
 *
 * `createAuthRouteHandlers` reads `AMPLIFY_APP_ORIGIN` when constructed, so it
 * is only built when Cognito is the active provider. In Clerk mode this route
 * 404s and never requires Cognito/Amplify env vars (keeps builds green).
 */

import { NextResponse } from 'next/server'

import { AUTH_PROVIDER } from '@/lib/auth/config'
import { createAuthRouteHandlers } from '@/lib/auth/adapters/cognito/amplifyServerUtils'

export const GET =
  AUTH_PROVIDER === 'cognito'
    ? createAuthRouteHandlers({
        redirectOnSignInComplete: '/projects',
        redirectOnSignOutComplete: '/login',
      })
    : () => NextResponse.json({ error: 'Not found' }, { status: 404 })
