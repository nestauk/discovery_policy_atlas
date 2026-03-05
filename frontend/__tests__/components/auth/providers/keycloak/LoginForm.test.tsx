import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
  login: (options?: { redirectUri?: string }) => mockLogin(options),
  register: (options?: { redirectUri?: string }) => mockRegister(options),
}));

// Mock Lucide icons
vi.mock('lucide-react', () => ({
  LogIn: () => <span data-testid="login-icon">LogIn</span>,
}));

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  // Reset mock state
  resetKeycloakCore(mockKeycloak);
  mockLogin.mockReset();
  mockRegister.mockReset();
  mockLogin.mockResolvedValue(undefined);
  mockRegister.mockResolvedValue(undefined);
  
  // Set env for keycloak
  process.env = makeKeycloakEnv(originalEnv);
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('LoginForm', () => {
  it('shows loading spinner when not loaded', async () => {
    mockKeycloak.authenticated = undefined as unknown as boolean;
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    const { container } = render(<LoginForm />);
    
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows "already signed in" message when authenticated', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = { sub: 'user-123' };
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<LoginForm />);
    
    await waitFor(() => {
      expect(screen.getByText('You are already signed in.')).toBeInTheDocument();
    });
  });

  it('shows login button when not authenticated', async () => {
    mockKeycloak.authenticated = false;
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<LoginForm />);
    
    await waitFor(() => {
      expect(screen.getByText('Continue to Login')).toBeInTheDocument();
    });
    expect(screen.getByText('Sign In')).toBeInTheDocument();
    expect(screen.getByText('You will be redirected to our secure login page.')).toBeInTheDocument();
  });

  it('triggers keycloak.login() when login button clicked', async () => {
    mockKeycloak.authenticated = false;
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<LoginForm />);
    
    await waitFor(() => {
      expect(screen.getByText('Continue to Login')).toBeInTheDocument();
    });
    
    fireEvent.click(screen.getByText('Continue to Login'));
    
    expect(mockLogin).toHaveBeenCalledWith({
      redirectUri: expect.any(String),
    });
  });

  it('uses redirectUrl when provided', async () => {
    mockKeycloak.authenticated = false;
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<LoginForm redirectUrl="https://example.com/dashboard" />);
    
    await waitFor(() => {
      expect(screen.getByText('Continue to Login')).toBeInTheDocument();
    });
    
    fireEvent.click(screen.getByText('Continue to Login'));
    
    expect(mockLogin).toHaveBeenCalledWith({
      redirectUri: 'https://example.com/dashboard',
    });
  });

  it('auto-redirects when autoRedirect is true', async () => {
    mockKeycloak.authenticated = false;
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<LoginForm autoRedirect />);
    
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalled();
    });
  });

  it('does not auto-redirect when already signed in', async () => {
    mockKeycloak.authenticated = true;
    mockKeycloak.tokenParsed = { sub: 'user-123' };
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<LoginForm autoRedirect />);
    
    await waitFor(() => {
      expect(screen.getByText('You are already signed in.')).toBeInTheDocument();
    });
    
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('applies custom className', async () => {
    mockKeycloak.authenticated = false;
    
    const { LoginForm } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    const { container } = render(<LoginForm className="custom-class" />);
    
    await waitFor(() => {
      expect(screen.getByText('Continue to Login')).toBeInTheDocument();
    });
    
    // Card should have the custom class
    const card = container.querySelector('.custom-class');
    expect(card).toBeInTheDocument();
  });
});

describe('SignUpPage', () => {
  it('triggers keycloak.register() on mount', async () => {
    const { SignUpPage } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<SignUpPage />);
    
    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        redirectUri: expect.any(String),
      });
    });
  });

  it('uses custom redirectUrl when provided', async () => {
    const { SignUpPage } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<SignUpPage redirectUrl="https://example.com/welcome" />);
    
    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        redirectUri: 'https://example.com/welcome',
      });
    });
  });

  it('shows redirecting message', async () => {
    const { SignUpPage } = await import('@/components/auth/providers/keycloak/LoginForm');
    
    render(<SignUpPage />);
    
    expect(screen.getByText('Redirecting to registration...')).toBeInTheDocument();
  });
});
