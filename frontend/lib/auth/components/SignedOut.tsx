'use client'

import { ReactNode } from 'react'
import { useAuth } from '../context'

export function SignedOut({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth()
  if (!isLoaded || isSignedIn) return null
  return <>{children}</>
}
