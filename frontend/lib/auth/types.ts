/**
 * Shared types for the auth abstraction.
 *
 * Components and pages depend only on these types — never on Clerk or
 * Cognito SDK types directly. Adapters under `./adapters/*` translate
 * provider-specific shapes into these.
 */

export interface AuthUser {
  id: string;
  email?: string;
  name?: string;
  firstName?: string;
  imageUrl?: string;
}

export interface AuthOrganization {
  id: string;
  slug?: string;
  role?: string;
  name?: string;
}

export interface AuthMembership {
  id: string;
  name: string;
  slug?: string;
  role?: string;
}

export interface AuthContextValue {
  /** True once the auth state has finished loading. */
  isLoaded: boolean;
  /** True if a user is currently signed in. */
  isSignedIn: boolean;
  /** The authenticated user, or null if signed out. */
  user: AuthUser | null;
  /** The user's currently active organisation, or null. */
  organization: AuthOrganization | null;
  /** All organisations the user is a member of. */
  organizations: AuthMembership[];
  /** True once the organisation memberships have finished loading. */
  organizationsLoaded: boolean;
  /** Switch the user's active organisation (provider-dependent). */
  selectOrganization: (organizationId: string) => Promise<void>;
  /** Fetch a fresh bearer token for backend requests. */
  getToken: () => Promise<string | null>;
  /** Trigger the provider's sign-in flow. */
  signIn: () => void;
  /** Sign the user out (revokes refresh token where supported). */
  signOut: () => Promise<void>;
}
