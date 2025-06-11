'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import { ProjectSelector } from '@/components/ProjectSelector'
import type { SearchParams } from '@/types/search'

interface SearchFormProps {
  onSearch: (params: SearchParams) => void
  isLoading: boolean
  screeningEnabled: boolean
  onScreeningEnabledChange: (enabled: boolean) => void
  initialQuery?: string
  initialFilters?: SearchParams
}

interface AdvancedOptionsProps {
  source: 'openalex' | 'mediacloud'
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
}

export function SearchForm({ 
  onSearch, 
  isLoading, 
  screeningEnabled, 
  onScreeningEnabledChange,
  initialQuery = '',
  initialFilters = {
    query: '',
    source: 'openalex',
    max_results: 10
  }
}: SearchFormProps) {
  const [query, setQuery] = useState(initialQuery)
  const [source, setSource] = useState<'openalex' | 'mediacloud'>(initialFilters.source || 'openalex')
  const [showAdvanced, setShowAdvanced] = useState(false)
  
  // Advanced options
  const [minCitations, setMinCitations] = useState(initialFilters.min_citations?.toString() || '')
  const [dateFrom, setDateFrom] = useState(initialFilters.date_from || '')
  const [dateTo, setDateTo] = useState(initialFilters.date_to || '')
  const [maxResults, setMaxResults] = useState(initialFilters.max_results?.toString() || '10')
  const [inclusionCriteria, setInclusionCriteria] = useState(initialFilters.inclusion_criteria || '')
  const [extractionFields, setExtractionFields] = useState<string[]>(initialFilters.extraction_fields || [])

  // Update form when initial values change
  useEffect(() => {
    console.log('Initial values changed:', { initialQuery, initialFilters })
    setQuery(initialQuery)
    setSource(initialFilters.source || 'openalex')
    setMinCitations(initialFilters.min_citations?.toString() || '')
    setDateFrom(initialFilters.date_from || '')
    setDateTo(initialFilters.date_to || '')
    setMaxResults(initialFilters.max_results?.toString() || '10')
    setInclusionCriteria(initialFilters.inclusion_criteria || '')
    setExtractionFields(initialFilters.extraction_fields || [])
  }, [initialQuery, initialFilters])

  const handleProjectSelect = (query: string, filters: SearchParams, projectId: string) => {
    console.log('Project selected in form:', { query, filters, projectId })
    // The parent component will handle this through the URL change
    // and pass down new initialQuery and initialFilters
    window.history.pushState({}, '', `/dashboard/search?project=${projectId}`)
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
    }

    onSearch(params)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Search Parameters</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <ProjectSelector
            currentQuery={query}
            currentFilters={{
              query,
              source,
              max_results: parseInt(maxResults) || 10,
              min_citations: minCitations ? parseInt(minCitations) : undefined,
              date_from: dateFrom,
              date_to: dateTo,
              inclusion_criteria: inclusionCriteria,
              extraction_fields: extractionFields,
            }}
            onProjectSelect={handleProjectSelect}
          />

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
              <Select value={source} onValueChange={(v: 'openalex' | 'mediacloud') => setSource(v)}>
                <SelectTrigger id="source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openalex">Research</SelectItem>
                  <SelectItem value="mediacloud">News</SelectItem>
                </SelectContent>
              </Select>
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