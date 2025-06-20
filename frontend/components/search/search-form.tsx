'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Loader2, ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import type { SearchParams } from '@/types/search'
import { useSearchStore } from '@/lib/searchStore'

interface SearchFormProps {
  onSearch: (params: SearchParams) => void
  isLoading: boolean
  screeningEnabled: boolean
  onScreeningEnabledChange: (enabled: boolean) => void
  initialQuery?: string
  initialFilters?: SearchParams
}

interface AdvancedOptionsProps {
  source: 'openalex' | 'mediacloud' | 'overton'
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
  // topics: string
  // setTopics: (value: string) => void
  // classifications: string
  // setClassifications: (value: string) => void
}

export function SearchForm({ 
  onSearch, 
  isLoading, 
  screeningEnabled, 
  onScreeningEnabledChange,
  initialQuery = '',
  initialFilters = {
    query: '',
    source: 'overton',
    max_results: 10
  }
}: SearchFormProps) {
  const [query, setQuery] = useState(initialQuery)
  const [source, setSource] = useState<'openalex' | 'mediacloud' | 'overton'>(initialFilters.source || 'overton')
  const [showAdvanced, setShowAdvanced] = useState(false)
  
  // Advanced options
  const [minCitations, setMinCitations] = useState(initialFilters.min_citations?.toString() || '')
  const [dateFrom, setDateFrom] = useState(initialFilters.date_from || '')
  const [dateTo, setDateTo] = useState(initialFilters.date_to || '')
  const [maxResults, setMaxResults] = useState(initialFilters.max_results?.toString() || '10')
  const [inclusionCriteria, setInclusionCriteria] = useState(initialFilters.inclusion_criteria || '')
  const [extractionFields, setExtractionFields] = useState<string[]>(initialFilters.extraction_fields || [])
  
  // Overton-specific fields
  const [sourceCountry, setSourceCountry] = useState(initialFilters.source_country || '')
  const [sourceType, setSourceType] = useState(initialFilters.source_type || '')
  const [semanticSearch, setSemanticSearch] = useState(initialFilters.semantic_search ?? false)
  // const [topics, setTopics] = useState(Array.isArray(initialFilters.topics) ? initialFilters.topics.join(', ') : initialFilters.topics || '')
  // const [classifications, setClassifications] = useState(initialFilters.classifications || '')

  // Zustand store
  const { reset: resetStore } = useSearchStore()

  // Store initial values for reset functionality
  const initialValues = {
    query: initialQuery,
    source: initialFilters.source || 'overton',
    minCitations: initialFilters.min_citations?.toString() || '',
    dateFrom: initialFilters.date_from || '',
    dateTo: initialFilters.date_to || '',
    maxResults: initialFilters.max_results?.toString() || '10',
    inclusionCriteria: initialFilters.inclusion_criteria || '',
    extractionFields: initialFilters.extraction_fields || [],
    sourceCountry: initialFilters.source_country || '',
    sourceType: initialFilters.source_type || '',
    semanticSearch: initialFilters.semantic_search ?? false,
    // topics: Array.isArray(initialFilters.topics) ? initialFilters.topics.join(', ') : initialFilters.topics || '',
    // classifications: initialFilters.classifications || '',
  }

  // Update form when initial values change
  useEffect(() => {
    console.log('Initial values changed:', { initialQuery, initialFilters })
    setQuery(initialQuery)
    setSource(initialFilters.source || 'overton')
    setMinCitations(initialFilters.min_citations?.toString() || '')
    setDateFrom(initialFilters.date_from || '')
    setDateTo(initialFilters.date_to || '')
    setMaxResults(initialFilters.max_results?.toString() || '10')
    setInclusionCriteria(initialFilters.inclusion_criteria || '')
    setExtractionFields(initialFilters.extraction_fields || [])
    setSourceCountry(initialFilters.source_country || '')
    setSourceType(initialFilters.source_type || '')
    setSemanticSearch(initialFilters.semantic_search ?? false)
    // setTopics(Array.isArray(initialFilters.topics) ? initialFilters.topics.join(', ') : initialFilters.topics || '')
    // setClassifications(initialFilters.classifications || '')
  }, [initialQuery, initialFilters])

  const handleReset = () => {
    // Reset local form state
    setQuery(initialValues.query)
    setSource(initialValues.source as 'openalex' | 'mediacloud' | 'overton')
    setMinCitations(initialValues.minCitations)
    setDateFrom(initialValues.dateFrom)
    setDateTo(initialValues.dateTo)
    setMaxResults(initialValues.maxResults)
    setInclusionCriteria(initialValues.inclusionCriteria)
    setExtractionFields([...initialValues.extractionFields])
    setSourceCountry(initialValues.sourceCountry)
    setSourceType(initialValues.sourceType)
    setSemanticSearch(false)
    // setTopics(initialValues.topics)
    // setClassifications(initialValues.classifications)
    setShowAdvanced(false)
    
    // Reset persisted Zustand store
    resetStore()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    const params: SearchParams = {
      query,
      source,
      max_results: parseInt(maxResults) || 10,
      inclusion_criteria: inclusionCriteria,
      extraction_fields: extractionFields.filter(f => f.trim() !== ''),
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
      // if (topics) {
      //   // Convert comma-separated string to array
      //   params.topics = topics.split(',').map(t => t.trim()).filter(t => t.length > 0)
      // }
      // if (classifications) params.classifications = classifications
    } else if (source === 'mediacloud') {
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
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
              <Label htmlFor="query">Search Query</Label>
              <Input
                id="query"
                placeholder="e.g., climate change policy"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="source">Data Source</Label>
              <div className="flex items-center gap-2">
                <Select value={source} onValueChange={(v: 'openalex' | 'mediacloud' | 'overton') => setSource(v)}>
                  <SelectTrigger id="source">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="overton">Overton (policy)</SelectItem>
                    <SelectItem value="openalex">OpenAlex (research)</SelectItem>
                    <SelectItem value="mediacloud">MediaCloud (news)</SelectItem>
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
                    <Label htmlFor="semanticSearch" className="ml-1 text-xs text-muted-foreground">
                      Semantic Search
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
                // topics={topics}
                // setTopics={setTopics}
                // classifications={classifications}
                // setClassifications={setClassifications}
              />
            </CollapsibleContent>
          </Collapsible>

          <Button type="submit" disabled={isLoading || !query.trim()} className="w-full">
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Searching and screening...
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
  // topics,
  // setTopics,
  // classifications,
  // setClassifications,
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
      {/* Screening Toggle */}
      <div className="flex items-center gap-2">
        <input
          id="screeningEnabled"
          type="checkbox"
          checked={screeningEnabled}
          onChange={e => onScreeningEnabledChange(e.target.checked)}
          className="h-4 w-4 accent-primary"
          title="Enable AI Screening"
        />
        <Label htmlFor="screeningEnabled" className="text-sm text-muted-foreground">
          Enable AI Screening
        </Label>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="maxResults">Max Results</Label>
          <Input
            id="maxResults"
            type="number"
            value={maxResults}
            onChange={(e) => setMaxResults(e.target.value)}
            min="1"
            max="100"
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

      {/* {source === 'overton' && (
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="topics">Topics</Label>
            <Input
              id="topics"
              placeholder="e.g., Climate Change, Energy, Health"
              value={topics}
              onChange={(e) => setTopics(e.target.value)}
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="classifications">Classifications</Label>
            <Input
              id="classifications"
              placeholder="e.g., environment, economy, politics"
              value={classifications}
              onChange={(e) => setClassifications(e.target.value)}
            />
          </div>
        </div>
      )} */}

      {/* Inclusion Criteria */}
      <div className="space-y-2">
        <Label htmlFor="inclusionCriteria">Inclusion Criteria</Label>
        <Input
          id="inclusionCriteria"
          placeholder="e.g., 'Human studies published after 2015 with at least 20 participants'"
          value={inclusionCriteria}
          onChange={(e) => setInclusionCriteria(e.target.value)}
        />
      </div>

      {/* Additional Extraction Fields */}
      <div className="space-y-2">
        <Label>Additional Extraction Fields</Label>
        {extractionFields.map((field: string, idx: number) => (
          <div key={idx} className="flex items-center gap-2 mb-2">
            <Input
              placeholder="e.g., 'Sample size', 'Effect size', 'Methodology'"
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
    </div>
  )
}