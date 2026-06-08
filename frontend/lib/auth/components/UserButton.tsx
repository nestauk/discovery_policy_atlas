'use client'

import dynamic from 'next/dynamic'
import { AUTH_PROVIDER } from '../config'

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
 * For Clerk this is the provider's own widget. For Cognito it's a small
 * custom popover built on the existing radix dropdown primitives; the
 * `appearance` prop is ignored because Cognito has no equivalent styling
 * system.
 *
 * Each implementation is lazy-loaded so the inactive provider's SDK never
 * runs (avoids Clerk's React SDK throwing on missing publishable key when
 * we're in Cognito mode, and keeps the Amplify chunk out of Clerk
 * builds).
 */

const ClerkUserButton = dynamic(
  () => import('@clerk/nextjs').then((m) => ({ default: m.UserButton })),
  { ssr: true }
)

const CognitoUserButton = dynamic(
  () =>
    import('../adapters/cognito/CognitoUserButton').then((m) => ({
      default: m.CognitoUserButton,
    })),
  { ssr: false }
)

export function UserButton({ appearance }: UserButtonProps = {}) {
  if (AUTH_PROVIDER === 'clerk') {
    return <ClerkUserButton appearance={appearance} />
  }
  if (AUTH_PROVIDER === 'cognito') {
    return <CognitoUserButton />
  }
  throw new Error(`UserButton not implemented for provider: ${AUTH_PROVIDER}`)
}
