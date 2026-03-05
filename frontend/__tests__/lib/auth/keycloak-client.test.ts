import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock keycloak-js module
const mockKeycloakInstance = {
  authenticated: undefined as boolean | undefined,
  init: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  updateToken: vi.fn(),
};

vi.mock('keycloak-js', () => ({
  default: vi.fn(() => mockKeycloakInstance),
}));

// Mock provider validation
vi.mock('@/lib/auth/provider', () => ({
  isKeycloakProvider: () => true,
  validateKeycloakConfig: vi.fn(),
}));

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  // Reset mock state
  mockKeycloakInstance.authenticated = undefined;
  mockKeycloakInstance.init = vi.fn().mockResolvedValue(false);
  mockKeycloakInstance.login = vi.fn().mockResolvedValue(undefined);
  mockKeycloakInstance.register = vi.fn().mockResolvedValue(undefined);
  mockKeycloakInstance.logout = vi.fn().mockResolvedValue(undefined);
  mockKeycloakInstance.updateToken = vi.fn().mockResolvedValue(true);

  // Set required env vars
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_AUTH_PROVIDER: 'keycloak',
    NEXT_PUBLIC_KEYCLOAK_URL: 'https://keycloak.example.com',
    NEXT_PUBLIC_KEYCLOAK_REALM: 'test-realm',
    NEXT_PUBLIC_KEYCLOAK_CLIENT_ID: 'test-client',
  };

  // Clear module cache to get fresh imports
  vi.resetModules();
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('initKeycloak', () => {
  it('initializes keycloak with correct options', async () => {
    const { initKeycloak } = await import('@/lib/auth/providers/keycloak/client');

    await initKeycloak();

    expect(mockKeycloakInstance.init).toHaveBeenCalledWith({
      onLoad: 'check-sso',
      pkceMethod: 'S256',
      silentCheckSsoRedirectUri: expect.any(String),
      checkLoginIframe: false,
    });
  });

  it('returns authentication status from init', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);

    const { initKeycloak } = await import('@/lib/auth/providers/keycloak/client');
    const result = await initKeycloak();

    expect(result).toBe(true);
  });

  it('only initializes once when called multiple times', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(false);

    const { initKeycloak } = await import('@/lib/auth/providers/keycloak/client');

    await initKeycloak();
    await initKeycloak();
    await initKeycloak();

    expect(mockKeycloakInstance.init).toHaveBeenCalledTimes(1);
  });

  it('skips init if already authenticated', async () => {
    mockKeycloakInstance.authenticated = true;

    const { initKeycloak } = await import('@/lib/auth/providers/keycloak/client');
    const result = await initKeycloak();

    expect(mockKeycloakInstance.init).not.toHaveBeenCalled();
    expect(result).toBe(true);
  });

  it('returns false on init failure', async () => {
    mockKeycloakInstance.init = vi.fn().mockRejectedValue(new Error('Init failed'));

    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { initKeycloak } = await import('@/lib/auth/providers/keycloak/client');
    const result = await initKeycloak();

    expect(result).toBe(false);
    expect(consoleSpy).toHaveBeenCalledWith(
      'Keycloak init failed:',
      expect.objectContaining({
        error: expect.objectContaining({ message: 'Init failed' }),
      })
    );

    consoleSpy.mockRestore();
  });
});

describe('login', () => {
  it('waits for init before calling login', async () => {
    const initOrder: string[] = [];
    mockKeycloakInstance.init = vi.fn().mockImplementation(async () => {
      initOrder.push('init');
      return true;
    });
    mockKeycloakInstance.login = vi.fn().mockImplementation(async () => {
      initOrder.push('login');
    });

    const { login } = await import('@/lib/auth/providers/keycloak/client');
    await login();

    expect(initOrder).toEqual(['init', 'login']);
  });

  it('calls keycloak.login() after init', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);

    const { login } = await import('@/lib/auth/providers/keycloak/client');
    await login();

    expect(mockKeycloakInstance.login).toHaveBeenCalled();
  });

  it('propagates login errors', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);
    mockKeycloakInstance.login = vi.fn().mockRejectedValue(new Error('Login failed'));

    const { login } = await import('@/lib/auth/providers/keycloak/client');

    await expect(login()).rejects.toThrow('Login failed');
  });

  it('throws when init fails', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(false);

    const { login } = await import('@/lib/auth/providers/keycloak/client');

    await expect(login()).rejects.toThrow('Keycloak init failed. Cannot perform login.');
  });
});

describe('register', () => {
  it('waits for init before calling register', async () => {
    const initOrder: string[] = [];
    mockKeycloakInstance.init = vi.fn().mockImplementation(async () => {
      initOrder.push('init');
      return true;
    });
    mockKeycloakInstance.register = vi.fn().mockImplementation(async () => {
      initOrder.push('register');
    });

    const { register } = await import('@/lib/auth/providers/keycloak/client');
    await register();

    expect(initOrder).toEqual(['init', 'register']);
  });

  it('calls keycloak.register() after init', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);

    const { register } = await import('@/lib/auth/providers/keycloak/client');
    await register();

    expect(mockKeycloakInstance.register).toHaveBeenCalled();
  });

  it('propagates register errors', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);
    mockKeycloakInstance.register = vi.fn().mockRejectedValue(new Error('Register failed'));

    const { register } = await import('@/lib/auth/providers/keycloak/client');

    await expect(register()).rejects.toThrow('Register failed');
  });

  it('throws when init fails', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(false);

    const { register } = await import('@/lib/auth/providers/keycloak/client');

    await expect(register()).rejects.toThrow('Keycloak init failed. Cannot perform registration.');
  });
});

describe('logout', () => {
  it('waits for init before calling logout', async () => {
    const initOrder: string[] = [];
    mockKeycloakInstance.init = vi.fn().mockImplementation(async () => {
      initOrder.push('init');
      return true;
    });
    mockKeycloakInstance.logout = vi.fn().mockImplementation(async () => {
      initOrder.push('logout');
    });

    const { logout } = await import('@/lib/auth/providers/keycloak/client');
    await logout();

    expect(initOrder).toEqual(['init', 'logout']);
  });

  it('calls keycloak.logout() with default redirectUri', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);

    const { logout } = await import('@/lib/auth/providers/keycloak/client');
    await logout();

    expect(mockKeycloakInstance.logout).toHaveBeenCalledWith({
      redirectUri: expect.any(String),
    });
  });

  it('uses custom redirectUri when provided', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);

    const { logout } = await import('@/lib/auth/providers/keycloak/client');
    await logout({ redirectUri: 'https://custom.redirect.com' });

    expect(mockKeycloakInstance.logout).toHaveBeenCalledWith({
      redirectUri: 'https://custom.redirect.com',
    });
  });

  it('propagates logout errors', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);
    mockKeycloakInstance.logout = vi.fn().mockRejectedValue(new Error('Logout failed'));

    const { logout } = await import('@/lib/auth/providers/keycloak/client');

    await expect(logout()).rejects.toThrow('Logout failed');
  });

  it('throws when init fails', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(false);

    const { logout } = await import('@/lib/auth/providers/keycloak/client');

    await expect(logout()).rejects.toThrow('Keycloak init failed. Cannot perform logout.');
  });
});

describe('getKeycloakInstance', () => {
  it('returns the same instance on multiple calls', async () => {
    const { getKeycloakInstance } = await import('@/lib/auth/providers/keycloak/client');

    const instance1 = getKeycloakInstance();
    const instance2 = getKeycloakInstance();

    expect(instance1).toBe(instance2);
  });
});

describe('isKeycloakInitialized', () => {
  it('returns false before init', async () => {
    const { isKeycloakInitialized } = await import('@/lib/auth/providers/keycloak/client');

    expect(isKeycloakInitialized()).toBe(false);
  });

  it('returns true after successful init', async () => {
    mockKeycloakInstance.init = vi.fn().mockResolvedValue(true);

    const { initKeycloak, isKeycloakInitialized } = await import(
      '@/lib/auth/providers/keycloak/client'
    );

    await initKeycloak();

    expect(isKeycloakInitialized()).toBe(true);
  });

  it('returns true after failed init (to prevent retries)', async () => {
    mockKeycloakInstance.init = vi.fn().mockRejectedValue(new Error('Init failed'));

    // Suppress console.error
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { initKeycloak, isKeycloakInitialized } = await import(
      '@/lib/auth/providers/keycloak/client'
    );

    await initKeycloak();

    expect(isKeycloakInitialized()).toBe(true);

    consoleSpy.mockRestore();
  });
});
