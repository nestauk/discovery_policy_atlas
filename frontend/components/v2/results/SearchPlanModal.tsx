'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { Settings, Search, Copy, CheckCircle, Info } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { buildSearchParams } from '@/lib/searchParamsUtils'
import type { AnalysisProject } from '@/lib/analysisProjectStore'

interface SearchPlanModalProps {
  project: AnalysisProject
}

export function SearchPlanModal({ project }: SearchPlanModalProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const router = useRouter()

  const searchQuery = project.search_query
  if (!searchQuery) return null

  const copyBooleanQuery = async () => {
    if (!searchQuery.boolean_query) return
    try {
      await navigator.clipboard.writeText(searchQuery.boolean_query)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const startNewSearch = () => {
    const params = buildSearchParams(searchQuery)
    setIsOpen(false)
    router.push(`/v2/search?${params}`)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Settings className="h-4 w-4 mr-2" />
          Search Settings
        </Button>
      </DialogTrigger>
      
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Search Settings</DialogTitle>
        </DialogHeader>
        
        <div className="space-y-4">
          {/* Research Question */}
          <div>
            <h4 className="font-medium mb-2">Research query</h4>
            <p className="text-sm bg-gray-50 p-3 rounded">
              {searchQuery.original_query}
            </p>
          </div>

          {/* Boolean Query */}
          {searchQuery.boolean_query && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <h4 className="font-medium">Boolean query</h4>
                <Tooltip content="Search query used to search the OpenAlex database (generated automatically from the free-text research query)">
                  <Info className="h-4 w-4 text-gray-400 hover:text-gray-600 cursor-help" />
                </Tooltip>
              </div>
              <div className="flex gap-2">
                <code className="flex-1 text-sm text-gray-600 bg-gray-50 p-3 rounded font-mono">
                  {searchQuery.boolean_query}
                </code>
                <Button variant="ghost" size="sm" onClick={copyBooleanQuery}>
                  {copied ? <CheckCircle className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
          )}

          {/* Key Parameters */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="font-medium">Sources:</span>
              <div className="mt-1">
                {searchQuery.sources?.map(source => (
                  <Badge key={source} variant="secondary" className="mr-1">
                    {source === 'openalex' ? 'Academic' : 'Policy'}
                  </Badge>
                ))}
              </div>
            </div>
            
            <div>
              <span className="font-medium">Time Range:</span>
              <div className="mt-1 text-sm text-gray-600">
                {searchQuery.time_preset?.replace('_', ' ').toLowerCase() || 'All time'}
              </div>
            </div>

            {searchQuery.geography_filter?.length ? (
              <div>
                <span className="font-medium">Geography:</span>
                <div className="mt-1">
                  {searchQuery.geography_filter.slice(0, 2).map(geo => (
                    <Badge key={geo} variant="secondary" className="mr-1">
                      {geo}
                    </Badge>
                  ))}
                  {searchQuery.geography_filter.length > 2 && (
                    <span className="text-xs text-gray-500">
                      +{searchQuery.geography_filter.length - 2} more
                    </span>
                  )}
                </div>
              </div>
            ) : null}

            <div>
              <span className="font-medium">Limit:</span>
              <div className="mt-1 text-sm text-gray-600">
                {searchQuery.limit || 200} results
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button variant="outline" onClick={() => setIsOpen(false)}>
              Close
            </Button>
            <Button onClick={startNewSearch}>
              <Search className="h-4 w-4 mr-2" />
              Start New Search
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}