'use client'

import { ReactNode, useCallback, useEffect, useMemo } from 'react'
import {
  ClerkProvider,
  useAuth as useClerkAuth,
  useUser as useClerkUser,
  useOrganization,
  useOrganizationList,
  useSession,
  useClerk,
  SignInButton as ClerkSignInButton,
  UserButton as ClerkUserButton,
} from '@clerk/nextjs'

import { AuthContext } from '../../context'
import { registerExternalTokenGetter } from '../../external'
import type {
  AuthContextValue,
  AuthMembership,
  AuthOrganization,
  AuthUser,
} from '../../types'

interface ClerkAdapterProps {
  children: ReactNode
}

export function ClerkAdapter({ children }: ClerkAdapterProps) {
  return (
    <ClerkProvider>
      <ClerkContextBridge>{children}</ClerkContextBridge>
    </ClerkProvider>
  )
}

function ClerkContextBridge({ children }: { children: ReactNode }) {
  const { isLoaded: authLoaded, isSignedIn, getToken, signOut: clerkSignOut } =
    useClerkAuth()
  const { user: clerkUser, isLoaded: userLoaded } = useClerkUser()
  const { organization: clerkOrg, isLoaded: orgLoaded } = useOrganization()
  const {
    userMemberships,
    isLoaded: listLoaded,
    setActive,
  } = useOrganizationList({ userMemberships: { infinite: true } })
  const { session } = useSession()
  const { openSignIn } = useClerk()

  const fetchToken = useCallback(async () => {
    try {
      return await getToken()
    } catch {
      return null
    }
  }, [getToken])

  useEffect(() => {
    return registerExternalTokenGetter(fetchToken)
  }, [fetchToken])

  const user = useMemo<AuthUser | null>(() => {
    if (!clerkUser) return null
    return {
      id: clerkUser.id,
      email: clerkUser.emailAddresses?.[0]?.emailAddress ?? undefined,
      name: clerkUser.fullName ?? undefined,
      firstName: clerkUser.firstName ?? undefined,
      imageUrl: clerkUser.imageUrl ?? undefined,
    }
  }, [clerkUser])

  const organization = useMemo<AuthOrganization | null>(() => {
    if (!clerkOrg) return null
    return {
      id: clerkOrg.id,
      name: clerkOrg.name ?? undefined,
      slug: clerkOrg.slug ?? undefined,
    }
  }, [clerkOrg])

  const organizations = useMemo<AuthMembership[]>(() => {
    if (!userMemberships?.data) return []
    return userMemberships.data.map((membership) => ({
      id: membership.organization.id,
      name: membership.organization.name,
      slug: membership.organization.slug ?? undefined,
      role: membership.role ?? undefined,
    }))
  }, [userMemberships])

  const selectOrganization = useCallback(
    async (organizationId: string) => {
      if (!setActive) return
      await setActive({ organization: organizationId })
      // Forces the next token request to include the new org claims.
      await session?.getToken({ skipCache: true })
    },
    [setActive, session]
  )

  const signIn = useCallback(() => {
    openSignIn()
  }, [openSignIn])

  const signOut = useCallback(async () => {
    await clerkSignOut()
  }, [clerkSignOut])

  const value = useMemo<AuthContextValue>(
    () => ({
      isLoaded: authLoaded && userLoaded,
      isSignedIn: Boolean(isSignedIn),
      user,
      organization,
      organizations,
      organizationsLoaded: orgLoaded && listLoaded,
      selectOrganization,
      getToken: fetchToken,
      signIn,
      signOut,
    }),
    [
      authLoaded,
      userLoaded,
      isSignedIn,
      user,
      organization,
      organizations,
      orgLoaded,
      listLoaded,
      selectOrganization,
      fetchToken,
      signIn,
      signOut,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export { ClerkSignInButton, ClerkUserButton }
