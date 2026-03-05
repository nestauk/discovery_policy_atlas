'use client';

/**
 * Keycloak-specific hook wrappers that conform to provider-agnostic interfaces.
 */

import { useState, useEffect } from 'react';
import { getKeycloakInstance } from './client';
import type { AuthUser, AuthOrganization } from '../../types';

/**
 * Parse Keycloak token claims into AuthUser format.
 */
function parseUserFromToken(keycloak: ReturnType<typeof getKeycloakInstance>): AuthUser | null {
  if (!keycloak.authenticated || !keycloak.tokenParsed) {
    return null;
  }

  const token = keycloak.tokenParsed as Record<string, unknown>;

  return {
    id: (token.sub as string) ?? '',
    email: (token.email as string) ?? null,
    fullName: (token.name as string) ?? null,
    firstName: (token.given_name as string) ?? null,
    lastName: (token.family_name as string) ?? null,
    imageUrl: null, // Keycloak doesn't provide avatar by default
  };
}

/**
 * Provider-agnostic user hook backed by Keycloak.
 */
export function useUser(): {
  user: AuthUser | null;
  isLoaded: boolean;
  isSignedIn: boolean;
} {
  const keycloak = getKeycloakInstance();
  const [isLoaded, setIsLoaded] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isSignedIn, setIsSignedIn] = useState(false);

  useEffect(() => {
    // Update state when Keycloak auth state changes
    const updateState = () => {
      setUser(parseUserFromToken(keycloak));
      setIsSignedIn(!!keycloak.authenticated);
      setIsLoaded(true);
    };

    // Check if already initialized
    if (keycloak.authenticated !== undefined) {
      updateState();
    }

    // Listen for auth events
    keycloak.onAuthSuccess = updateState;
    keycloak.onAuthLogout = updateState;
    keycloak.onAuthRefreshSuccess = updateState;
    keycloak.onAuthRefreshError = () => {
      setUser(null);
      setIsSignedIn(false);
    };

    return () => {
      keycloak.onAuthSuccess = undefined;
      keycloak.onAuthLogout = undefined;
      keycloak.onAuthRefreshSuccess = undefined;
      keycloak.onAuthRefreshError = undefined;
    };
  }, [keycloak]);

  return { user, isLoaded, isSignedIn };
}

/**
 * Provider-agnostic organization hook backed by Keycloak.
 * 
 * Keycloak uses groups/roles instead of organizations.
 * This is a simplified implementation - extend as needed for your Keycloak setup.
 */
export function useOrganization(): {
  organization: AuthOrganization | null;
  isLoaded: boolean;
} {
  const keycloak = getKeycloakInstance();
  const [isLoaded, setIsLoaded] = useState(false);
  const [organization, setOrganization] = useState<AuthOrganization | null>(null);

  useEffect(() => {
    const updateState = () => {
      if (!keycloak.authenticated || !keycloak.tokenParsed) {
        setOrganization(null);
        setIsLoaded(true);
        return;
      }

      const token = keycloak.tokenParsed as Record<string, unknown>;
      
      // Try to extract organization from token claims
      // Customize this based on your Keycloak configuration
      // Common patterns: azp (authorized party), groups, resource_access
      const orgId = (token.azp as string) ?? null;
      const groups = (token.groups as string[]) ?? [];
      
      if (orgId || groups.length > 0) {
        setOrganization({
          id: orgId ?? groups[0] ?? '',
          name: orgId ?? groups[0] ?? 'Default Organization',
          slug: orgId?.toLowerCase().replace(/\s+/g, '-'),
        });
      } else {
        setOrganization(null);
      }
      
      setIsLoaded(true);
    };

    if (keycloak.authenticated !== undefined) {
      updateState();
    }

    keycloak.onAuthSuccess = updateState;
    keycloak.onAuthLogout = () => {
      setOrganization(null);
      setIsLoaded(true);
    };

    return () => {
      keycloak.onAuthSuccess = undefined;
      keycloak.onAuthLogout = undefined;
    };
  }, [keycloak]);

  return { organization, isLoaded };
}
