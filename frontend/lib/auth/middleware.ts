/**
 * Edge middleware dispatcher.
 *
 * Re-exports the adapter selected by `NEXT_PUBLIC_AUTH_PROVIDER`. Picks the
 * implementation at module load time — Next.js middleware can't switch
 * dynamically per request.
 */

import { AUTH_PROVIDER } from './config'
import {
  authMiddleware as clerkMiddleware,
  authMiddlewareConfig as clerkMiddlewareConfig,
} from './adapters/clerk/middleware'

if (AUTH_PROVIDER !== 'clerk') {
  throw new Error(
    `Unsupported NEXT_PUBLIC_AUTH_PROVIDER for middleware: ${AUTH_PROVIDER}`
  )
}

export const authMiddleware = clerkMiddleware
export const authMiddlewareConfig = clerkMiddlewareConfig
