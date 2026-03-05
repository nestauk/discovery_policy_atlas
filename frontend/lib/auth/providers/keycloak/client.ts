'use client';

/**
 * Keycloak client singleton.
 * Initializes once and provides the Keycloak instance for auth operations.
 */

import Keycloak from 'keycloak-js';
import { isKeycloakProvider, validateKeycloakConfig } from '../../provider';

// Validate config only when Keycloak is the selected provider.
if (isKeycloakProvider()) {
  validateKeycloakConfig();
}

function getKeycloakConfig() {
  validateKeycloakConfig();
  return {
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL!,
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM!,
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID!,
  };
}

// Create singleton instance
let keycloakInstance: Keycloak | null = null;
let initPromise: Promise<boolean> | null = null;
let isInitialized = false;

type LoginOptions = Parameters<Keycloak['login']>[0];
type RegisterOptions = Parameters<Keycloak['register']>[0];
type LogoutOptions = Parameters<Keycloak['logout']>[0];

export function getKeycloakInstance(): Keycloak {
  if (!keycloakInstance) {
    const instance = new Keycloak(getKeycloakConfig());
    if (!instance) {
      throw new Error(
        'Keycloak instance could not be created. Check NEXT_PUBLIC_KEYCLOAK_* environment variables.'
      );
    }
    keycloakInstance = instance;
  }
  return keycloakInstance;
}

/**
 * Initialize Keycloak. Safe to call multiple times - only initializes once.
 * Returns a promise that resolves when init is complete.
 */
export function initKeycloak(): Promise<boolean> {
  if (initPromise) {
    return initPromise;
  }

  const keycloak = getKeycloakInstance();

  // Already initialized
  if (keycloak.authenticated !== undefined) {
    isInitialized = true;
    return Promise.resolve(keycloak.authenticated);
  }

  const config = getKeycloakConfig();
  const initOptions = {
    onLoad: 'check-sso' as const,
    pkceMethod: 'S256' as const,
    silentCheckSsoRedirectUri:
      typeof window !== 'undefined'
        ? `${window.location.origin}/silent-check-sso.html`
        : undefined,
    checkLoginIframe: false,
  };

  initPromise = keycloak
    .init(initOptions)
    .then((authenticated) => {
      isInitialized = true;
      return authenticated;
    })
    .catch((err) => {
      const errorDetails = err instanceof Error
        ? { message: err.message, name: err.name, stack: err.stack }
        : { rawError: err };

      console.error('Keycloak init failed:', {
        error: errorDetails,
        config: {
          url: config.url,
          realm: config.realm,
          clientId: config.clientId,
        },
        initOptions,
        browserOrigin: typeof window !== 'undefined' ? window.location.origin : 'N/A (SSR)',
        // Include any extra properties from the error object
        ...(typeof err === 'object' && err !== null
          ? Object.fromEntries(
              Object.entries(err).filter(
                ([key]) => !['message', 'name', 'stack'].includes(key)
              )
            )
          : {}),
      });
      isInitialized = true; // Mark as initialized even on failure to avoid retries
      return false;
    });

  return initPromise;
}

/**
 * Check if Keycloak has been initialized.
 */
export function isKeycloakInitialized(): boolean {
  return isInitialized;
}

/**
 * Wait for Keycloak to be initialized, then call login.
 */
export async function login(options?: LoginOptions): Promise<void> {
  const initialized = await initKeycloak();
  if (!initialized) {
    throw new Error('Keycloak init failed. Cannot perform login.');
  }
  const keycloak = getKeycloakInstance();
  if (!keycloak?.login) {
    throw new Error('Keycloak login is unavailable. Ensure the client is initialized.');
  }
  await keycloak.login(options);
}

/**
 * Wait for Keycloak to be initialized, then call register.
 */
export async function register(options?: RegisterOptions): Promise<void> {
  const initialized = await initKeycloak();
  if (!initialized) {
    throw new Error('Keycloak init failed. Cannot perform registration.');
  }
  const keycloak = getKeycloakInstance();
  if (!keycloak?.register) {
    throw new Error('Keycloak register is unavailable. Ensure the client is initialized.');
  }
  await keycloak.register(options);
}

/**
 * Wait for Keycloak to be initialized, then call logout.
 */
export async function logout(options?: LogoutOptions): Promise<void> {
  const initialized = await initKeycloak();
  if (!initialized) {
    throw new Error('Keycloak init failed. Cannot perform logout.');
  }
  const keycloak = getKeycloakInstance();
  if (!keycloak?.logout) {
    throw new Error('Keycloak logout is unavailable. Ensure the client is initialized.');
  }
  const fallbackOptions = {
    redirectUri: window.location.origin,
  };
  await keycloak.logout(options ?? fallbackOptions);
}

// Export default for convenience
export default getKeycloakInstance();
