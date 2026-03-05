import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockGetToken = vi.fn();

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    getToken: mockGetToken,
  }),
}));

const originalWindow = globalThis.window;

beforeEach(() => {
  mockGetToken.mockReset();
  vi.resetModules();
  Object.defineProperty(globalThis, 'window', {
    value: originalWindow,
    configurable: true,
    writable: true,
  });
});

afterEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(globalThis, 'window', {
    value: originalWindow,
    configurable: true,
    writable: true,
  });
});

describe('useAuthToken (Clerk)', () => {
  it('returns getToken from useAuth hook', async () => {
    mockGetToken.mockResolvedValue('token-123');

    const { useAuthToken } = await import('@/lib/auth/providers/clerk');
    const { getToken } = useAuthToken();

    await expect(getToken()).resolves.toBe('token-123');
  });
});

describe('getTokenExternal (Clerk)', () => {
  it('returns null when window is undefined', async () => {
    Object.defineProperty(globalThis, 'window', {
      value: undefined,
      configurable: true,
      writable: true,
    });

    const { getTokenExternal } = await import('@/lib/auth/providers/clerk');
    await expect(getTokenExternal()).resolves.toBe(null);
  });

  it('returns null when window.Clerk is missing', async () => {
    Object.defineProperty(globalThis, 'window', {
      value: {},
      configurable: true,
      writable: true,
    });

    const { getTokenExternal } = await import('@/lib/auth/providers/clerk');
    await expect(getTokenExternal()).resolves.toBe(null);
  });

  it('returns null when window.Clerk.session is missing', async () => {
    Object.defineProperty(globalThis, 'window', {
      value: { Clerk: {} },
      configurable: true,
      writable: true,
    });

    const { getTokenExternal } = await import('@/lib/auth/providers/clerk');
    await expect(getTokenExternal()).resolves.toBe(null);
  });

  it('returns token from window.Clerk.session.getToken()', async () => {
    const getToken = vi.fn().mockResolvedValue('external-token');

    Object.defineProperty(globalThis, 'window', {
      value: {
        Clerk: {
          session: { getToken },
        },
      },
      configurable: true,
      writable: true,
    });

    const { getTokenExternal } = await import('@/lib/auth/providers/clerk');
    await expect(getTokenExternal()).resolves.toBe('external-token');
    expect(getToken).toHaveBeenCalled();
  });

  it('returns null and logs error when getToken throws', async () => {
    const getToken = vi.fn().mockRejectedValue(new Error('Token error'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    Object.defineProperty(globalThis, 'window', {
      value: {
        Clerk: {
          session: { getToken },
        },
      },
      configurable: true,
      writable: true,
    });

    const { getTokenExternal } = await import('@/lib/auth/providers/clerk');
    await expect(getTokenExternal()).resolves.toBe(null);
    expect(consoleSpy).toHaveBeenCalledWith(
      'Failed to get Clerk token from window:',
      expect.any(Error)
    );

    consoleSpy.mockRestore();
  });
});
