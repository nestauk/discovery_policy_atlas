'use client';

/**
 * Clerk-specific provider root wrapper.
 */

import { ClerkProvider } from '@clerk/nextjs';
import { ReactNode } from 'react';

interface ProviderRootProps {
  children: ReactNode;
}

export function ProviderRoot({ children }: ProviderRootProps) {
  return <ClerkProvider>{children}</ClerkProvider>;
}

// Re-export for direct usage
export { ClerkProvider } from '@clerk/nextjs';
