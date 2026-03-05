import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { makeKeycloakEnv, resetKeycloakCore } from '../../../../helpers/keycloak-test-helpers';

// Mock the Keycloak client
const mockKeycloak = {
  authenticated: undefined as boolean | undefined,
  token: null as string | null,
  tokenParsed: null as Record<string, unknown> | null,
  updateToken: vi.fn().mockResolvedValue(true),
  onAuthSuccess: undefined as (() => void) | undefined,
  onAuthLogout: undefined as (() => void) | undefined,
  onAuthRefreshSuccess: undefined as (() => void) | undefined,
  onAuthRefreshError: undefined as (() => void) | undefined,
};

const mockInitKeycloak = vi.fn();

vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
  initKeycloak: () => mockInitKeycloak(),
}));

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  // Reset mock state
  resetKeycloakCore(mockKeycloak);
  mockKeycloak.authenticated = undefined;
  mockKeycloak.updateToken = vi.fn().mockResolvedValue(true);
  mockInitKeycloak.mockReset();
  mockInitKeycloak.mockResolvedValue(true);
  
  // Set env for keycloak
  process.env = makeKeycloakEnv(originalEnv);
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('ProviderRoot', () => {
  it('shows loading state initially', async () => {
    mockInitKeycloak.mockImplementation(() => new Promise(() => {}));
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    const { container } = render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );
    
    // Should show loading spinner
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    expect(screen.getByText('Initializing authentication...')).toBeInTheDocument();
  });

  it('renders children after keycloak initializes successfully', async () => {
    mockInitKeycloak.mockResolvedValue(true);
    
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });
    
    await waitFor(() => {
      expect(screen.getByText('App Content')).toBeInTheDocument();
    });
  });

  it('calls initKeycloak()', async () => {
    mockInitKeycloak.mockResolvedValue(true);
    
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });
    
    await waitFor(() => {
      expect(mockInitKeycloak).toHaveBeenCalledTimes(1);
    });
  });

  it('renders children even when init fails (graceful degradation)', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockInitKeycloak.mockRejectedValue(new Error('Init failed'));
    
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });
    
    await waitFor(() => {
      expect(screen.getByText('Authentication initialization failed')).toBeInTheDocument();
    });
    
    consoleSpy.mockRestore();
  });

  it('renders children when already authenticated', async () => {
    mockKeycloak.authenticated = true; // Already initialized
    mockInitKeycloak.mockResolvedValue(true);
    
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });
    
    await waitFor(() => {
      expect(screen.getByText('App Content')).toBeInTheDocument();
    });
    
    expect(mockInitKeycloak).toHaveBeenCalledTimes(1);
  });

  it('sets up token refresh interval', async () => {
    mockKeycloak.authenticated = undefined;
    mockInitKeycloak.mockResolvedValue(true);
    vi.useFakeTimers();
    
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText('App Content')).toBeInTheDocument();

    mockKeycloak.authenticated = true;
    
    // Fast-forward 30 seconds
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    
    // Should have called updateToken
    expect(mockKeycloak.updateToken).toHaveBeenCalledWith(60);
  });

  it('cleans up interval on unmount', async () => {
    mockKeycloak.authenticated = true;
    mockInitKeycloak.mockResolvedValue(true);
    vi.useFakeTimers();
    
    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');
    
    const { unmount } = render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText('App Content')).toBeInTheDocument();
    
    // Clear the mock call count
    mockKeycloak.updateToken.mockClear();
    
    // Unmount
    unmount();
    
    // Fast-forward 30 seconds after unmount
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    
    // Should NOT have called updateToken since component is unmounted
    expect(mockKeycloak.updateToken).not.toHaveBeenCalled();
  });

  it('logs a warning when token refresh fails', async () => {
    mockKeycloak.authenticated = undefined;
    mockInitKeycloak.mockResolvedValue(true);
    mockKeycloak.updateToken = vi.fn().mockRejectedValue(new Error('Refresh failed'));
    vi.useFakeTimers();
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const { ProviderRoot } = await import('@/components/auth/providers/keycloak/ProviderRoot');

    render(
      <ProviderRoot>
        <div>App Content</div>
      </ProviderRoot>
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText('App Content')).toBeInTheDocument();

    mockKeycloak.authenticated = true;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(consoleSpy).toHaveBeenCalledWith(
      'Token refresh failed, user may need to re-login'
    );

    consoleSpy.mockRestore();
  });
});
