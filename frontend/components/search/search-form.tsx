'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Loader2, ChevronDown, ChevronUp, RotateCcw, Info } from 'lucide-react'
import type { SearchParams } from '@/types/search'
import { useSearchStore } from '@/lib/searchStore'
import { SEARCH_DEFAULTS } from '@/lib/constants'
import { Switch } from '@/components/ui/switch'
import { Tooltip } from '@/components/ui/tooltip'

interface SearchFormProps {
  onSearch: (params: SearchParams) => void
  isLoading: boolean
  initialQuery?: string
  initialFilters?: SearchParams
  screeningEnabled: boolean
  onScreeningEnabledChange: (enabled: boolean) => void
}

interface AdvancedOptionsProps {
  source: 'openalex' | 'overton'
  maxResults: string
  setMaxResults: (value: string) => void
  minCitations: string
  setMinCitations: (value: string) => void
  dateFrom: string
  setDateFrom: (value: string) => void
  dateTo: string
  setDateTo: (value: string) => void
  inclusionCriteria: string
  setInclusionCriteria: (value: string) => void
  extractionFields: string[]
  setExtractionFields: (value: string[]) => void
  screeningEnabled: boolean
  onScreeningEnabledChange: (enabled: boolean) => void
  // Overton-specific fields
  sourceCountry: string
  setSourceCountry: (value: string) => void
  sourceType: string
  setSourceType: (value: string) => void
}

export function SearchForm({ 
  onSearch, 
  isLoading, 
  initialQuery = '',
  initialFilters = {
    query: '',
    source: SEARCH_DEFAULTS.SOURCE,
    max_results: SEARCH_DEFAULTS.MAX_RESULTS
  },
  screeningEnabled,
  onScreeningEnabledChange
}: SearchFormProps) {
  const [query, setQuery] = useState(initialQuery)
  const [source, setSource] = useState<'openalex' | 'overton'>(initialFilters.source || 'overton')
  const [showAdvanced, setShowAdvanced] = useState(false)
  
  // Advanced options
  const [minCitations, setMinCitations] = useState(initialFilters.min_citations?.toString() || '')
  const [dateFrom, setDateFrom] = useState(initialFilters.date_from || SEARCH_DEFAULTS.DATE_FROM)
  const [dateTo, setDateTo] = useState(initialFilters.date_to || SEARCH_DEFAULTS.DATE_TO)
  const [maxResults, setMaxResults] = useState(initialFilters.max_results?.toString() || SEARCH_DEFAULTS.MAX_RESULTS.toString())
  const [inclusionCriteria, setInclusionCriteria] = useState(initialFilters.inclusion_criteria || '')
  const [extractionFields, setExtractionFields] = useState<string[]>(initialFilters.extraction_fields || [])
  
  // Overton-specific fields
  const [sourceCountry, setSourceCountry] = useState(initialFilters.source_country || '')
  const [sourceType, setSourceType] = useState(initialFilters.source_type || '')
  const [semanticSearch, setSemanticSearch] = useState(
    initialFilters.semantic_search ?? (initialFilters.source === 'overton' ? true : false)
  )

  // Zustand store
  const { reset: resetStore } = useSearchStore()

  // Store initial values for reset functionality
  const initialValues = {
    query: initialQuery,
    source: initialFilters.source || 'overton',
    minCitations: initialFilters.min_citations?.toString() || '',
    dateFrom: initialFilters.date_from || SEARCH_DEFAULTS.DATE_FROM,
    dateTo: initialFilters.date_to || SEARCH_DEFAULTS.DATE_TO,
    maxResults: initialFilters.max_results?.toString() || SEARCH_DEFAULTS.MAX_RESULTS.toString(),
    inclusionCriteria: initialFilters.inclusion_criteria || '',
    extractionFields: initialFilters.extraction_fields || [],
    sourceCountry: initialFilters.source_country || '',
    sourceType: initialFilters.source_type || '',
    semanticSearch: initialFilters.semantic_search ?? false,
  }

  // Update form when initial values change
  useEffect(() => {
    console.log('Initial values changed:', { initialQuery, initialFilters })
    setQuery(initialQuery)
    setSource(initialFilters.source || 'overton')
    setMinCitations(initialFilters.min_citations?.toString() || '')
    setDateFrom(initialFilters.date_from || SEARCH_DEFAULTS.DATE_FROM)
    setDateTo(initialFilters.date_to || SEARCH_DEFAULTS.DATE_TO)
    setMaxResults(initialFilters.max_results?.toString() || SEARCH_DEFAULTS.MAX_RESULTS.toString())
    setInclusionCriteria(initialFilters.inclusion_criteria || '')
    setExtractionFields(initialFilters.extraction_fields || [])
    setSourceCountry(initialFilters.source_country || '')
    setSourceType(initialFilters.source_type || '')
    setSemanticSearch(
      initialFilters.semantic_search ?? (initialFilters.source === 'overton' ? true : false)
    )
  }, [initialQuery, initialFilters, initialFilters.semantic_search])

  // When the source changes, enable semantic search by default for Overton
  useEffect(() => {
    if (source === 'overton' && semanticSearch === false && initialFilters.semantic_search === undefined) {
      setSemanticSearch(true)
    }
    if (source === 'openalex' && semanticSearch === true && initialFilters.semantic_search === undefined) {
      setSemanticSearch(false)
    }
  }, [source, semanticSearch, initialFilters.semantic_search])

  const handleReset = () => {
    // Reset local form state
    setQuery(initialValues.query)
    setSource(initialValues.source as 'openalex' | 'overton')
    setMinCitations(initialValues.minCitations)
    setDateFrom(initialValues.dateFrom || SEARCH_DEFAULTS.DATE_FROM)
    setDateTo(initialValues.dateTo || SEARCH_DEFAULTS.DATE_TO)
    setMaxResults(initialValues.maxResults)
    setInclusionCriteria(initialValues.inclusionCriteria)
    setExtractionFields([...initialValues.extractionFields])
    setSourceCountry(initialValues.sourceCountry)
    setSourceType(initialValues.sourceType)
    setSemanticSearch(
      initialValues.semanticSearch !== undefined
        ? initialValues.semanticSearch
        : (initialValues.source === 'overton' ? true : false)
    )
    setShowAdvanced(false)
    // Enable AI screening after reset
    onScreeningEnabledChange(true)
    // Reset persisted Zustand store
    resetStore()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    const params: SearchParams & { screening_enabled: boolean } = {
      query,
      source,
      max_results: parseInt(maxResults) || SEARCH_DEFAULTS.MAX_RESULTS,
      inclusion_criteria: inclusionCriteria,
      extraction_fields: extractionFields.filter(f => f.trim() !== ''),
      screening_enabled: screeningEnabled,
    }

    if (source === 'openalex') {
      if (minCitations) params.min_citations = parseInt(minCitations)
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
    } else if (source === 'overton') {
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      if (sourceCountry) params.source_country = sourceCountry
      if (sourceType) params.source_type = sourceType
      params.semantic_search = semanticSearch
    }

    onSearch(params)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Search Parameters</CardTitle>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={isLoading}
            className="flex items-center gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="query" className="flex items-center gap-1">
                Search Query
                <Tooltip content={
                  source === 'overton'
                    ? 'Enter boolean search query with keywords - or free text queries if Semantic Search is enabled - to search for relevant policy documents in Overton.'
                    : 'Enter boolean search query with keywords to search for academic research papers in OpenAlex.'
                }>
                  <span tabIndex={0} className="focus:outline-none cursor-pointer">
                    <Info className="w-3.5 h-3.5 text-muted-foreground" aria-label="Info about search query" />
                  </span>
                </Tooltip>
              </Label>
              <Input
                id="query"
                placeholder="e.g., parenting interventions"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="source">Data Source</Label>
              <div className="flex items-center gap-2">
                <Select value={source} onValueChange={(v: 'openalex' | 'overton') => setSource(v)}>
                  <SelectTrigger id="source">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="overton">Overton (policy)</SelectItem>
                    <SelectItem value="openalex">OpenAlex (research)</SelectItem>
                  </SelectContent>
                </Select>
                {source === 'overton' && (
                  <div className="flex items-center ml-2">
                    <input
                      id="semanticSearch"
                      type="checkbox"
                      checked={semanticSearch}
                      onChange={e => setSemanticSearch(e.target.checked)}
                      className="h-4 w-4 accent-primary"
                    />
                    <Label htmlFor="semanticSearch" className="ml-1 text-xs text-muted-foreground flex items-center gap-1">
                      Semantic Search
                      <Tooltip content="Semantic search uses AI to find relevant documents based on meaning, not just keywords. This may improve results for complex queries.">
                        <span tabIndex={0} className="focus:outline-none cursor-pointer">
                          <Info className="w-3.5 h-3.5 text-muted-foreground" aria-label="Info about semantic search" />
                        </span>
                      </Tooltip>
                    </Label>
                  </div>
                )}
              </div>
            </div>
          </div>

          <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
            <CollapsibleTrigger asChild>
              <Button variant="outline" type="button" className="w-full">
                Advanced Options
                {showAdvanced ? 
                  <ChevronUp className="ml-2 h-4 w-4" /> : 
                  <ChevronDown className="ml-2 h-4 w-4" />
                }
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <AdvancedOptions
                source={source}
                maxResults={maxResults}
                setMaxResults={setMaxResults}
                minCitations={minCitations}
                setMinCitations={setMinCitations}
                dateFrom={dateFrom}
                setDateFrom={setDateFrom}
                dateTo={dateTo}
                setDateTo={setDateTo}
                inclusionCriteria={inclusionCriteria}
                setInclusionCriteria={setInclusionCriteria}
                extractionFields={extractionFields}
                setExtractionFields={setExtractionFields}
                screeningEnabled={screeningEnabled}
                onScreeningEnabledChange={onScreeningEnabledChange}
                sourceCountry={sourceCountry}
                setSourceCountry={setSourceCountry}
                sourceType={sourceType}
                setSourceType={setSourceType}
              />
            </CollapsibleContent>
          </Collapsible>

          <Button type="submit" disabled={isLoading || !query.trim()} className="w-full">
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {screeningEnabled ? 'Searching and screening...' : 'Searching...'}
              </>
            ) : (
              'Search'
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function AdvancedOptions({
  source,
  maxResults,
  setMaxResults,
  minCitations,
  setMinCitations,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  inclusionCriteria,
  setInclusionCriteria,
  extractionFields,
  setExtractionFields,
  screeningEnabled,
  onScreeningEnabledChange,
  sourceCountry,
  setSourceCountry,
  sourceType,
  setSourceType,
}: AdvancedOptionsProps) {
  const handleFieldChange = (idx: number, value: string) => {
    const updated = [...extractionFields]
    updated[idx] = value
    setExtractionFields(updated)
  }
  const handleAddField = () => setExtractionFields([...extractionFields, ''])
  const handleRemoveField = (idx: number) => setExtractionFields(extractionFields.filter((_: string, i: number) => i !== idx))

  return (
    <div className="space-y-4 mt-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="maxResults" className="flex items-center gap-1">
            Max Results
            <Tooltip content="We recommend starting with smaller values (<50), refining your search, and then increasing the number of results. Higher values will take longer to load.">
              <span tabIndex={0} className="focus:outline-none cursor-pointer">
                <Info className="w-3.5 h-3.5 text-muted-foreground" aria-label="Info about max results" />
              </span>
            </Tooltip>
          </Label>
          <Input
            id="maxResults"
            type="number"
            value={maxResults}
            onChange={(e) => setMaxResults(e.target.value)}
            min="1"
            max={SEARCH_DEFAULTS.MAX_RESULTS_LIMIT.toString()}
          />
        </div>
        
        {source === 'openalex' && (
          <div className="space-y-2">
            <Label htmlFor="minCitations">Min Citations</Label>
            <Input
              id="minCitations"
              type="number"
              value={minCitations}
              onChange={(e) => setMinCitations(e.target.value)}
              min="0"
              placeholder="0"
            />
          </div>
        )}
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="dateFrom">Date From</Label>
          <Input
            id="dateFrom"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="dateTo">Date To</Label>
          <Input
            id="dateTo"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
      </div>

      {/* Overton-specific fields */}
      {source === 'overton' && (
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="sourceCountry">Source Country</Label>
            <Input
              id="sourceCountry"
              placeholder="e.g., USA, UK, France"
              value={sourceCountry}
              onChange={(e) => setSourceCountry(e.target.value)}
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="sourceType">Source Type</Label>
            <Select value={sourceType} onValueChange={setSourceType}>
              <SelectTrigger id="sourceType">
                <SelectValue placeholder="Select source type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="government">Government</SelectItem>
                <SelectItem value="think tank">Think Tank</SelectItem>
                <SelectItem value="ngo">NGO</SelectItem>
                <SelectItem value="academic">Academic</SelectItem>
                <SelectItem value="international">International</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
      
      {/* Move AI Screening toggle here, use Switch */}
      <div className="flex items-center gap-2 mt-2">
        <Switch
          id="screeningEnabled"
          checked={screeningEnabled}
          onCheckedChange={onScreeningEnabledChange}
        />
        <Label htmlFor="screeningEnabled" className="text-sm text-muted-foreground">
          Enable AI Screening
        </Label>
      </div>

      {/* Only show these if screeningEnabled is true */}
      {screeningEnabled && (
        <>
          <div className="space-y-2">
            <Label htmlFor="inclusionCriteria" className="flex items-center gap-1">
              Inclusion Criteria
              <Tooltip content="Specific criteria for screening paper summaries: e.g., particular research focus or study type.">
                <span tabIndex={0} className="focus:outline-none cursor-pointer">
                  <Info className="w-3.5 h-3.5 text-muted-foreground" aria-label="Info about inclusion criteria" />
                </span>
              </Tooltip>
            </Label>
            <Input
              id="inclusionCriteria"
              placeholder="e.g., Interventions regarding parents of young children (0-5 years of age)"
              value={inclusionCriteria}
              onChange={(e) => setInclusionCriteria(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label className="flex items-center gap-1">
              Extraction Fields
              <Tooltip content="List extra fields you want the AI to extract from each paper: e.g., Sample size, Effect size.">
                <span tabIndex={0} className="focus:outline-none cursor-pointer">
                  <Info className="w-3.5 h-3.5 text-muted-foreground" aria-label="Info about extraction fields" />
                </span>
              </Tooltip>
            </Label>
            {extractionFields.map((field: string, idx: number) => (
              <div key={idx} className="flex items-center gap-2 mb-2">
                <Input
                  placeholder="e.g., Country or countries that is the focus of the document (n/a if not reported)"
                  value={field}
                  onChange={(e) => handleFieldChange(idx, e.target.value)}
                />
                <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveField(idx)} aria-label="Remove field">
                  <span className="text-destructive text-lg">&minus;</span>
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" onClick={handleAddField}>
              + Add Extraction Field
            </Button>
          </div>
        </>
      )}

    </div>
  )
}