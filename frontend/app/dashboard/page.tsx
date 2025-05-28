'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function DashboardPage() {
  const router = useRouter()
  
  useEffect(() => {
    // Redirect to search page by default
    router.push('/dashboard/search')
  }, [router])

  return null
}