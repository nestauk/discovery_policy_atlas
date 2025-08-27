'use client'

import { useUser, UserButton } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Search, FileText, FolderOpen, Folder } from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'

const sidebarItems = [
  { name: 'Projects', href: '/v2/projects', icon: FolderOpen },
  { name: 'Search', href: '/v2/search', icon: Search },  
  { name: 'Results', href: '/v2/results', icon: FileText },
  // { name: 'Search History', href: '/agent/history', icon: History },
]

// const quickStats = [
//   { label: 'Searches Today', value: '12' },
//   { label: 'Evidence Saved', value: '47' },
//   { label: 'Policy Areas', value: '8' },
// ]

export default function AgentLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isSignedIn, isLoaded, user } = useUser()
  const router = useRouter()
  const pathname = usePathname()
  const { activeProject } = useAnalysisProjectStore()

  useEffect(() => {
    if (!isLoaded) return
    if (!isSignedIn) router.push('/login')
  }, [isSignedIn, isLoaded, router])

  if (!isLoaded) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  }

  if (!isSignedIn) {
    return null
  }

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <div className="w-64 bg-white border-r border-slate-200 fixed h-full flex flex-col">
        {/* Header */}
        <div className="p-6 pb-4">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-2xl font-bold">🌐 Policy Atlas</h1>
            </div>
          </div>
        </div>

        {/* Active Project */}
        <div className="px-6 pb-4">
          <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
            <div className="flex items-center gap-2 mb-1">
              <Folder className="h-3 w-3 text-slate-500" />
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">ACTIVE PROJECT</p>
            </div>
            {activeProject ? (
              <div>
                <p className="text-sm font-semibold text-slate-900 mb-1">{activeProject.title}</p>
                <div className="flex items-center gap-2">
                  <Badge variant={
                    activeProject.status === 'completed' ? 'default' :
                    activeProject.status === 'running' ? 'secondary' :
                    activeProject.status === 'failed' ? 'destructive' : 'outline'
                  } className="text-xs">
                    {activeProject.status}
                  </Badge>
                  {activeProject.total_references > 0 && (
                    <span className="text-xs text-slate-500">
                      {activeProject.total_references} refs
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-600">No project selected</p>
            )}
          </div>
        </div>

        {/* Navigation */}
        <div className="p-4 pt-2">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">NAVIGATION</p>
          <nav className="space-y-1">
            {sidebarItems.map((item) => (
              <Link key={item.name} href={item.href}>
                <Button
                  variant={pathname === item.href ? "secondary" : "ghost"}
                  className="w-full justify-start h-auto p-3 text-left"
                >
                  <item.icon className="mr-3 h-4 w-4 text-slate-500" />
                  <div className="font-medium text-sm">{item.name}</div>
                </Button>
              </Link>
            ))}
          </nav>
        </div>

        {/* Spacer to push user section to bottom */}
        <div className="flex-1"></div>

        {/* User */}
        <div className="p-4 border-t border-slate-100">
          <div className="flex items-center gap-3">
            <div className="flex-shrink-0">
              <UserButton 
                appearance={{
                  elements: {
                    avatarBox: "w-8 h-8",
                    userButtonPopoverCard: "shadow-lg border border-slate-200",
                    userButtonPopoverActionButton: "hover:bg-slate-50",
                    userButtonPopoverActionButtonText: "text-slate-700"
                  }
                }}
              />
            </div>
            <div className="flex-1 min-w-0 flex items-center">
              <p className="text-sm font-medium text-slate-900 truncate leading-none">
                {user?.firstName || user?.emailAddresses?.[0]?.emailAddress || 'User'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col ml-64">
        {children}
      </div>
    </div>
  )
}