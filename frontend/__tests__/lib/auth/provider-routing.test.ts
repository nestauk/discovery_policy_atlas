import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('provider-aware exports', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv, NEXT_PUBLIC_AUTH_PROVIDER: 'clerk' };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.clearAllMocks();
  });

  it('routes token exports to Clerk when isClerkProvider is true', async () => {
    const clerkUseAuthToken = vi.fn();
    const clerkGetTokenExternal = vi.fn();
    const keycloakUseAuthToken = vi.fn();
    const keycloakGetTokenExternal = vi.fn();

    vi.doMock('@/lib/auth/provider', () => ({
      isClerkProvider: () => true,
    }));
    vi.doMock('@/lib/auth/providers/clerk', () => ({
      useAuthToken: clerkUseAuthToken,
      getTokenExternal: clerkGetTokenExternal,
    }));
    vi.doMock('@/lib/auth/providers/keycloak', () => ({
      useAuthToken: keycloakUseAuthToken,
      getTokenExternal: keycloakGetTokenExternal,
    }));

    const { useAuthToken, getTokenExternal } = await import('@/lib/auth/token');

    expect(useAuthToken).toBe(clerkUseAuthToken);
    expect(getTokenExternal).toBe(clerkGetTokenExternal);
  });

  it('routes token exports to Keycloak when isClerkProvider is false', async () => {
    const clerkUseAuthToken = vi.fn();
    const clerkGetTokenExternal = vi.fn();
    const keycloakUseAuthToken = vi.fn();
    const keycloakGetTokenExternal = vi.fn();

    vi.doMock('@/lib/auth/provider', () => ({
      isClerkProvider: () => false,
    }));
    vi.doMock('@/lib/auth/providers/clerk', () => ({
      useAuthToken: clerkUseAuthToken,
      getTokenExternal: clerkGetTokenExternal,
    }));
    vi.doMock('@/lib/auth/providers/keycloak', () => ({
      useAuthToken: keycloakUseAuthToken,
      getTokenExternal: keycloakGetTokenExternal,
    }));

    const { useAuthToken, getTokenExternal } = await import('@/lib/auth/token');

    expect(useAuthToken).toBe(keycloakUseAuthToken);
    expect(getTokenExternal).toBe(keycloakGetTokenExternal);
  });

  it('routes user hooks to Clerk when isClerkProvider is true', async () => {
    const clerkUseUser = vi.fn();
    const clerkUseOrganization = vi.fn();
    const keycloakUseUser = vi.fn();
    const keycloakUseOrganization = vi.fn();

    vi.doMock('@/lib/auth/provider', () => ({
      isClerkProvider: () => true,
    }));
    vi.doMock('@/lib/auth/providers/clerk/hooks', () => ({
      useUser: clerkUseUser,
      useOrganization: clerkUseOrganization,
    }));
    vi.doMock('@/lib/auth/providers/keycloak/hooks', () => ({
      useUser: keycloakUseUser,
      useOrganization: keycloakUseOrganization,
    }));

    const { useAuthUser, useAuthOrganization } = await import('@/lib/auth/hooks');

    expect(useAuthUser).toBe(clerkUseUser);
    expect(useAuthOrganization).toBe(clerkUseOrganization);
  });

  it('routes user hooks to Keycloak when isClerkProvider is false', async () => {
    const clerkUseUser = vi.fn();
    const clerkUseOrganization = vi.fn();
    const keycloakUseUser = vi.fn();
    const keycloakUseOrganization = vi.fn();

    vi.doMock('@/lib/auth/provider', () => ({
      isClerkProvider: () => false,
    }));
    vi.doMock('@/lib/auth/providers/clerk/hooks', () => ({
      useUser: clerkUseUser,
      useOrganization: clerkUseOrganization,
    }));
    vi.doMock('@/lib/auth/providers/keycloak/hooks', () => ({
      useUser: keycloakUseUser,
      useOrganization: keycloakUseOrganization,
    }));

    const { useAuthUser, useAuthOrganization } = await import('@/lib/auth/hooks');

    expect(useAuthUser).toBe(keycloakUseUser);
    expect(useAuthOrganization).toBe(keycloakUseOrganization);
  });
});
