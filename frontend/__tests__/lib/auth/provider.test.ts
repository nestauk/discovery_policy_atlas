import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Store original env
const originalEnv = process.env;

// We need to test the provider module in isolation, so we reset modules between tests
beforeEach(() => {
  vi.resetModules();
  process.env = { ...originalEnv };
});

afterEach(() => {
  process.env = originalEnv;
});

describe('getAuthProviderName', () => {
  it('throws error when NEXT_PUBLIC_AUTH_PROVIDER is not set', async () => {
    delete process.env.NEXT_PUBLIC_AUTH_PROVIDER;
    
    const { getAuthProviderName } = await import('@/lib/auth/provider');
    
    expect(() => getAuthProviderName()).toThrow(
      'NEXT_PUBLIC_AUTH_PROVIDER environment variable is required'
    );
  });

  it('throws error when NEXT_PUBLIC_AUTH_PROVIDER has invalid value', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'invalid-provider';
    
    const { getAuthProviderName } = await import('@/lib/auth/provider');
    
    expect(() => getAuthProviderName()).toThrow(
      'Invalid NEXT_PUBLIC_AUTH_PROVIDER value: "invalid-provider"'
    );
  });

  it('returns "clerk" when NEXT_PUBLIC_AUTH_PROVIDER is "clerk"', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'clerk';
    
    const { getAuthProviderName } = await import('@/lib/auth/provider');
    
    expect(getAuthProviderName()).toBe('clerk');
  });

  it('returns "keycloak" when NEXT_PUBLIC_AUTH_PROVIDER is "keycloak"', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';
    
    const { getAuthProviderName } = await import('@/lib/auth/provider');
    
    expect(getAuthProviderName()).toBe('keycloak');
  });

  it('is case-insensitive (accepts "CLERK")', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'CLERK';
    
    const { getAuthProviderName } = await import('@/lib/auth/provider');
    
    expect(getAuthProviderName()).toBe('clerk');
  });

  it('caches the provider after first call', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'clerk';
    
    const { getAuthProviderName } = await import('@/lib/auth/provider');
    
    // First call
    expect(getAuthProviderName()).toBe('clerk');
    
    // Change env (should not affect due to caching)
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';
    
    // Should still return cached value
    expect(getAuthProviderName()).toBe('clerk');
  });
});

describe('isClerkProvider', () => {
  it('returns true when provider is clerk', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'clerk';
    
    const { isClerkProvider } = await import('@/lib/auth/provider');
    
    expect(isClerkProvider()).toBe(true);
  });

  it('returns false when provider is keycloak', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';
    
    const { isClerkProvider } = await import('@/lib/auth/provider');
    
    expect(isClerkProvider()).toBe(false);
  });
});

describe('isKeycloakProvider', () => {
  it('returns true when provider is keycloak', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';
    
    const { isKeycloakProvider } = await import('@/lib/auth/provider');
    
    expect(isKeycloakProvider()).toBe(true);
  });

  it('returns false when provider is clerk', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'clerk';
    
    const { isKeycloakProvider } = await import('@/lib/auth/provider');
    
    expect(isKeycloakProvider()).toBe(false);
  });
});

describe('validateKeycloakConfig', () => {
  it('throws when required Keycloak env vars are missing', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';
    delete process.env.NEXT_PUBLIC_KEYCLOAK_URL;
    delete process.env.NEXT_PUBLIC_KEYCLOAK_REALM;
    delete process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID;
    
    const { validateKeycloakConfig } = await import('@/lib/auth/provider');
    
    expect(() => validateKeycloakConfig()).toThrow(
      'Missing required Keycloak environment variables'
    );
  });

  it('does not throw when all Keycloak env vars are set', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';
    process.env.NEXT_PUBLIC_KEYCLOAK_URL = 'https://keycloak.example.com';
    process.env.NEXT_PUBLIC_KEYCLOAK_REALM = 'test-realm';
    process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID = 'test-client';
    
    const { validateKeycloakConfig } = await import('@/lib/auth/provider');
    
    expect(() => validateKeycloakConfig()).not.toThrow();
  });
});
