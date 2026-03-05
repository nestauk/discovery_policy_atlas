import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest, NextFetchEvent } from "next/server";

/**
 * proxy.ts convention has been adopted replacing middleware.ts
 * Provider-aware middleware
 * Uses NEXT_PUBLIC_AUTH_PROVIDER to determine which auth middleware to apply.
 * 
 * - Clerk: Uses Clerk middleware for session management
 * - Keycloak: Pass-through since Keycloak auth is handled client-side via keycloak-js
 *   and verified backend-side via JWKS
 * 
 * The environment variable must be set or the app will fail at startup.
 */
const authProvider = process.env.NEXT_PUBLIC_AUTH_PROVIDER;

if (!authProvider) {
  throw new Error(
    'NEXT_PUBLIC_AUTH_PROVIDER environment variable is required but not set. ' +
    'Set it to "clerk" or "keycloak".'
  );
}

if (authProvider !== 'clerk' && authProvider !== 'keycloak') {
  throw new Error(
    `Invalid NEXT_PUBLIC_AUTH_PROVIDER value: "${authProvider}". ` +
    'Must be "clerk" or "keycloak".'
  );
}

// Clerk middleware instance (only used when provider is clerk)
const clerkMiddlewareHandler = authProvider === 'clerk' ? clerkMiddleware() : null;

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  if (authProvider === 'clerk' && clerkMiddlewareHandler) {
    // Delegate to Clerk middleware
    return clerkMiddlewareHandler(request, event);
  }
  
  // Keycloak: Pass through
  // Keycloak authentication is handled:
  // - Client-side: via keycloak-js library initialization
  // - Server-side: API routes verify JWT via backend JWKS validation
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
};