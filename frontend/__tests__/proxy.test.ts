import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const nextResponseNext = vi.fn(() => ({ ok: true }));

vi.mock('next/server', () => ({
  NextResponse: {
    next: nextResponseNext,
  },
}));

const clerkHandler = vi.fn(() => ({ handled: true }));
const clerkMiddleware = vi.fn(() => clerkHandler);

vi.mock('@clerk/nextjs/server', () => ({
  clerkMiddleware,
}));

const originalEnv = process.env;

describe('middleware', () => {
  beforeEach(() => {
    vi.resetModules();
    nextResponseNext.mockClear();
    clerkMiddleware.mockClear();
    clerkHandler.mockClear();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.clearAllMocks();
  });

  it('passes through when provider is keycloak', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';

    const middleware = (await import('@/proxy')).default;

    const response = middleware({} as never, {} as never);

    expect(nextResponseNext).toHaveBeenCalled();
    expect(response).toEqual({ ok: true });
    expect(clerkMiddleware).not.toHaveBeenCalled();
  });

  it('delegates to clerk middleware when provider is clerk', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'clerk';

    const middleware = (await import('@/proxy')).default;

    const response = middleware({} as never, {} as never);

    expect(clerkMiddleware).toHaveBeenCalled();
    expect(clerkHandler).toHaveBeenCalled();
    expect(response).toEqual({ handled: true });
    expect(nextResponseNext).not.toHaveBeenCalled();
  });

  it('exports matcher configuration', async () => {
    process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'keycloak';

    const { config } = await import('@/proxy');

    expect(config.matcher).toEqual(
      expect.arrayContaining([
        '/(api|trpc)(.*)',
      ])
    );
  });
});
