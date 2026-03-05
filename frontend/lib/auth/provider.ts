/**
 * Provider selector for auth.
 * Reads NEXT_PUBLIC_AUTH_PROVIDER and returns the appropriate provider module.
 * 
 * NEXT_PUBLIC_AUTH_PROVIDER is REQUIRED. If not set, the app will fail.
 */

import type { AuthProvider } from './types';
import { VALID_PROVIDERS } from './types';

let cachedProvider: AuthProvider | null = null;

/**
 * Get the configured auth provider.
 * Throws if NEXT_PUBLIC_AUTH_PROVIDER is not set or invalid.
 */
export function getAuthProviderName(): AuthProvider {
  if (cachedProvider) {
    return cachedProvider;
  }

  const provider = process.env.NEXT_PUBLIC_AUTH_PROVIDER?.toLowerCase();
  
  if (!provider) {
    throw new Error(
      'NEXT_PUBLIC_AUTH_PROVIDER environment variable is required. ' +
      `Set it to one of: ${VALID_PROVIDERS.join(', ')}`
    );
  }
  
  if (!VALID_PROVIDERS.includes(provider as AuthProvider)) {
    throw new Error(
      `Invalid NEXT_PUBLIC_AUTH_PROVIDER value: "${provider}". ` +
      `Valid values are: ${VALID_PROVIDERS.join(', ')}`
    );
  }
  
  cachedProvider = provider as AuthProvider;
  return cachedProvider;
}

export function isClerkProvider(): boolean {
  return getAuthProviderName() === 'clerk';
}

export function isKeycloakProvider(): boolean {
  return getAuthProviderName() === 'keycloak';
}

/**
 * Validate Keycloak-specific env vars.
 * Call this when provider is keycloak to ensure required config is present.
 */
export function validateKeycloakConfig(): void {
  const missing: string[] = [];

  if (!process.env.NEXT_PUBLIC_KEYCLOAK_URL) {
    missing.push('NEXT_PUBLIC_KEYCLOAK_URL');
  }
  if (!process.env.NEXT_PUBLIC_KEYCLOAK_REALM) {
    missing.push('NEXT_PUBLIC_KEYCLOAK_REALM');
  }
  if (!process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID) {
    missing.push('NEXT_PUBLIC_KEYCLOAK_CLIENT_ID');
  }

  if (missing.length > 0) {
    throw new Error(
      `Missing required Keycloak environment variables: ${missing.join(', ')}`
    );
  }
}
