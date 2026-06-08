/**
 * Edge middleware dispatcher.
 *
 * Re-exports the adapter selected by `NEXT_PUBLIC_AUTH_PROVIDER`. The
 * provider is resolved at module load time — Next.js middleware can't
 * switch dynamically per request.
 */

import { AUTH_PROVIDER } from './config'
import {
  authMiddleware as clerkMiddleware,
  authMiddlewareConfig as clerkMiddlewareConfig,
} from './adapters/clerk/middleware'
import {
  authMiddleware as cognitoMiddleware,
  authMiddlewareConfig as cognitoMiddlewareConfig,
} from './adapters/cognito/middleware'

function pickMiddleware() {
  if (AUTH_PROVIDER === 'clerk') {
    return { mw: clerkMiddleware, cfg: clerkMiddlewareConfig }
  }
  if (AUTH_PROVIDER === 'cognito') {
    return { mw: cognitoMiddleware, cfg: cognitoMiddlewareConfig }
  }
  throw new Error(
    `Unsupported NEXT_PUBLIC_AUTH_PROVIDER for middleware: ${AUTH_PROVIDER}`
  )
}

const { mw, cfg } = pickMiddleware()

export const authMiddleware = mw
export const authMiddlewareConfig = cfg
