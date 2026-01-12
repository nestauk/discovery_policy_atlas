'use client'

import { useUser, UserButton } from '@clerk/nextjs'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FileText, Folder, Home, Search, FolderOpen, HelpCircle, Zap, ChevronRight, ChevronDown } from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { OrganizationManager } from '@/components/OrganizationManager'

interface ProjectLayoutProps {
  children: React.ReactNode
  params: { projectId: string }
}

const sidebarItems = [
  { name: 'Projects', href: '/projects', icon: FolderOpen },
  { name: 'Search', href: '/search', icon: Search },
  { name: 'FAQ', href: '/faq', icon: HelpCircle },
]

const testItems = [
  { name: 'Test extraction', href: '/test_extraction', icon: Zap },
  { name: 'Extractions', href: '/text_extractions', icon: FileText },
]

export default function ProjectLayout({ children, params: _params }: ProjectLayoutProps) {
  const { isSignedIn, isLoaded, user } = useUser()
  const pathname = usePathname()
  const { activeProject } = useAnalysisProjectStore()
  const [testSectionOpen, setTestSectionOpen] = useState(false)

  if (!isLoaded) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  }

  // Public view - minimal layout with just Results navigation
  if (!isSignedIn) {
    return (
      <div className="flex h-screen bg-slate-50">
        {/* Minimal Sidebar for public view */}
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
                <Folder className="h-4 w-4 text-slate-500 -mt-2.5" />
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">SHARED PROJECT</p>
              </div>
              {activeProject ? (
                <div>
                  <p className="text-sm font-semibold text-slate-900 mb-1">{activeProject.title}</p>
                  <Badge variant="secondary" className="text-xs">
                    Public
                  </Badge>
                </div>
              ) : (
                <p className="text-sm text-slate-600">Loading...</p>
              )}
            </div>
          </div>

          {/* Navigation - Only Results for public view */}
          <div className="p-4 pt-2">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">NAVIGATION</p>
            <nav className="space-y-1">
              <Button
                variant="secondary"
                className="w-full justify-start h-auto p-3 text-left"
              >
                <FileText className="mr-3 h-4 w-4 text-slate-500" />
                <div className="font-medium text-sm">Results</div>
              </Button>
            </nav>
          </div>

          {/* Spacer */}
          <div className="flex-1"></div>

          {/* Sign in prompt */}
          <div className="p-4 border-t border-slate-100">
            <Link href="/login">
              <Button variant="outline" className="w-full">
                <Home className="mr-2 h-4 w-4" />
                Sign in for full access
              </Button>
            </Link>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col ml-64 bg-white">
          {children}
        </div>
      </div>
    )
  }

  // Authenticated view - full layout
  return (
    <div className="flex h-screen bg-slate-50">
      {/* Full Sidebar for authenticated users */}
      <div className="w-64 bg-white border-r border-slate-200 fixed h-full flex flex-col">
        {/* Header */}
        <div className="p-6 pb-4">
          <div className="flex items-center gap-3">
            <div>
              <Link href="/">
                <h1 className="text-2xl font-bold cursor-pointer">🌐 Policy Atlas</h1>
              </Link>
            </div>
          </div>
        </div>

        {/* Active Project */}
        <div className="px-6 pb-4">
          <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
            <div className="flex items-center gap-2 mb-1">
              <Folder className="h-4 w-4 text-slate-500 -mt-2.5" />
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
            
            {/* Results link - currently active */}
            <Button
              variant="secondary"
              className="w-full justify-start h-auto p-3 text-left"
            >
              <FileText className="mr-3 h-4 w-4 text-slate-500" />
              <div className="font-medium text-sm">Results</div>
            </Button>
          </nav>

          {/* Divider */}
          <div className="my-4 border-t border-slate-200"></div>

          {/* Test Section */}
          <div className="space-y-1">
            <Button
              variant="ghost"
              onClick={() => setTestSectionOpen(!testSectionOpen)}
              className="w-full justify-start h-auto p-3 text-left"
            >
              {testSectionOpen ? (
                <ChevronDown className="mr-3 h-4 w-4 text-slate-500" />
              ) : (
                <ChevronRight className="mr-3 h-4 w-4 text-slate-500" />
              )}
              <div className="font-medium text-sm">Test</div>
            </Button>
            
            {testSectionOpen && (
              <div className="ml-4 space-y-1">
                {testItems.map((item) => (
                  <Link key={item.name} href={item.href}>
                    <Button
                      variant={pathname === item.href ? "secondary" : "ghost"}
                      className="w-full justify-start h-auto p-2 text-left"
                    >
                      <item.icon className="mr-3 h-4 w-4 text-slate-500" />
                      <div className="font-medium text-sm">{item.name}</div>
                    </Button>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Spacer */}
        <div className="flex-1"></div>

        {/* User */}
        <div className="p-4 border-t border-slate-100">
          <div className="flex items-start gap-3">
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
            <div className="flex-1 min-w-0 flex flex-col gap-0.5">
              <p className="text-sm font-medium text-slate-900 truncate leading-none">
                {user?.firstName || user?.emailAddresses?.[0]?.emailAddress || 'User'}
              </p>
              <OrganizationManager />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col ml-64 bg-white">
        {children}
      </div>
    </div>
  )
}

