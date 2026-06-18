'use client'

import { useEffect } from 'react'
import { Home } from 'lucide-react'
import { useAuth } from '@/lib/auth'

/**
 * Auto-selects the first membership when the user has no active org and
 * displays the current organisation name in the sidebar.
 *
 * Users with multiple memberships still switch via the provider's user
 * menu (Clerk's `<UserButton>` today; will become a custom org switcher
 * in Phase 6).
 */
export function OrganizationManager() {
  const {
    organization,
    organizations,
    organizationsLoaded,
    selectOrganization,
  } = useAuth()

  useEffect(() => {
    if (!organizationsLoaded) return
    if (organization || organizations.length === 0) return

    const first = organizations[0]
    selectOrganization(first.id).catch((err) => {
      console.error('Failed to auto-select organisation:', err)
    })
  }, [organization, organizations, organizationsLoaded, selectOrganization])

  if (!organizationsLoaded) return null

  if (!organization && organizations.length === 0) {
    return null
  }

  if (organization) {
    return (
      <div className="flex items-center gap-1.5 text-slate-500">
        <Home className="h-3 w-3 flex-shrink-0" />
        <span className="text-xs truncate">{organization.name ?? organization.slug ?? ''}</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 text-slate-400">
      <Home className="h-3 w-3 flex-shrink-0" />
      <span className="text-xs">Loading...</span>
    </div>
  )
}
