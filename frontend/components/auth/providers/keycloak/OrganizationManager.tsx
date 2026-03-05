'use client';

/**
 * Keycloak organization manager - Keycloak doesn't have built-in
 * organization management like Clerk, so this provides a stub/no-op
 * implementation that can display groups/roles from the token.
 */

import { ReactNode } from 'react';
import { useOrganization } from '@/lib/auth/providers/keycloak/hooks';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface OrganizationManagerProps {
  /** Children to render inside the manager */
  children?: ReactNode;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Organization list - shows groups from Keycloak token.
 * 
 * Note: Keycloak organizational structure is different from Clerk.
 * This shows the groups/roles assigned to the user in Keycloak.
 */
export function OrganizationList({ className }: { className?: string }) {
  const { organization, isLoaded } = useOrganization();

  if (!isLoaded) {
    return (
      <div className={className}>
        <div className="h-8 bg-gray-200 rounded animate-pulse" />
      </div>
    );
  }

  if (!organization) {
    return (
      <Card className={className}>
        <CardContent className="py-4 text-center">
          <p className="text-sm text-gray-500">No organization assigned.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{organization.name}</CardTitle>
        {organization.slug && (
          <CardDescription>Group ID: {organization.slug}</CardDescription>
        )}
      </CardHeader>
    </Card>
  );
}

/**
 * Organization switcher - stub implementation.
 * 
 * Keycloak doesn't support organization switching like Clerk.
 * Users would need to re-authenticate with different group memberships.
 */
export function OrganizationSwitcher({ 
  appearance 
}: { 
  appearance?: { elements?: Record<string, string> };
}) {
  const { organization, isLoaded } = useOrganization();

  if (!isLoaded) {
    return <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />;
  }

  if (!organization) {
    return null;
  }

  // Display current organization, no switching available
  return (
    <div className={`px-3 py-1.5 text-sm bg-gray-100 rounded-md ${appearance?.elements?.rootBox || ''}`}>
      <span className="text-gray-700">{organization.name}</span>
    </div>
  );
}

/**
 * Organization profile - displays organization details.
 */
export function OrganizationProfile({ 
  appearance 
}: { 
  appearance?: { elements?: Record<string, string> };
}) {
  const { organization, isLoaded } = useOrganization();

  if (!isLoaded) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="h-20 bg-gray-200 rounded animate-pulse" />
        </CardContent>
      </Card>
    );
  }

  if (!organization) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-gray-500">No organization profile available.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={appearance?.elements?.card}>
      <CardHeader>
        <CardTitle>Organization</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-4">
          <div>
            <dt className="text-sm font-medium text-gray-500">Name</dt>
            <dd className="mt-1 text-sm text-gray-900">{organization.name}</dd>
          </div>
          {organization.slug && (
            <div>
              <dt className="text-sm font-medium text-gray-500">Group ID</dt>
              <dd className="mt-1 text-sm text-gray-900">{organization.slug}</dd>
            </div>
          )}
        </dl>
      </CardContent>
    </Card>
  );
}

/**
 * Create organization button - not supported in Keycloak.
 */
export function CreateOrganization({ 
  children: _children 
}: { 
  children?: ReactNode;
}) {
  // Keycloak doesn't support client-side organization creation
  // Return null or show a message
  return null;
}

/**
 * Organization manager wrapper component.
 */
export function OrganizationManager({ 
  children, 
  className 
}: OrganizationManagerProps) {
  return (
    <div className={className}>
      <OrganizationList className="mb-4" />
      {children}
    </div>
  );
}
