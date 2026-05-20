'use client'

import { ReactNode } from 'react'
import { useAuth } from '../context'

export function SignedIn({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth()
  if (!isLoaded || !isSignedIn) return null
  return <>{children}</>
}
