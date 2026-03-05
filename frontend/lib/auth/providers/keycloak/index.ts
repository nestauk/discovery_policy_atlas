'use client';

/**
 * Keycloak-specific token provider implementation.
 */

import { getKeycloakInstance } from './client';
import type { AuthTokenProvider } from '../../types';

/**
 * Hook-based token acquisition for Keycloak.
 * Returns the current access token from the Keycloak instance.
 */
export function useAuthToken() {
  const keycloak = getKeycloakInstance();
  
  return {
    getToken: async (): Promise<string | null> => {
      if (!keycloak.authenticated) {
        return null;
      }
      
      // Refresh token if it expires within 30 seconds
      try {
        await keycloak.updateToken(30);
      } catch (err) {
        console.error('Failed to refresh Keycloak token:', err);
        return null;
      }
      
      return keycloak.token ?? null;
    },
  };
}

/**
 * External (non-React) token acquisition for Keycloak.
 * Uses the global Keycloak instance.
 */
export async function getTokenExternal(): Promise<string | null> {
  const keycloak = getKeycloakInstance();
  
  if (!keycloak.authenticated) {
    return null;
  }
  
  try {
    await keycloak.updateToken(30);
  } catch (err) {
    console.error('Failed to refresh Keycloak token (external):', err);
    return null;
  }
  
  return keycloak.token ?? null;
}

/**
 * Keycloak token provider conforming to AuthTokenProvider interface.
 */
export const keycloakTokenProvider: AuthTokenProvider = {
  useAuthToken,
  getTokenExternal,
};
