/**
 * Shared auth types for provider-agnostic authentication.
 */

export type AuthProvider = 'clerk' | 'keycloak';

/** Valid provider names */
export const VALID_PROVIDERS: AuthProvider[] = ['clerk', 'keycloak'];

export interface AuthUser {
  id: string;
  email?: string | null;
  fullName?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  imageUrl?: string | null;
}

export interface AuthOrganization {
  id: string;
  name: string;
  slug?: string;
}

export interface AuthSession {
  getToken: (options?: { skipCache?: boolean }) => Promise<string | null>;
}

/**
 * Provider interface for token acquisition.
 * Each provider must implement these.
 */
export interface AuthTokenProvider {
  /** Get token inside a React component (hook-based) */
  useAuthToken: () => { getToken: () => Promise<string | null> };
  /** Get token from window/global for non-React contexts */
  getTokenExternal: () => Promise<string | null>;
}

/** Return type for useUser hook */
export interface AuthUserHookReturn {
  user: AuthUser | null;
  isLoaded: boolean;
  isSignedIn: boolean;
}

/** Return type for useOrganization hook */
export interface AuthOrganizationHookReturn {
  organization: AuthOrganization | null;
  isLoaded: boolean;
}

/** Type for useUser hook function */
export type AuthUserHook = () => AuthUserHookReturn;

/** Type for useOrganization hook function */
export type AuthOrganizationHook = () => AuthOrganizationHookReturn;

/**
 * Provider interface for user context.
 */
export interface AuthUserProvider {
  useUser: AuthUserHook;
  useOrganization: AuthOrganizationHook;
}
