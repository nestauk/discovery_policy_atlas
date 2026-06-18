'use client'

import { Children, cloneElement, isValidElement, MouseEvent, ReactElement, ReactNode } from 'react'
import { useAuth } from '../context'

interface SignInButtonProps {
  children: ReactNode
}

/**
 * Trigger the provider's sign-in flow.
 *
 * Wraps a single child element and routes its click through the auth
 * adapter (Clerk opens the modal sign-in via `openSignIn()`; Cognito
 * redirects to the Hosted UI). Any existing `onClick` on the child is
 * preserved and runs before sign-in; if the child calls
 * `event.preventDefault()`, sign-in is skipped.
 */
export function SignInButton({ children }: SignInButtonProps) {
  const { signIn } = useAuth()
  const child = Children.only(children)
  if (!isValidElement(child)) return null

  type Clickable = { onClick?: (e: MouseEvent) => void }
  const childElement = child as ReactElement<Clickable>
  const existingOnClick = childElement.props.onClick

  const onClick = (event: MouseEvent) => {
    existingOnClick?.(event)
    if (!event.defaultPrevented) {
      signIn()
    }
  }

  return cloneElement(childElement, { onClick })
}
