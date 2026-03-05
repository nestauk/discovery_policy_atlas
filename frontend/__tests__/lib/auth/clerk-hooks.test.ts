import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const mockUseClerkUser = vi.fn();
const mockUseClerkOrganization = vi.fn();

vi.mock('@clerk/nextjs', () => ({
  useUser: () => mockUseClerkUser(),
  useOrganization: () => mockUseClerkOrganization(),
}));

beforeEach(() => {
  mockUseClerkUser.mockReset();
  mockUseClerkOrganization.mockReset();
  vi.resetModules();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useUser (Clerk)', () => {
  it('returns null user when not loaded', async () => {
    mockUseClerkUser.mockReturnValue({
      user: null,
      isLoaded: false,
      isSignedIn: false,
    });

    const { useUser } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useUser());

    expect(result.current.user).toBe(null);
    expect(result.current.isLoaded).toBe(false);
    expect(result.current.isSignedIn).toBe(false);
  });

  it('returns null user when signed out', async () => {
    mockUseClerkUser.mockReturnValue({
      user: null,
      isLoaded: true,
      isSignedIn: false,
    });

    const { useUser } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useUser());

    expect(result.current.user).toBe(null);
    expect(result.current.isLoaded).toBe(true);
    expect(result.current.isSignedIn).toBe(false);
  });

  it('maps Clerk user to AuthUser', async () => {
    mockUseClerkUser.mockReturnValue({
      user: {
        id: 'user_123',
        emailAddresses: [{ emailAddress: 'test@example.com' }],
        fullName: 'Test User',
        firstName: 'Test',
        lastName: 'User',
        imageUrl: 'https://example.com/avatar.png',
      },
      isLoaded: true,
      isSignedIn: true,
    });

    const { useUser } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useUser());

    expect(result.current.user).toEqual({
      id: 'user_123',
      email: 'test@example.com',
      fullName: 'Test User',
      firstName: 'Test',
      lastName: 'User',
      imageUrl: 'https://example.com/avatar.png',
    });
    expect(result.current.isLoaded).toBe(true);
    expect(result.current.isSignedIn).toBe(true);
  });

  it('handles missing email addresses', async () => {
    mockUseClerkUser.mockReturnValue({
      user: {
        id: 'user_456',
        emailAddresses: [],
        fullName: null,
        firstName: null,
        lastName: null,
        imageUrl: null,
      },
      isLoaded: true,
      isSignedIn: true,
    });

    const { useUser } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useUser());

    expect(result.current.user).toEqual({
      id: 'user_456',
      email: null,
      fullName: null,
      firstName: null,
      lastName: null,
      imageUrl: null,
    });
  });
});

describe('useOrganization (Clerk)', () => {
  it('returns null organization when not loaded', async () => {
    mockUseClerkOrganization.mockReturnValue({
      organization: null,
      isLoaded: false,
    });

    const { useOrganization } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useOrganization());

    expect(result.current.organization).toBe(null);
    expect(result.current.isLoaded).toBe(false);
  });

  it('returns null organization when no org selected', async () => {
    mockUseClerkOrganization.mockReturnValue({
      organization: null,
      isLoaded: true,
    });

    const { useOrganization } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useOrganization());

    expect(result.current.organization).toBe(null);
    expect(result.current.isLoaded).toBe(true);
  });

  it('maps Clerk organization to AuthOrganization', async () => {
    mockUseClerkOrganization.mockReturnValue({
      organization: {
        id: 'org_123',
        name: 'Test Org',
        slug: 'test-org',
      },
      isLoaded: true,
    });

    const { useOrganization } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useOrganization());

    expect(result.current.organization).toEqual({
      id: 'org_123',
      name: 'Test Org',
      slug: 'test-org',
    });
    expect(result.current.isLoaded).toBe(true);
  });

  it('maps missing slug to undefined', async () => {
    mockUseClerkOrganization.mockReturnValue({
      organization: {
        id: 'org_456',
        name: 'No Slug Org',
        slug: null,
      },
      isLoaded: true,
    });

    const { useOrganization } = await import('@/lib/auth/providers/clerk/hooks');
    const { result } = renderHook(() => useOrganization());

    expect(result.current.organization).toEqual({
      id: 'org_456',
      name: 'No Slug Org',
      slug: undefined,
    });
  });
});
