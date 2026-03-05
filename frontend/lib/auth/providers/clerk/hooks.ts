'use client';

/**
 * Clerk-specific hook wrappers that conform to provider-agnostic interfaces.
 */

import {
  useUser as useClerkUserHook,
  useOrganization as useClerkOrganizationHook,
} from '@clerk/nextjs';
import type { AuthUser, AuthOrganization } from '../../types';

/**
 * Provider-agnostic user hook backed by Clerk.
 */
export function useUser(): {
  user: AuthUser | null;
  isLoaded: boolean;
  isSignedIn: boolean;
} {
  const { user, isLoaded, isSignedIn } = useClerkUserHook();

  if (!user) {
    return { user: null, isLoaded, isSignedIn: isSignedIn ?? false };
  }

  return {
    user: {
      id: user.id,
      email: user.emailAddresses?.[0]?.emailAddress ?? null,
      fullName: user.fullName ?? null,
      firstName: user.firstName ?? null,
      lastName: user.lastName ?? null,
      imageUrl: user.imageUrl ?? null,
    },
    isLoaded,
    isSignedIn: isSignedIn ?? false,
  };
}

/**
 * Provider-agnostic organization hook backed by Clerk.
 */
export function useOrganization(): {
  organization: AuthOrganization | null;
  isLoaded: boolean;
} {
  const { organization, isLoaded } = useClerkOrganizationHook();

  if (!organization) {
    return { organization: null, isLoaded };
  }

  return {
    organization: {
      id: organization.id,
      name: organization.name,
      slug: organization.slug ?? undefined,
    },
    isLoaded,
  };
}
