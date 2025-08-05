'use client'

import { Button } from '@/components/ui/button'
import { History, Search } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function HistoryPage() {
  const router = useRouter()

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <h1 className="text-2xl font-bold text-slate-900">Search History</h1>
        <p className="text-slate-600 mt-1">Previous searches and saved queries</p>
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <History className="h-12 w-12 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Search History Yet</h3>
              <p className="text-slate-600 mb-6">Start searching to see your previous queries here</p>
              <Button 
                onClick={() => router.push('/agent')}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Search className="h-4 w-4 mr-2" />
                Start Searching
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}