'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Settings, Copy, CheckCircle, Info, RefreshCw } from 'lucide-react'
import { useRouter } from 'next/navigation'
import type { AnalysisProject } from '@/lib/analysisProjectStore'
import { useWizard } from '@/components/search/SearchWizard'

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

const GEO_LABELS: Record<string, string> = {
  All: 'Anywhere',
  'All but UK': 'Anywhere but UK',
}

export function SearchPlanModal({ project }: SearchPlanModalProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selectedQueryIndex, setSelectedQueryIndex] = useState(0)
  const router = useRouter()

  const searchQuery = project.search_query
  if (!searchQuery) return null

  // Handle both old and new formats
  const researchQuestion = searchQuery.research_question || searchQuery.original_query
  const semanticQuery = searchQuery.semantic_query
  const booleanQueries = searchQuery.boolean_queries || (searchQuery.boolean_query ? [searchQuery.boolean_query] : [])
  const population = searchQuery.population || []
  const innerSetting = searchQuery.inner_setting || []
  const outcome = searchQuery.outcome || []
  const geography = searchQuery.geography || searchQuery.geography_filter || []
  const timePreset = searchQuery.time_preset
  const timeFrom = searchQuery.time_from
  const timeTo = searchQuery.time_to
  const maxResults = searchQuery.max_results || searchQuery.limit
  const implementationConstraints = searchQuery.implementation_constraints
  const hasImplementationConstraints = !!implementationConstraints && [
    implementationConstraints.cost,
    implementationConstraints.staffing,
    implementationConstraints.implementation_complexity,
  ].some((value) => value && value.toLowerCase() !== 'any')
  const hasCustomTimeRange = timePreset === 'CUSTOM' || !!(timeFrom || timeTo)
  const chipClassName = 'inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800'
  const formatConstraintValue = (value?: string) => {
    if (!value) return null
    const normalised = value.trim()
    if (!normalised || normalised.toLowerCase() === 'any') return null
    return normalised.charAt(0).toUpperCase() + normalised.slice(1)
  }
  const constraintCost = formatConstraintValue(implementationConstraints?.cost)
  const constraintStaffing = formatConstraintValue(implementationConstraints?.staffing)
  const constraintComplexity = formatConstraintValue(implementationConstraints?.implementation_complexity)

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

  const refineSearch = () => {
    useWizard.getState().initFromSearchQuery(searchQuery as Record<string, unknown>, project.id)
    setIsOpen(false)
    router.push('/search')
  }

  const selectedBooleanQuery = booleanQueries[selectedQueryIndex] || ''

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="flex items-center gap-2">
          <Settings className="h-4 w-4" />
          View search settings
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

          <div className="grid gap-3">
            <div className="rounded-xl border border-gray-200 bg-gray-50/50 p-3">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Population</div>
              {population.length > 0 ? (
                <p className="text-sm text-gray-900">{population.join(', ')}</p>
              ) : (
                <p className="text-sm text-gray-500">Not specified</p>
              )}
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50/50 p-3">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Setting</div>
              {innerSetting.length > 0 ? (
                <p className="text-sm text-gray-900">{innerSetting.join(', ')}</p>
              ) : (
                <p className="text-sm text-gray-500">No preference</p>
              )}
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50/50 p-3">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Outcome</div>
              {outcome.length > 0 ? (
                <p className="text-sm text-gray-900">{outcome.join(', ')}</p>
              ) : (
                <p className="text-sm text-gray-500">Not specified</p>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-3 space-y-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Refinement</div>
            <div>
              <span className="font-medium text-sm">Implementation constraints</span>
              {hasImplementationConstraints ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {constraintCost && <span className={chipClassName}>Cost: {constraintCost}</span>}
                  {constraintStaffing && <span className={chipClassName}>Staffing: {constraintStaffing}</span>}
                  {constraintComplexity && <span className={chipClassName}>Complexity: {constraintComplexity}</span>}
                </div>
              ) : (
                <div className="mt-2 text-sm text-gray-500">Not specified</div>
              )}
            </div>
            <div>
              <span className="font-medium text-sm">Screening factors</span>
              {searchQuery.screening_factors && searchQuery.screening_factors.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {searchQuery.screening_factors.map((item, idx) => (
                    <span key={`${item}-${idx}`} className={chipClassName}>
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-sm text-gray-500">None added</div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-3 space-y-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Filters</div>
            <div>
              <span className="font-medium text-sm">Search sources</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {searchQuery.sources && searchQuery.sources.length > 0 ? (
                  searchQuery.sources.map((source: string) => (
                    <span key={source} className={chipClassName}>
                      {SOURCE_LABELS[source] || source}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-gray-500">Not specified</span>
                )}
              </div>
            </div>
            <div>
              <span className="font-medium text-sm">Retrieval limit</span>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={chipClassName}>{maxResults || 'Not specified'} per source</span>
                <span className="text-xs text-gray-500">
                  {searchQuery.sources?.length || 0} source{(searchQuery.sources?.length || 0) === 1 ? '' : 's'} selected
                </span>
              </div>
            </div>
            <div>
              <span className="font-medium text-sm">Time window</span>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className={chipClassName}>
                  {timePreset ? (TIME_PRESET_LABELS[timePreset] || timePreset.replaceAll('_', ' ')) : 'Not specified'}
                </span>
                {hasCustomTimeRange && (
                  <span className={chipClassName}>
                    {timeFrom || 'No start date'} to {timeTo || 'No end date'}
                  </span>
                )}
              </div>
            </div>
            <div>
              <span className="font-medium text-sm">Geography</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {geography.length > 0 ? (
                  geography.map((geo: string) => (
                    <span key={geo} className={chipClassName}>
                      {GEO_LABELS[geo] || geo}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-gray-500">Not specified</span>
                )}
              </div>
            </div>
          </div>

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

          {/* Advanced options */}
          {(searchQuery.scope?.length || searchQuery.custom_focus?.length || searchQuery.excludes?.length) ? (
            <div className="rounded-xl border border-gray-200 bg-white p-3 space-y-3">
              <div className="text-xs uppercase tracking-wide text-gray-500">Advanced options</div>
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
            </div>
          ) : null}

          {/* Refine & Re-search Button */}
          {(project.status === 'completed' || project.status === 'failed') && (
            <div className="pt-2 border-t">
              <Button onClick={refineSearch} className="w-full h-9" variant="default">
                <RefreshCw className="h-3.5 w-3.5 mr-2" />
                Refine &amp; re-search
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
