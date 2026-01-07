'use client'

import { useEffect } from 'react'
import { useOrganization, useOrganizationList, useSession } from '@clerk/nextjs'
import { Building2 } from 'lucide-react'

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

  // If user has no organizations, show nothing (or a message)
  if (!organization && (!userMemberships?.data || userMemberships.data.length === 0)) {
    return (
      <div className="px-6 pb-4">
        <div className="bg-amber-50 rounded-lg p-3 border border-amber-200">
          <div className="flex items-center gap-2">
            <Building2 className="h-4 w-4 text-amber-600" />
            <p className="text-xs text-amber-700">No organization assigned</p>
          </div>
        </div>
      </div>
    )
  }

  // Show current organization
  if (organization) {
    return (
      <div className="px-6 pb-2">
        <div className="flex items-center gap-2 text-slate-500">
          <Building2 className="h-3.5 w-3.5" />
          <p className="text-xs font-medium truncate">{organization.name}</p>
        </div>
      </div>
    )
  }

  // Still loading/selecting
  return (
    <div className="px-6 pb-2">
      <div className="flex items-center gap-2 text-slate-400">
        <Building2 className="h-3.5 w-3.5" />
        <p className="text-xs">Loading organization...</p>
      </div>
    </div>
  )
}

