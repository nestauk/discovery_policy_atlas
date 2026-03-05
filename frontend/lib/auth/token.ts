'use client';

/**
 * Provider-agnostic token acquisition.
 * Delegates to the appropriate provider based on NEXT_PUBLIC_AUTH_PROVIDER.
 * 
 * Since we need to conditionally export React hooks and can't use dynamic
 * imports at runtime (hooks must be called unconditionally), we import both
 * providers and export the appropriate one based on the environment variable.
 */

import { isClerkProvider } from './provider';
import {
  useAuthToken as useClerkAuthToken,
  getTokenExternal as getClerkTokenExternal,
} from './providers/clerk';
import {
  useAuthToken as useKeycloakAuthToken,
  getTokenExternal as getKeycloakTokenExternal,
} from './providers/keycloak';

// Select implementations based on provider at module load time
const useAuthTokenImpl = isClerkProvider() ? useClerkAuthToken : useKeycloakAuthToken;
const getTokenExternalImpl = isClerkProvider() ? getClerkTokenExternal : getKeycloakTokenExternal;

/**
 * Hook for token acquisition inside React components.
 * Delegates to the configured provider (Clerk or Keycloak).
 */
export const useAuthToken = useAuthTokenImpl;

/**
 * Get token from window/global for non-React contexts (e.g., Zustand stores).
 * Delegates to the configured provider (Clerk or Keycloak).
 */
export const getTokenExternal = getTokenExternalImpl;
