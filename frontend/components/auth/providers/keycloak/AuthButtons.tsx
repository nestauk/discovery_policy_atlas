'use client';

/**
 * Keycloak-specific authentication buttons.
 */

import { ReactNode } from 'react';
import { login, register, logout } from '@/lib/auth/providers/keycloak/client';
import { useUser } from '@/lib/auth/providers/keycloak/hooks';
import { Button } from '@/components/ui/button';
import { LogIn, LogOut } from 'lucide-react';

/**
 * Sign in button that triggers Keycloak login.
 */
export function SignInButton({ 
  children, 
  mode: _mode = 'redirect' // modal not supported by Keycloak, always redirects
}: { 
  children?: ReactNode;
  mode?: 'redirect' | 'modal';
}) {
  const handleLogin = () => {
    login().catch((err) => {
      console.error('Keycloak login failed:', err);
    });
  };

  return (
    <span onClick={handleLogin} className="cursor-pointer">
      {children || (
        <Button variant="default" size="sm">
          <LogIn className="h-4 w-4 mr-2" />
          Sign in
        </Button>
      )}
    </span>
  );
}

/**
 * Sign up button - redirects to Keycloak registration.
 */
export function SignUpButton({ children }: { children?: ReactNode }) {
  const handleRegister = () => {
    register().catch((err) => {
      console.error('Keycloak registration failed:', err);
    });
  };

  return (
    <span onClick={handleRegister} className="cursor-pointer">
      {children || (
        <Button variant="outline" size="sm">
          Sign up
        </Button>
      )}
    </span>
  );
}

/**
 * User button that shows user info and logout option.
 */
export function UserButton({ 
  appearance 
}: { 
  appearance?: { elements?: Record<string, string> };
}) {
  const { user, isSignedIn } = useUser();

  if (!isSignedIn || !user) {
    return null;
  }

  const handleLogout = () => {
    logout().catch((err) => {
      console.error('Keycloak logout failed:', err);
    });
  };

  const initials = user.firstName?.[0] || user.email?.[0] || 'U';

  return (
    <div className="relative group">
      <button 
        className={`w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-medium ${appearance?.elements?.avatarBox || ''}`}
        title={user.fullName || user.email || 'User'}
      >
        {initials.toUpperCase()}
      </button>
      <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
        <div className="p-3 border-b border-gray-100">
          <p className="text-sm font-medium text-gray-900 truncate">
            {user.fullName || 'User'}
          </p>
          <p className="text-xs text-gray-500 truncate">{user.email}</p>
        </div>
        <button
          onClick={handleLogout}
          className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </div>
  );
}

/**
 * Wrapper that renders children only when signed in.
 */
export function SignedIn({ children }: { children: ReactNode }) {
  const { isSignedIn, isLoaded } = useUser();

  if (!isLoaded || !isSignedIn) {
    return null;
  }

  return <>{children}</>;
}

/**
 * Wrapper that renders children only when signed out.
 */
export function SignedOut({ children }: { children: ReactNode }) {
  const { isSignedIn, isLoaded } = useUser();

  if (!isLoaded || isSignedIn) {
    return null;
  }

  return <>{children}</>;
}

/**
 * Combined auth buttons component.
 */
export function AuthButtons() {
  const { isSignedIn, isLoaded } = useUser();

  if (!isLoaded) {
    return <div className="w-8 h-8 bg-gray-200 rounded-full animate-pulse" />;
  }

  if (isSignedIn) {
    return (
      <div className="flex items-center gap-2">
        <UserButton />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <SignInButton />
      <SignUpButton />
    </div>
  );
}
