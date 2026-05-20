'use client'

import { AUTH_PROVIDER } from '../config'
import { ClerkUserButton } from '../adapters/clerk/ClerkAdapter'

export interface UserButtonAppearance {
  elements?: {
    avatarBox?: string
    userButtonPopoverCard?: string
    userButtonPopoverActionButton?: string
    userButtonPopoverActionButtonText?: string
  }
}

interface UserButtonProps {
  appearance?: UserButtonAppearance
}

/**
 * User avatar with a dropdown for account actions.
 *
 * For Clerk this is the provider's own component (which the codebase
 * already styles via `appearance`). For Cognito (Phase 4) this will be a
 * small custom popover built on Ant Design that consumes `useAuth().user`.
 */
export function UserButton({ appearance }: UserButtonProps = {}) {
  if (AUTH_PROVIDER === 'clerk') {
    return <ClerkUserButton appearance={appearance} />
  }
  throw new Error(`UserButton not implemented for provider: ${AUTH_PROVIDER}`)
}
