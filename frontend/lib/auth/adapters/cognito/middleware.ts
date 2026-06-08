/**
 * Cognito middleware (Phase 4: pass-through).
 *
 * Amplify keeps tokens in `localStorage`, which the edge runtime cannot
 * read. So protection happens client-side in `app/(main)/layout.tsx`
 * (the `useEffect` that redirects unauthenticated users to `/login`).
 *
 * Phase 5 swaps token storage to an httpOnly cookie set by Next.js Route
 * Handlers; at that point this middleware will inspect the cookie and
 * enforce protection at the edge.
 */

import { NextResponse } from 'next/server'

export function authMiddleware() {
  return NextResponse.next()
}

export const authMiddlewareConfig = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
  ],
}
