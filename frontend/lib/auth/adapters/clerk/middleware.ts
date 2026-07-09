import {
  clerkMiddleware,
  createRouteMatcher,
} from '@clerk/nextjs/server'

const isPublicRoute = createRouteMatcher([
  '/public/(.*)',
  '/login',
  '/login/(.*)',
  '/sign-in',
  '/sign-in/(.*)',
  '/sign-up',
  '/sign-up/(.*)',
  '/',
  '/privacy',
  '/terms',
])

export const authMiddleware = clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect()
  }
})

export const authMiddlewareConfig = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
