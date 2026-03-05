'use client';

/**
 * Clerk-specific LoginForm component.
 */

import { SignIn } from '@clerk/nextjs';

export function LoginForm() {
  return (
    <div className="flex justify-center items-center min-h-[400px]">
      <SignIn />
    </div>
  );
}

// Re-export for direct usage
export { SignIn } from '@clerk/nextjs';
