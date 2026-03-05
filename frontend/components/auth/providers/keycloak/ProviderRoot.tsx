'use client';

/**
 * Keycloak-specific provider root wrapper.
 * Initializes Keycloak and manages authentication state.
 */

import { ReactNode, useEffect, useState } from 'react';
import { initKeycloak, getKeycloakInstance } from '@/lib/auth/providers/keycloak/client';

interface ProviderRootProps {
  children: ReactNode;
}

export function ProviderRoot({ children }: ProviderRootProps) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    initKeycloak()
      .then(() => {
        if (isMounted) {
          setReady(true);
        }
      })
      .catch((err) => {
        console.error('Keycloak initialization failed:', err);
        if (isMounted) {
          setError('Authentication initialization failed');
          setReady(true); // Allow app to render even if init fails
        }
      });

    // Set up token refresh interval
    const keycloak = getKeycloakInstance();
    const refreshInterval = setInterval(() => {
      if (keycloak.authenticated) {
        keycloak.updateToken(60).catch(() => {
          console.warn('Token refresh failed, user may need to re-login');
        });
      }
    }, 30_000); // Refresh every 30 seconds

    return () => {
      isMounted = false;
      clearInterval(refreshInterval);
    };
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Initializing authentication...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center text-red-600">
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
