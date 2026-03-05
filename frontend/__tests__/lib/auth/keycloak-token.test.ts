import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

// Mock the Keycloak client
const mockKeycloak = {
  authenticated: false,
  token: 'mock-token-123',
  updateToken: vi.fn().mockResolvedValue(true),
};

vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
}));

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  // Reset mock state
  mockKeycloak.authenticated = false;
  mockKeycloak.token = 'mock-token-123';
  mockKeycloak.updateToken = vi.fn().mockResolvedValue(true);
  
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_AUTH_PROVIDER: 'keycloak',
  };
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('useAuthToken (Keycloak)', () => {
  it('returns null token when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { useAuthToken } = await import('@/lib/auth/providers/keycloak');
    const { result } = renderHook(() => useAuthToken());
    
    const token = await result.current.getToken();
    expect(token).toBe(null);
  });

  it('returns token when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.token = 'valid-access-token';
    
    const { useAuthToken } = await import('@/lib/auth/providers/keycloak');
    const { result } = renderHook(() => useAuthToken());
    
    const token = await result.current.getToken();
    expect(token).toBe('valid-access-token');
  });

  it('refreshes token before returning', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.token = 'refreshed-token';
    
    const { useAuthToken } = await import('@/lib/auth/providers/keycloak');
    const { result } = renderHook(() => useAuthToken());
    
    await result.current.getToken();
    expect(mockKeycloak.updateToken).toHaveBeenCalledWith(30);
  });

  it('returns null when token refresh fails', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.token = 'valid-token';
    mockKeycloak.updateToken = vi.fn().mockRejectedValue(new Error('Refresh failed'));
    
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    
    const { useAuthToken } = await import('@/lib/auth/providers/keycloak');
    const { result } = renderHook(() => useAuthToken());
    
    const token = await result.current.getToken();
    expect(token).toBe(null);
    
    consoleSpy.mockRestore();
  });
});

describe('getTokenExternal (Keycloak)', () => {
  it('returns null when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { getTokenExternal } = await import('@/lib/auth/providers/keycloak');
    const token = await getTokenExternal();
    
    expect(token).toBe(null);
  });

  it('returns token when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.token = 'external-access-token';
    
    const { getTokenExternal } = await import('@/lib/auth/providers/keycloak');
    const token = await getTokenExternal();
    
    expect(token).toBe('external-access-token');
  });

  it('refreshes token before returning', async () => {
    mockKeycloak.authenticated = true;
    
    const { getTokenExternal } = await import('@/lib/auth/providers/keycloak');
    await getTokenExternal();
    
    expect(mockKeycloak.updateToken).toHaveBeenCalledWith(30);
  });

  it('returns null when token refresh fails', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.updateToken = vi.fn().mockRejectedValue(new Error('Refresh failed'));
    
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    
    const { getTokenExternal } = await import('@/lib/auth/providers/keycloak');
    const token = await getTokenExternal();
    
    expect(token).toBe(null);
    expect(consoleSpy).toHaveBeenCalledWith(
      'Failed to refresh Keycloak token (external):',
      expect.any(Error)
    );
    
    consoleSpy.mockRestore();
  });
});
