'use client'

import { useUser, UserButton } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Search, FileText, FolderOpen, Folder, Zap, ChevronRight, ChevronDown, HelpCircle } from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { FeedbackButton } from '@/components/ui/feedback-button'
import { FeedbackModal } from '@/components/ui/feedback-modal'
import { useFeedbackStore, fetchProjectFeedback, saveProjectFeedback } from '@/lib/feedbackStore'
import { fetchEvidenceCategories } from '@/lib/evidenceCategories'

const sidebarItems = [
  { name: 'Projects', href: '/projects', icon: FolderOpen },
  { name: 'Search', href: '/search', icon: Search },
  { name: 'Results', href: '/results', icon: FileText },
  { name: 'FAQ', href: '/faq', icon: HelpCircle },
]

const testItems = [
  { name: 'Test extraction', href: '/test_extraction', icon: Zap },
  { name: 'Extractions', href: '/text_extractions', icon: FileText },
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
  const [testSectionOpen, setTestSectionOpen] = useState(false)
  
  // Feedback state
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false)
  const { isLoading, setFeedback, setLoading, getFeedback } = useFeedbackStore()
  
  // Load feedback when active project changes
  useEffect(() => {
    if (activeProject?.id && !getFeedback(activeProject.id)) {
      setLoading(true)
      fetchProjectFeedback(activeProject.id)
        .then((feedbackData) => {
          setFeedback(activeProject.id, feedbackData)
        })
        .catch((error) => {
          console.error('Failed to load feedback:', error)
        })
        .finally(() => {
          setLoading(false)
        })
    }
  }, [activeProject?.id, getFeedback, setFeedback, setLoading])

  const handleFeedbackSubmit = async (feedbackData: { rating: number; comment: string }) => {
    if (!activeProject?.id) return

    setLoading(true)
    try {
      const savedFeedback = await saveProjectFeedback(activeProject.id, feedbackData)
      setFeedback(activeProject.id, savedFeedback)
      setFeedbackModalOpen(false)
    } catch (error) {
      console.error('Failed to save feedback:', error)
      // You might want to show a toast notification here
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!isLoaded) return
    if (!isSignedIn) router.push('/login')
  }, [isSignedIn, isLoaded, router])

  // Prime evidence categories cache from backend API
  useEffect(() => {
    fetchEvidenceCategories()
  }, [])

  // Auto-expand test section if user is on a test page
  useEffect(() => {
    const isOnTestPage = testItems.some(item => pathname === item.href)
    if (isOnTestPage) {
      setTestSectionOpen(true)
    }
  }, [pathname])

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
            
            {/* Feedback Button */}
            {activeProject && (
              <FeedbackButton
                onClick={() => setFeedbackModalOpen(true)}
                hasFeedback={!!getFeedback(activeProject.id)}
                className="mt-2"
              />
            )}
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
      <div className="flex-1 flex flex-col ml-64 bg-white">
        {children}
      </div>

      {/* Feedback Modal */}
      {activeProject && (
        <FeedbackModal
          isOpen={feedbackModalOpen}
          onClose={() => setFeedbackModalOpen(false)}
          onSubmit={handleFeedbackSubmit}
          projectTitle={activeProject.title}
          existingFeedback={getFeedback(activeProject.id)}
          isLoading={isLoading}
        />
      )}
    </div>
  )
}