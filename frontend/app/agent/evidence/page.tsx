'use client'

import { Button } from '@/components/ui/button'
import { BookOpen, Search } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function EvidencePage() {
  const router = useRouter()

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <h1 className="text-2xl font-bold text-slate-900">Saved Evidence</h1>
        <p className="text-slate-600 mt-1">Your curated evidence library</p>
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <BookOpen className="h-12 w-12 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Saved Evidence Yet</h3>
              <p className="text-slate-600 mb-6">Save evidence from your searches to build your research library</p>
              <Button 
                onClick={() => router.push('/agent')}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Search className="h-4 w-4 mr-2" />
                Find Evidence
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}