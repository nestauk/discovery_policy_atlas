'use client'

import { useEffect } from 'react'
import { useOrganization, useOrganizationList, useSession } from '@clerk/nextjs'
import { Home } from 'lucide-react'

/**
 * Handles organization auto-selection and displays current org.
 * 
 * - If user has no active org but belongs to orgs, auto-selects the first one
 * - Shows the current organization name in the sidebar
 * - For users with multiple orgs, they can use Clerk's UserButton to switch
 */
export function OrganizationManager() {
  const { organization, isLoaded: orgLoaded } = useOrganization()
  const { userMemberships, isLoaded: listLoaded, setActive } = useOrganizationList({
    userMemberships: { infinite: true }
  })
  const { session } = useSession()

  // Auto-select organization if user has orgs but none is active
  useEffect(() => {
    if (!orgLoaded || !listLoaded) return
    
    // If no active org but user has memberships, auto-select the first one
    if (!organization && userMemberships?.data && userMemberships.data.length > 0) {
      const firstOrg = userMemberships.data[0].organization
      console.log(`Auto-selecting organization: ${firstOrg.name}`)
      setActive?.({ organization: firstOrg.id })
        .then(() => {
          // Force token refresh to include new org claims
          session?.getToken({ skipCache: true })
          console.log('Organization set, token refreshed')
        })
    }
  }, [organization, userMemberships, orgLoaded, listLoaded, setActive, session])

  // Don't render anything until loaded
  if (!orgLoaded || !listLoaded) {
    return null
  }

  // If user has no organizations, show nothing
  if (!organization && (!userMemberships?.data || userMemberships.data.length === 0)) {
    return null
  }

  // Show current organization
  if (organization) {
    return (
      <div className="flex items-center gap-1.5 text-slate-500">
        <Home className="h-3 w-3 flex-shrink-0" />
        <span className="text-xs truncate">{organization.name}</span>
      </div>
    )
  }

  // Still loading/selecting
  return (
    <div className="flex items-center gap-1.5 text-slate-400">
      <Home className="h-3 w-3 flex-shrink-0" />
      <span className="text-xs">Loading...</span>
    </div>
  )
}

