'use client';

/**
 * Provider-agnostic auth hooks.
 * Delegates to the appropriate provider based on NEXT_PUBLIC_AUTH_PROVIDER.
 * 
 * Since we need to conditionally export React hooks and can't use dynamic
 * imports at runtime (hooks must be called unconditionally), we import both
 * providers and export the appropriate one based on the environment variable.
 */

import { isClerkProvider } from './provider';
import {
  useUser as useClerkUser,
  useOrganization as useClerkOrganization,
} from './providers/clerk/hooks';
import {
  useUser as useKeycloakUser,
  useOrganization as useKeycloakOrganization,
} from './providers/keycloak/hooks';

// Select implementations based on provider at module load time
const useUserImpl = isClerkProvider() ? useClerkUser : useKeycloakUser;
const useOrganizationImpl = isClerkProvider() ? useClerkOrganization : useKeycloakOrganization;

/**
 * Provider-agnostic user hook.
 * Delegates to the configured provider (Clerk or Keycloak).
 */
export const useAuthUser = useUserImpl;

/**
 * Provider-agnostic organization hook.
 * Delegates to the configured provider (Clerk or Keycloak).
 */
export const useAuthOrganization = useOrganizationImpl;

// Legacy aliases for existing code
export const useUser = useAuthUser;
export const useOrganization = useAuthOrganization;