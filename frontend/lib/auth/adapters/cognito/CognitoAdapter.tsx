'use client'

import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AuthContext } from '../../context'
import { registerExternalTokenGetter } from '../../external'
import type { AuthContextValue, AuthUser } from '../../types'
import { getMissingCognitoEnv } from './config'

interface CognitoAdapterProps {
  children: ReactNode
}

interface SessionResponse {
  authenticated: boolean
  accessToken?: string
  expiresAt?: number | null
  user?: AuthUser
}

/** Refresh the access token slightly before expiry to avoid 401 races. */
const TOKEN_REFRESH_MARGIN_MS = 60_000

/**
 * Cognito adapter for the server-side httpOnly flow (Phase 5).
 *
 * Tokens live in httpOnly cookies on the Next.js origin, set by Amplify's
 * `/api/auth/*` Route Handlers. This adapter never touches client-side
 * Amplify APIs; it:
 *  - reads the session (user + short-lived access token) from
 *    `/api/auth/session` and keeps the access token in memory,
 *  - drives sign-in/out via top-level navigation to the Amplify routes.
 *
 * The refresh token is never exposed to client JS.
 *
 * Limitation (Phase 6): organisation state is always empty until app-owned
 * organisations land.
 */
export function CognitoAdapter({ children }: CognitoAdapterProps) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoaded, setIsLoaded] = useState(false)
  const tokenRef = useRef<{ token: string; expiresAt: number | null } | null>(null)

  const missingVars = useMemo(() => getMissingCognitoEnv(), [])

  const loadSession = useCallback(async (): Promise<string | null> => {
    try {
      const res = await fetch('/api/auth/session', {
        credentials: 'include',
        cache: 'no-store',
      })
      if (!res.ok) {
        tokenRef.current = null
        setUser(null)
        return null
      }
      const data = (await res.json()) as SessionResponse
      if (!data.authenticated || !data.accessToken) {
        tokenRef.current = null
        setUser(null)
        return null
      }
      tokenRef.current = {
        token: data.accessToken,
        expiresAt: data.expiresAt ?? null,
      }
      setUser(data.user ?? null)
      return data.accessToken
    } catch {
      tokenRef.current = null
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    if (missingVars.length > 0) {
      setIsLoaded(true)
      return
    }
    void loadSession().finally(() => setIsLoaded(true))
  }, [loadSession, missingVars.length])

  const getToken = useCallback(async () => {
    const cached = tokenRef.current
    if (
      cached &&
      (cached.expiresAt === null ||
        cached.expiresAt - Date.now() > TOKEN_REFRESH_MARGIN_MS)
    ) {
      return cached.token
    }
    return loadSession()
  }, [loadSession])

  useEffect(() => {
    return registerExternalTokenGetter(getToken)
  }, [getToken])

  const signIn = useCallback(() => {
    window.location.href = '/api/auth/sign-in'
  }, [])

  const signOut = useCallback(async () => {
    window.location.href = '/api/auth/sign-out'
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
      getToken,
      signIn,
      signOut,
    }),
    [isLoaded, user, selectOrganization, getToken, signIn, signOut]
  )

  if (missingVars.length > 0) {
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
