'use client';

/**
 * Clerk-specific token provider implementation.
 */

import { useAuth as useClerkAuth } from '@clerk/nextjs';
import type { AuthTokenProvider } from '../../types';

/**
 * Hook-based token acquisition for Clerk.
 */
export function useAuthToken() {
  const { getToken } = useClerkAuth();
  return { getToken };
}

/**
 * External (non-React) token acquisition for Clerk.
 * Uses window.Clerk global.
 */
export async function getTokenExternal(): Promise<string | null> {
  try {
    if (
      typeof window !== 'undefined' &&
      (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string> } } }).Clerk?.session
    ) {
      const clerkWindow = window as unknown as { Clerk?: { session?: { getToken: () => Promise<string> } } };
      return await clerkWindow.Clerk!.session!.getToken();
    }
  } catch (err) {
    console.error('Failed to get Clerk token from window:', err);
  }
  return null;
}

/**
 * Clerk token provider conforming to AuthTokenProvider interface.
 */
export const clerkTokenProvider: AuthTokenProvider = {
  useAuthToken,
  getTokenExternal,
};

// Re-export Clerk hooks for components that need them directly
export {
  useAuth as useClerkAuth,
  useUser as useClerkUser,
  useOrganization as useClerkOrganization,
  useOrganizationList as useClerkOrganizationList,
  useSession as useClerkSession,
} from '@clerk/nextjs';
