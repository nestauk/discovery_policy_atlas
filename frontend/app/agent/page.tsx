'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { Search } from 'lucide-react'


export default function AgentSearchPage() {
  const [query, setQuery] = useState('')
  const router = useRouter()

  const handleSearch = () => {
    if (!query.trim()) return
    
    // Store search parameters and navigate directly to options page
    const searchParams = new URLSearchParams()
    searchParams.set('query', query.trim())
    
    router.push(`/agent/options?${searchParams.toString()}`)
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-4xl">
          {/* Header */}
          <div className="text-center mb-12">
            {/* <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
              <Search className="h-8 w-8 text-white" />
            </div> */}
            <div className="flex items-center justify-center gap-3 mb-4">
              <h1 className="text-4xl font-bold text-slate-900">
                Find global policy evidence
              </h1>
              <Tooltip content={
                <p className="max-w-xs">
                  Alpha means this is an early prototype with limited functionality. 
                  Features may be incomplete, unstable, or subject to change. 
                  We&apos;re actively developing and improving the tool.
                </p>
              }>
                <Badge variant="default" className="text-xs bg-blue-600 hover:bg-blue-700 text-white font-semibold px-2 py-0.5 -mt-1">ALPHA</Badge>
              </Tooltip>
            </div>
            <p className="text-lg text-slate-600 max-w-2xl mx-auto">
              
            </p>
          </div>

          {/* Search Configuration Card */}
          <Card className="border-0 shadow-lg">
            <CardContent className="p-8">
              <div className="space-y-8">
                {/* Research Question */}
                <div>
                  <label className="block font-medium text-slate-700 mb-3">
                    Research question
                  </label>
                  <div className="relative">
                    <textarea
                      placeholder="e.g., What are the most effective parenting interventions?"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      className="w-full min-h-[120px] p-4 text-base border border-slate-200 rounded-md focus:border-blue-500 focus:ring-blue-500 resize-y"
                      style={{ resize: 'vertical' }}
                    />
                  </div>
                </div>

                {/* Search Button */}
                <div className="pt-4">
                  <Button
                    onClick={handleSearch}
                    disabled={!query.trim()}
                    className="w-full h-12 bg-blue-600 hover:bg-blue-700 text-base font-medium"
                  >
                    <Search className="mr-2 h-4 w-4" />
                    Find Evidence
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}