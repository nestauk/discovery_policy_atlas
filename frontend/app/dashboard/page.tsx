'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function DashboardPage() {
  const router = useRouter()
  
  useEffect(() => {
    // Redirect to home page by default
    router.push('/dashboard/home')
  }, [router])

  return null
}