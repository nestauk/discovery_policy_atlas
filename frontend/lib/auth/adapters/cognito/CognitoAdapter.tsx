'use client'

import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAuthSession,
  getCurrentUser,
  signInWithRedirect,
  signOut as amplifySignOut,
} from 'aws-amplify/auth'
import { Hub } from 'aws-amplify/utils'

import { AuthContext } from '../../context'
import { registerExternalTokenGetter } from '../../external'
import type { AuthContextValue, AuthUser } from '../../types'
import { configureAmplify } from './config'

interface CognitoAdapterProps {
  children: ReactNode
}

/**
 * Cognito-backed implementation of the auth context.
 *
 * Wraps Amplify's Hub events into the same surface as the Clerk adapter so
 * the rest of the app stays provider-agnostic.
 *
 * Limitations (resolved in Phase 5 + 6):
 *  - Tokens live in localStorage (XSS-exposed). Phase 5 moves them behind
 *    httpOnly cookies via Next.js Route Handlers.
 *  - Organisation state is always empty. Phase 6 introduces app-owned
 *    organisations + memberships.
 */
export function CognitoAdapter({ children }: CognitoAdapterProps) {
  const [configReady, setConfigReady] = useState(false)
  const [missingVars, setMissingVars] = useState<string[]>([])
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoaded, setIsLoaded] = useState(false)

  useEffect(() => {
    const status = configureAmplify()
    setConfigReady(status.configured)
    setMissingVars(status.missing)
    if (!status.configured) {
      setIsLoaded(true)
    }
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const currentUser = await getCurrentUser()
      const { tokens } = await fetchAuthSession()
      const idPayload = tokens?.idToken?.payload as Record<string, unknown> | undefined
      const email =
        typeof idPayload?.email === 'string' ? (idPayload.email as string) : undefined
      const name =
        typeof idPayload?.name === 'string' ? (idPayload.name as string) : undefined
      const givenName =
        typeof idPayload?.given_name === 'string'
          ? (idPayload.given_name as string)
          : undefined

      setUser({
        id: currentUser.userId,
        email,
        name: name ?? givenName ?? currentUser.username,
        firstName: givenName,
      })
    } catch {
      setUser(null)
    } finally {
      setIsLoaded(true)
    }
  }, [])

  useEffect(() => {
    if (!configReady) return
    void refreshUser()

    const stop = Hub.listen('auth', ({ payload }) => {
      switch (payload.event) {
        case 'signedIn':
        case 'tokenRefresh':
        case 'signInWithRedirect':
          void refreshUser()
          break
        case 'signedOut':
          setUser(null)
          break
        case 'signInWithRedirect_failure':
        case 'tokenRefresh_failure':
          setUser(null)
          break
      }
    })

    return () => {
      stop()
    }
  }, [configReady, refreshUser])

  const fetchToken = useCallback(async () => {
    try {
      const { tokens } = await fetchAuthSession()
      return tokens?.accessToken?.toString() ?? null
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    return registerExternalTokenGetter(fetchToken)
  }, [fetchToken])

  const signIn = useCallback(() => {
    void signInWithRedirect()
  }, [])

  const signOut = useCallback(async () => {
    await amplifySignOut()
    setUser(null)
  }, [])

  const selectOrganization = useCallback(async () => {
    // No-op until Phase 6 introduces app-owned organisations.
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      isLoaded,
      isSignedIn: Boolean(user),
      user,
      organization: null,
      organizations: [],
      organizationsLoaded: true,
      selectOrganization,
      getToken: fetchToken,
      signIn,
      signOut,
    }),
    [isLoaded, user, selectOrganization, fetchToken, signIn, signOut]
  )

  if (!configReady && missingVars.length > 0) {
    return (
      <div
        style={{
          fontFamily: 'sans-serif',
          maxWidth: 640,
          margin: '80px auto',
          padding: '0 16px',
          color: '#b45309',
        }}
      >
        <h2>Cognito not configured</h2>
        <p>
          Set the following environment variables in <code>frontend/.env.local</code>{' '}
          before starting the app with <code>NEXT_PUBLIC_AUTH_PROVIDER=cognito</code>:
        </p>
        <ul>
          {missingVars.map((name) => (
            <li key={name}>
              <code>{name}</code>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
