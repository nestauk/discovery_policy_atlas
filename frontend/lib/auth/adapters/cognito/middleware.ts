/**
 * Cognito edge middleware (Phase 5: real protection via httpOnly cookies).
 *
 * Reads the auth session from the httpOnly token cookies using Amplify's
 * server context and redirects unauthenticated requests for protected routes
 * to `/login`. Public routes and the `/api/auth/*` flow pass through.
 *
 * `fetchAuthSession` with a `response` context also refreshes tokens and
 * writes the updated cookies back via `Set-Cookie` when needed.
 */

import { fetchAuthSession } from 'aws-amplify/auth/server'
import { NextRequest, NextResponse } from 'next/server'

import { runWithAmplifyServerContext } from './amplifyServerUtils'

const PUBLIC_PATHS = new Set(['/', '/login', '/privacy', '/terms'])

function isPublicRoute(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true
  if (pathname.startsWith('/login/')) return true
  if (pathname.startsWith('/public/')) return true
  // The Amplify auth flow + session endpoint must never be gated.
  if (pathname.startsWith('/api/auth')) return true
  return false
}

export async function authMiddleware(request: NextRequest) {
  if (isPublicRoute(request.nextUrl.pathname)) {
    return NextResponse.next()
  }

  const response = NextResponse.next()

  const authenticated = await runWithAmplifyServerContext({
    nextServerContext: { request, response },
    operation: async (contextSpec) => {
      try {
        const session = await fetchAuthSession(contextSpec)
        return session.tokens?.accessToken !== undefined
      } catch {
        return false
      }
    },
  })

  if (authenticated) {
    return response
  }

  return NextResponse.redirect(new URL('/login', request.url))
}

export const authMiddlewareConfig = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
  ],
}
