'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Settings, Search, Copy, CheckCircle, Info } from 'lucide-react'
import { useRouter } from 'next/navigation'
import type { AnalysisProject } from '@/lib/analysisProjectStore'

interface SearchPlanModalProps {
  project: AnalysisProject
}

const SOURCE_LABELS: Record<string, string> = {
  openalex: 'Academic literature',
  overton: 'Grey literature',
}

const TIME_PRESET_LABELS: Record<string, string> = {
  LAST_YEAR: 'Last year',
  LAST_2_YEARS: 'Last 2 years',
  LAST_5_YEARS: 'Last 5 years',
  LAST_10_YEARS: 'Last 10 years',
  SINCE_2000: 'Since 2000',
  ANY: 'Any time',
  CUSTOM: 'Custom range',
}

type SearchQueryExtended = {
  research_question?: string
  original_query?: string
  semantic_query?: string
  boolean_queries?: string[]
  boolean_query?: string
  population?: string[]
  outcome?: string[]
  geography?: string[]
  geography_filter?: string[]
  time_preset?: string
  time_from?: string
  time_to?: string
  max_results?: number
  limit?: number
  sources?: string[]
  mode?: string
  relevance_enabled?: boolean
  use_abstracts_only?: boolean
  sub_questions?: string[]
  additional_questions?: string[]
  screening_factors?: string[]
  scope?: string[]
  custom_focus?: string[]
  excludes?: string[]
}

export function SearchPlanModal({ project }: SearchPlanModalProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selectedQueryIndex, setSelectedQueryIndex] = useState(0)
  const router = useRouter()

  const searchQuery = project.search_query as SearchQueryExtended | undefined
  if (!searchQuery) return null

  // Handle both old and new formats
  const researchQuestion = searchQuery.research_question || searchQuery.original_query
  const semanticQuery = searchQuery.semantic_query
  const booleanQueries = searchQuery.boolean_queries || (searchQuery.boolean_query ? [searchQuery.boolean_query] : [])
  const population = searchQuery.population || []
  const outcome = searchQuery.outcome || []
  const geography = searchQuery.geography || searchQuery.geography_filter || []
  const timePreset = searchQuery.time_preset
  const timeFrom = searchQuery.time_from
  const timeTo = searchQuery.time_to
  const maxResults = searchQuery.max_results || searchQuery.limit

  const copyBooleanQuery = async (query: string) => {
    if (!query) return
    try {
      await navigator.clipboard.writeText(query)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const startNewSearch = () => {
    setIsOpen(false)
    router.push('/search')
  }

  const selectedBooleanQuery = booleanQueries[selectedQueryIndex] || ''

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="flex items-center gap-2">
          <Settings className="h-4 w-4" />
          Search Settings
        </Button>
      </DialogTrigger>
      
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader className="pb-3">
          <DialogTitle>Search Settings</DialogTitle>
        </DialogHeader>
        
        <div className="space-y-3">
          {/* Research Question */}
          {researchQuestion && (
            <div>
              <h4 className="font-medium mb-1.5 text-sm">Research query</h4>
              <p className="text-xs bg-gray-50 p-2 rounded">
                {researchQuestion}
              </p>
            </div>
          )}

          {/* Semantic Query */}
          {semanticQuery && (
            <div>
              <h4 className="font-medium mb-1.5 text-sm">Semantic query</h4>
              <p className="text-xs bg-gray-50 p-2 rounded">
                {semanticQuery}
              </p>
            </div>
          )}

          {/* Boolean Queries */}
          {booleanQueries.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <h4 className="font-medium text-sm">
                  Boolean {booleanQueries.length > 1 ? 'queries' : 'query'}
                  {booleanQueries.length > 1 && ` (${booleanQueries.length} variants)`}
                </h4>
                <Tooltip content="Search queries used to search the OpenAlex database (generated automatically from the free-text research query)">
                  <Info className="h-3.5 w-3.5 text-gray-400 hover:text-gray-600 cursor-help" />
                </Tooltip>
              </div>
              
              {booleanQueries.length > 1 && (
                <div className="mb-1.5">
                  <Select value={selectedQueryIndex.toString()} onValueChange={(val) => setSelectedQueryIndex(parseInt(val))}>
                    <SelectTrigger className="w-full h-8 text-sm">
                      <SelectValue placeholder="Select query variant" />
                    </SelectTrigger>
                    <SelectContent>
                      {booleanQueries.map((_, idx) => (
                        <SelectItem key={idx} value={idx.toString()}>
                          Query variant {idx + 1}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="flex gap-2">
                <code className="flex-1 text-xs text-gray-600 bg-gray-50 p-2 rounded font-mono break-all max-h-24 overflow-y-scroll whitespace-pre-wrap block">
                  {selectedBooleanQuery}
                </code>
                <Button variant="ghost" size="sm" onClick={() => copyBooleanQuery(selectedBooleanQuery)} className="flex-shrink-0 h-8 w-8 p-0">
                  {copied ? <CheckCircle className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
              </div>
            </div>
          )}

          {/* Key Parameters */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            {searchQuery.sources && searchQuery.sources.length > 0 && (
              <div>
                <span className="font-medium">Sources:</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {searchQuery.sources.map((source: string) => (
                    <Badge key={source} variant="outline">
                      {SOURCE_LABELS[source] || source}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {timePreset && (
              <div>
                <span className="font-medium">Time window:</span>
                <div className="mt-1">
                  <Badge variant="outline">
                    {TIME_PRESET_LABELS[timePreset] || timePreset.replaceAll('_', ' ')}
                  </Badge>
                  {(timePreset === 'CUSTOM' || (timeFrom && timeTo)) && (
                    <div className="text-xs text-gray-600 mt-1">
                      {timeFrom && new Date(timeFrom).toLocaleDateString()} - {timeTo && new Date(timeTo).toLocaleDateString()}
                    </div>
                  )}
                </div>
              </div>
            )}

            {geography.length > 0 && (
              <div>
                <span className="font-medium">Geography:</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {geography.map((geo: string) => (
                    <Badge key={geo} variant="outline">
                      {geo}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {maxResults && (
              <div>
                <span className="font-medium">Max results:</span>
                <div className="mt-1">{maxResults}</div>
              </div>
            )}

            {searchQuery.mode && (
              <div>
                <span className="font-medium">Search mode:</span>
                <div className="mt-1">
                  <Badge variant="outline">{searchQuery.mode}</Badge>
                </div>
              </div>
            )}
          </div>

          {/* Population */}
          {population.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Population</h4>
              <div className="flex flex-wrap gap-1">
                {population.map((item: string, idx: number) => (
                  <Badge key={idx} variant="outline" className="text-xs py-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Outcome */}
          {outcome.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Outcome</h4>
              <div className="flex flex-wrap gap-1">
                {outcome.map((item: string, idx: number) => (
                  <Badge key={idx} variant="outline" className="text-xs py-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Sub Questions */}
          {searchQuery.sub_questions && searchQuery.sub_questions.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Sub questions</h4>
              <ul className="text-xs text-gray-700 space-y-0.5 list-disc list-inside">
                {searchQuery.sub_questions.map((q, idx) => (
                  <li key={idx}>{q}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Additional Questions */}
          {searchQuery.additional_questions && searchQuery.additional_questions.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Additional questions</h4>
              <ul className="text-xs text-gray-700 space-y-0.5 list-disc list-inside">
                {searchQuery.additional_questions.map((q, idx) => (
                  <li key={idx}>{q}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Screening Factors */}
          {searchQuery.screening_factors && searchQuery.screening_factors.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Screening factors</h4>
              <div className="flex flex-wrap gap-1">
                {searchQuery.screening_factors.map((item, idx) => (
                  <Badge key={idx} variant="outline" className="text-xs py-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Scope */}
          {searchQuery.scope && searchQuery.scope.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Scope</h4>
              <div className="flex flex-wrap gap-1">
                {searchQuery.scope.map((item) => (
                  <Badge key={item} variant="outline" className="text-xs py-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Custom Focus */}
          {searchQuery.custom_focus && searchQuery.custom_focus.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Custom focus</h4>
              <div className="flex flex-wrap gap-1">
                {searchQuery.custom_focus.map((item) => (
                  <Badge key={item} variant="outline" className="text-xs py-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Excludes */}
          {searchQuery.excludes && searchQuery.excludes.length > 0 && (
            <div>
              <h4 className="font-medium mb-1 text-xs">Exclusions</h4>
              <div className="flex flex-wrap gap-1">
                {searchQuery.excludes.map((item) => (
                  <Badge key={item} variant="outline" className="bg-red-50 text-red-700 border-red-200 text-xs py-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Start New Search Button */}
          <div className="pt-2 border-t">
            <Button onClick={startNewSearch} className="w-full h-9" variant="default">
              <Search className="h-3.5 w-3.5 mr-2" />
              Start new search
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
