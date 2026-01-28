'use client'

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { Loader2 } from 'lucide-react'

export default function ResultsRedirectPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { activeProject } = useAnalysisProjectStore()
  
  useEffect(() => {
    // Check for project_id in URL (legacy links)
    const urlProjectId = searchParams.get('project_id')
    
    if (urlProjectId) {
      // Redirect to the new URL structure
      router.replace(`/projects/${urlProjectId}`)
    } else if (activeProject?.id) {
      // If there's an active project, go to its results
      router.replace(`/projects/${activeProject.id}`)
    } else {
      // Otherwise, go to projects list
      router.replace('/projects')
    }
  }, [router, searchParams, activeProject?.id])

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
        <p className="text-slate-600">Redirecting...</p>
      </div>
    </div>
  )
}
