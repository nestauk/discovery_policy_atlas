'use client'

import { useUser } from '@clerk/nextjs' // can also output useClerk
import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Search, Brain, Beaker } from 'lucide-react'

const sidebarItems = [
  { name: 'Search', href: '/dashboard/search', icon: Search },
  { name: 'Synthesis', href: '/dashboard/synthesis', icon: Brain },
  { name: 'Simulation', href: '/dashboard/simulation', icon: Beaker },
]

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isSignedIn, isLoaded } = useUser() // can also output user object
  // const { signOut } = useClerk()
  const router = useRouter()
  const pathname = usePathname()

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
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-64 bg-card border-r">
        <nav className="space-y-2 px-3 mt-6">
          {/* <ProjectSelector
            currentQuery=""
            currentFilters={{}}
            onProjectSelect={(query: string, filters: any, projectId: string) => {
              // Navigate to search page with the selected project
              router.push(`/dashboard/search?project=${projectId}`)
            }}
          />
          <div className="border-b border-gray-200 my-2" /> */}
          {sidebarItems.map((item) => (
            <Link key={item.name} href={item.href}>
              <Button
                variant={pathname === item.href ? "secondary" : "ghost"}
                className="w-full justify-start"
              >
                <item.icon className="mr-2 h-4 w-4" />
                {item.name}
              </Button>
            </Link>
          ))}
        </nav>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  )
}