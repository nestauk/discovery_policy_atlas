'use client'

import { ReactNode } from 'react'
import { AUTH_PROVIDER } from '../config'
import { ClerkSignInButton } from '../adapters/clerk/ClerkAdapter'

interface SignInButtonProps {
  children: ReactNode
}

/**
 * Trigger the provider's sign-in flow.
 *
 * For Clerk this opens the modal sign-in. For Cognito (Phase 4) this will
 * redirect to the Hosted UI. Callers wrap the child element they want to
 * use as the trigger (typically a `<Button>`).
 */
export function SignInButton({ children }: SignInButtonProps) {
  if (AUTH_PROVIDER === 'clerk') {
    return <ClerkSignInButton mode="modal">{children}</ClerkSignInButton>
  }
  throw new Error(`SignInButton not implemented for provider: ${AUTH_PROVIDER}`)
}
