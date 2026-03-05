import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { makeKeycloakEnv, resetKeycloakCore } from '../../../../helpers/keycloak-test-helpers';

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

const mockLogin = vi.fn();
const mockRegister = vi.fn();
const mockLogout = vi.fn();

vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
  login: () => mockLogin(),
  register: () => mockRegister(),
  logout: (...args: [string?]) => mockLogout(...args),
}));

// Mock Lucide icons
vi.mock('lucide-react', () => ({
  LogIn: () => <span data-testid="login-icon">LogIn</span>,
  LogOut: () => <span data-testid="logout-icon">LogOut</span>,
}));

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  // Reset mock state
  resetKeycloakCore(mockKeycloak);
  mockLogin.mockReset();
  mockRegister.mockReset();
  mockLogout.mockReset();
  mockLogin.mockResolvedValue(undefined);
  mockRegister.mockResolvedValue(undefined);
  mockLogout.mockResolvedValue(undefined);
  
  // Set env for keycloak
  process.env = makeKeycloakEnv(originalEnv);
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('SignInButton', () => {
  it('renders default button when no children provided', async () => {
    const { SignInButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<SignInButton />);
    
    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(screen.getByTestId('login-icon')).toBeInTheDocument();
  });

  it('renders custom children when provided', async () => {
    const { SignInButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<SignInButton><button>Custom Login</button></SignInButton>);
    
    expect(screen.getByText('Custom Login')).toBeInTheDocument();
    expect(screen.queryByText('Sign in')).not.toBeInTheDocument();
  });

  it('calls keycloak.login() when clicked', async () => {
    const { SignInButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<SignInButton />);
    
    fireEvent.click(screen.getByText('Sign in'));
    expect(mockLogin).toHaveBeenCalled();
  });

  it('logs an error if login fails', async () => {
    mockLogin.mockRejectedValue(new Error('Login failed'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { SignInButton } = await import('@/components/auth/providers/keycloak/AuthButtons');

    render(<SignInButton />);

    fireEvent.click(screen.getByText('Sign in'));

    await Promise.resolve();
    expect(consoleSpy).toHaveBeenCalledWith('Keycloak login failed:', expect.any(Error));

    consoleSpy.mockRestore();
  });
});

describe('SignUpButton', () => {
  it('renders default button when no children provided', async () => {
    const { SignUpButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<SignUpButton />);
    
    expect(screen.getByText('Sign up')).toBeInTheDocument();
  });

  it('calls keycloak.register() when clicked', async () => {
    const { SignUpButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<SignUpButton />);
    
    fireEvent.click(screen.getByText('Sign up'));
    expect(mockRegister).toHaveBeenCalled();
  });

  it('logs an error if registration fails', async () => {
    mockRegister.mockRejectedValue(new Error('Register failed'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { SignUpButton } = await import('@/components/auth/providers/keycloak/AuthButtons');

    render(<SignUpButton />);

    fireEvent.click(screen.getByText('Sign up'));

    await Promise.resolve();
    expect(consoleSpy).toHaveBeenCalledWith('Keycloak registration failed:', expect.any(Error));

    consoleSpy.mockRestore();
  });
});

describe('UserButton', () => {
  it('returns null when not signed in', async () => {
    mockKeycloak.authenticated = false;
    
    const { UserButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    const { container } = render(<UserButton />);
    expect(container.firstChild).toBe(null);
  });

  it('displays user initials from firstName', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      email: 'test@example.com',
      given_name: 'Test',
      family_name: 'User',
      name: 'Test User',
    };
    
    const { UserButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<UserButton />);
    
    // Should show initial 'T' from 'Test'
    expect(screen.getByText('T')).toBeInTheDocument();
  });

  it('displays user initials from email when no name', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      email: 'john@example.com',
    };
    
    const { UserButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<UserButton />);
    
    // Should show initial 'J' from 'john@example.com'
    expect(screen.getByText('J')).toBeInTheDocument();
  });

  it('calls keycloak.logout() when sign out is clicked', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
    };
    
    const { UserButton } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<UserButton />);
    
    // Click the sign out button
    fireEvent.click(screen.getByText('Sign out'));
    expect(mockLogout).toHaveBeenCalled();
  });
});

describe('SignedIn', () => {
  it('renders children when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = { sub: 'user-123' };
    
    const { SignedIn } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(
      <SignedIn>
        <div>Protected Content</div>
      </SignedIn>
    );
    
    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });

  it('renders nothing when not loaded', async () => {
    mockKeycloak.authenticated = undefined as unknown as boolean;

    const { SignedIn } = await import('@/components/auth/providers/keycloak/AuthButtons');

    const { container } = render(
      <SignedIn>
        <div>Protected Content</div>
      </SignedIn>
    );

    expect(container.firstChild).toBe(null);
  });

  it('renders nothing when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { SignedIn } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    const { container } = render(
      <SignedIn>
        <div>Protected Content</div>
      </SignedIn>
    );
    
    expect(container.firstChild).toBe(null);
  });
});

describe('SignedOut', () => {
  it('renders children when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { SignedOut } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(
      <SignedOut>
        <div>Public Content</div>
      </SignedOut>
    );
    
    expect(screen.getByText('Public Content')).toBeInTheDocument();
  });

  it('renders nothing when not loaded', async () => {
    mockKeycloak.authenticated = undefined as unknown as boolean;

    const { SignedOut } = await import('@/components/auth/providers/keycloak/AuthButtons');

    const { container } = render(
      <SignedOut>
        <div>Public Content</div>
      </SignedOut>
    );

    expect(container.firstChild).toBe(null);
  });

  it('renders nothing when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = { sub: 'user-123' };
    
    const { SignedOut } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    const { container } = render(
      <SignedOut>
        <div>Public Content</div>
      </SignedOut>
    );
    
    expect(container.firstChild).toBe(null);
  });
});

describe('AuthButtons', () => {
  it('shows loading state when not loaded', async () => {
    // Simulate not loaded state
    mockKeycloak.authenticated = undefined as unknown as boolean;
    
    const { AuthButtons } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    const { container } = render(<AuthButtons />);
    
    // Should have loading skeleton
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows sign in/up buttons when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { AuthButtons } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<AuthButtons />);
    
    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(screen.getByText('Sign up')).toBeInTheDocument();
  });

  it('shows user button when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = {
      sub: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      given_name: 'Test',
    };
    
    const { AuthButtons } = await import('@/components/auth/providers/keycloak/AuthButtons');
    
    render(<AuthButtons />);
    
    // Should show user button with initial
    expect(screen.getByText('T')).toBeInTheDocument();
    expect(screen.queryByText('Sign in')).not.toBeInTheDocument();
  });
});
