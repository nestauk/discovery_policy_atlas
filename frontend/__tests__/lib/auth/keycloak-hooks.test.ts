import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// Mock the Keycloak client
const mockKeycloak = {
  authenticated: false,
  token: null as string | null,
  tokenParsed: null as Record<string, unknown> | null,
  onAuthSuccess: undefined as (() => void) | undefined,
  onAuthLogout: undefined as (() => void) | undefined,
  onAuthRefreshSuccess: undefined as (() => void) | undefined,
  onAuthRefreshError: undefined as (() => void) | undefined,
};

vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
}));

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  // Reset mock state
  mockKeycloak.authenticated = false;
  mockKeycloak.token = null;
  mockKeycloak.tokenParsed = null;
  mockKeycloak.onAuthSuccess = undefined;
  mockKeycloak.onAuthLogout = undefined;
  mockKeycloak.onAuthRefreshSuccess = undefined;
  mockKeycloak.onAuthRefreshError = undefined;
  
  // Set env for keycloak
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_AUTH_PROVIDER: 'keycloak',
  };
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('useUser (Keycloak)', () => {
  it('returns not loaded initially when keycloak is not initialized', async () => {
    mockKeycloak.authenticated = undefined as unknown as boolean;
    
    const { useUser } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useUser());
    
    expect(result.current.isLoaded).toBe(false);
    expect(result.current.isSignedIn).toBe(false);
    expect(result.current.user).toBe(null);
  });

  it('returns loaded when keycloak authentication state is defined', async () => {
    mockKeycloak.authenticated = false;
    
    const { useUser } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useUser());
    
    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    expect(result.current.isSignedIn).toBe(false);
    expect(result.current.user).toBe(null);
  });

  it('returns user data when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      given_name: 'Test',
      family_name: 'User',
    };
    
    const { useUser } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useUser());
    
    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    
    expect(result.current.isSignedIn).toBe(true);
    expect(result.current.user).toEqual({
      id: 'user-123',
      email: 'test@example.com',
      fullName: 'Test User',
      firstName: 'Test',
      lastName: 'User',
      imageUrl: null,
    });
  });

  it('updates when onAuthSuccess is triggered', async () => {
    mockKeycloak.authenticated = false;
    
    const { useUser } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useUser());
    
    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    expect(result.current.isSignedIn).toBe(false);
    
    // Simulate auth success
    act(() => {
      mockKeycloak.authenticated = true;
      mockKeycloak.tokenParsed = {
        sub: 'user-456',
        email: 'new@example.com',
        name: 'New User',
      };
      mockKeycloak.onAuthSuccess?.();
    });
    
    await waitFor(() => {
      expect(result.current.isSignedIn).toBe(true);
    });
    expect(result.current.user?.id).toBe('user-456');
  });
});

describe('useOrganization (Keycloak)', () => {
  it('returns null organization when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { useOrganization } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useOrganization());
    
    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    
    expect(result.current.organization).toBe(null);
  });

  it('extracts organization from azp claim', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      azp: 'my-organization',
    };
    
    const { useOrganization } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useOrganization());
    
    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    
    expect(result.current.organization).toEqual({
      id: 'my-organization',
      name: 'my-organization',
      slug: 'my-organization',
    });
  });

  it('extracts organization from groups claim when azp is absent', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      groups: ['group-alpha', 'group-beta'],
    };
    
    const { useOrganization } = await import('@/lib/auth/providers/keycloak/hooks');
    const { result } = renderHook(() => useOrganization());
    
    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    
    expect(result.current.organization).toEqual({
      id: 'group-alpha',
      name: 'group-alpha',
      slug: undefined,
    });
  });
});
