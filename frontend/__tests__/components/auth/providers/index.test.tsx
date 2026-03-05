import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const originalEnv = process.env;

describe('provider-aware auth UI exports', () => {
  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv, NEXT_PUBLIC_AUTH_PROVIDER: 'clerk' };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.clearAllMocks();
  });

  it('exports Clerk components when provider is clerk', async () => {
    const clerkExports = {
      AuthButtons: vi.fn(),
      LoginForm: vi.fn(),
      OrganizationManager: vi.fn(),
      ProviderRoot: vi.fn(),
      SignInButton: vi.fn(),
      SignUpButton: vi.fn(),
      SignedIn: vi.fn(),
      SignedOut: vi.fn(),
      UserButton: vi.fn(),
      SignIn: vi.fn(),
    };

    const keycloakExports = {
      AuthButtons: vi.fn(),
      LoginForm: vi.fn(),
      OrganizationManager: vi.fn(),
      ProviderRoot: vi.fn(),
      SignInButton: vi.fn(),
      SignUpButton: vi.fn(),
      SignedIn: vi.fn(),
      SignedOut: vi.fn(),
      UserButton: vi.fn(),
      SignInPage: vi.fn(),
    };

    vi.doMock('@/lib/auth/provider', () => ({
      isClerkProvider: () => true,
      getAuthProviderName: () => 'clerk',
    }));

    vi.doMock('@/components/auth/providers/clerk', () => clerkExports);
    vi.doMock('@/components/auth/providers/keycloak', () => keycloakExports);

    const exported = await import('@/components/auth/providers');

    expect(exported.ProviderRoot).toBe(clerkExports.ProviderRoot);
    expect(exported.AuthButtons).toBe(clerkExports.AuthButtons);
    expect(exported.LoginForm).toBe(clerkExports.LoginForm);
    expect(exported.OrganizationManager).toBe(clerkExports.OrganizationManager);
    expect(exported.SignInButton).toBe(clerkExports.SignInButton);
    expect(exported.SignUpButton).toBe(clerkExports.SignUpButton);
    expect(exported.UserButton).toBe(clerkExports.UserButton);
    expect(exported.SignedIn).toBe(clerkExports.SignedIn);
    expect(exported.SignedOut).toBe(clerkExports.SignedOut);
    expect(exported.SignIn).toBe(clerkExports.SignIn);
  });

  it('exports Keycloak components when provider is keycloak', async () => {
    const clerkExports = {
      AuthButtons: vi.fn(),
      LoginForm: vi.fn(),
      OrganizationManager: vi.fn(),
      ProviderRoot: vi.fn(),
      SignInButton: vi.fn(),
      SignUpButton: vi.fn(),
      SignedIn: vi.fn(),
      SignedOut: vi.fn(),
      UserButton: vi.fn(),
      SignIn: vi.fn(),
    };

    const keycloakExports = {
      AuthButtons: vi.fn(),
      LoginForm: vi.fn(),
      OrganizationManager: vi.fn(),
      ProviderRoot: vi.fn(),
      SignInButton: vi.fn(),
      SignUpButton: vi.fn(),
      SignedIn: vi.fn(),
      SignedOut: vi.fn(),
      UserButton: vi.fn(),
      SignInPage: vi.fn(),
    };

    vi.doMock('@/lib/auth/provider', () => ({
      isClerkProvider: () => false,
      getAuthProviderName: () => 'keycloak',
    }));

    vi.doMock('@/components/auth/providers/clerk', () => clerkExports);
    vi.doMock('@/components/auth/providers/keycloak', () => keycloakExports);

    const exported = await import('@/components/auth/providers');

    expect(exported.ProviderRoot).toBe(keycloakExports.ProviderRoot);
    expect(exported.AuthButtons).toBe(keycloakExports.AuthButtons);
    expect(exported.LoginForm).toBe(keycloakExports.LoginForm);
    expect(exported.OrganizationManager).toBe(keycloakExports.OrganizationManager);
    expect(exported.SignInButton).toBe(keycloakExports.SignInButton);
    expect(exported.SignUpButton).toBe(keycloakExports.SignUpButton);
    expect(exported.UserButton).toBe(keycloakExports.UserButton);
    expect(exported.SignedIn).toBe(keycloakExports.SignedIn);
    expect(exported.SignedOut).toBe(keycloakExports.SignedOut);
    expect(exported.SignIn).toBe(keycloakExports.SignInPage);
  });
});
