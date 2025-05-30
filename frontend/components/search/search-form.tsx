'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import type { SearchParams } from '@/types/search'

interface SearchFormProps {
  onSearch: (params: SearchParams) => void
  isLoading: boolean
  screeningEnabled: boolean
  onScreeningEnabledChange: (enabled: boolean) => void
}

export function SearchForm({ onSearch, isLoading, screeningEnabled, onScreeningEnabledChange }: SearchFormProps) {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<'openalex' | 'mediacloud'>('openalex')
  const [showAdvanced, setShowAdvanced] = useState(false)
  
  // Advanced options
  const [minCitations, setMinCitations] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [maxResults, setMaxResults] = useState('10')
  const [inclusionCriteria, setInclusionCriteria] = useState('')
  const [extractionFields, setExtractionFields] = useState<string[]>([])

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
              <Select value={source} onValueChange={(v: any) => setSource(v)}>
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
              />
            </CollapsibleContent>
          </Collapsible>

          {/* Inclusion Criteria with inline screening checkbox */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 mb-1">
              <Label htmlFor="inclusionCriteria" className="mb-0">
                Inclusion Criteria
              </Label>
              <input
                id="screeningEnabled"
                type="checkbox"
                checked={screeningEnabled}
                onChange={e => onScreeningEnabledChange(e.target.checked)}
                className="h-4 w-4 accent-primary"
                style={{ marginLeft: 8 }}
                title="Enable AI Screening"
              />
              <span className="text-xs text-muted-foreground">Enable AI Screening</span>
            </div>
            <Input
              id="inclusionCriteria"
              placeholder="e.g., 'Human studies published after 2015 with at least 20 participants'"
              value={inclusionCriteria}
              onChange={(e) => setInclusionCriteria(e.target.value)}
            />
          </div>

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

// Separate component for advanced options
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
}: any) {
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