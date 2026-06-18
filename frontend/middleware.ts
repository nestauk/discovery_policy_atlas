import { AUTH_PROVIDER } from '@/lib/auth/config'
import { authMiddleware as clerkMiddleware } from '@/lib/auth/adapters/clerk/middleware'
import { authMiddleware as cognitoMiddleware } from '@/lib/auth/adapters/cognito/middleware'

const middleware = AUTH_PROVIDER === 'cognito' ? cognitoMiddleware : clerkMiddleware

export default middleware

// Keep matcher local so Next can statically analyze it.
export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
