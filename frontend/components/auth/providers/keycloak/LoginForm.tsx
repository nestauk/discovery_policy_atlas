'use client';

/**
 * Keycloak login form - since Keycloak handles auth via redirect,
 * this component triggers the Keycloak login flow.
 */

import { useEffect, useCallback } from 'react';
import { login, register } from '@/lib/auth/providers/keycloak/client';
import { useUser } from '@/lib/auth/providers/keycloak/hooks';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { LogIn } from 'lucide-react';

interface LoginFormProps {
  /** URL to redirect after successful login */
  redirectUrl?: string;
  /** Automatically trigger login on mount */
  autoRedirect?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Login form component that redirects to Keycloak for authentication.
 * 
 * Unlike Clerk's embedded forms, Keycloak authentication happens
 * on the Keycloak server, so this component triggers a redirect.
 */
export function LoginForm({ 
  redirectUrl, 
  autoRedirect = false,
  className = '' 
}: LoginFormProps) {
  const { isSignedIn, isLoaded } = useUser();

  const handleLogin = useCallback(() => {
    void login({
      redirectUri: redirectUrl || window.location.origin,
    }).catch((err) => {
      console.error('Keycloak login failed:', err);
    });
  }, [redirectUrl]);

  useEffect(() => {
    if (autoRedirect && isLoaded && !isSignedIn) {
      handleLogin();
    }
  }, [autoRedirect, isLoaded, isSignedIn, handleLogin]);

  if (!isLoaded) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (isSignedIn) {
    return (
      <Card className={className}>
        <CardContent className="py-8 text-center">
          <p className="text-sm text-gray-600">You are already signed in.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Sign In</CardTitle>
        <CardDescription>
          You will be redirected to our secure login page.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button 
          onClick={handleLogin} 
          className="w-full"
          size="lg"
        >
          <LogIn className="h-4 w-4 mr-2" />
          Continue to Login
        </Button>
      </CardContent>
    </Card>
  );
}

/**
 * Sign in page wrapper - redirects to Keycloak immediately.
 */
export function SignInPage({ redirectUrl }: { redirectUrl?: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <LoginForm redirectUrl={redirectUrl} autoRedirect className="w-full max-w-md" />
    </div>
  );
}

/**
 * Sign up page - redirects to Keycloak registration.
 */
export function SignUpPage({ redirectUrl }: { redirectUrl?: string }) {
  useEffect(() => {
    void register({
      redirectUri: redirectUrl || window.location.origin,
    }).catch((err) => {
      console.error('Keycloak registration failed:', err);
    });
  }, [redirectUrl]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md">
        <CardContent className="flex items-center justify-center py-8">
          <div className="text-center">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-sm text-gray-600">Redirecting to registration...</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
