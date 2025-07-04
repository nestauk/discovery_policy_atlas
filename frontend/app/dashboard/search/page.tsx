'use client'

import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
import { SearchForm } from '@/components/search/search-form'
import { SearchSummary } from '@/components/search/search-summary'
import { PapersList } from '@/components/search/papers-list'
import { ErrorMessage } from '@/components/search/error-message'
import { AiSummary } from '@/components/search/ai-summary'
import { DownloadButton } from '@/components/search/download-button'
import type { SearchParams, SearchResult } from '@/types/search'
import { useAPI } from '@/lib/api'
import { useSearchStore } from '@/lib/searchStore'
import { SEARCH_DEFAULTS } from '@/lib/constants'

export default function SearchPage() {
  const searchParams = useSearchParams()
  const [results, setResults] = useState<SearchResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [screeningEnabled, setScreeningEnabled] = useState(true)
  const { fetchWithAuth } = useAPI()
  const { user } = useUser()

  // Zustand store
  const { searchParams: persistedParams, setSearchParams } = useSearchStore()

  // Local state for form
  const [currentQuery, setCurrentQuery] = useState(persistedParams.query)
  const [currentFilters, setCurrentFilters] = useState<SearchParams>(persistedParams)

  // Sync local state with zustand on mount (or when persistedParams changes)
  useEffect(() => {
    setCurrentQuery(persistedParams.query)
    setCurrentFilters(persistedParams)
  }, [persistedParams])

  const handleProjectSelect = useCallback(async (projectId: string) => {
    try {
      const project = await fetchWithAuth(`/api/projects/${projectId}?clerk_user_id=${user?.id}`)
      setCurrentQuery(project.query)
      setCurrentFilters({
        query: project.query,
        source: project.filters.source || 'openalex',
        max_results: project.filters.max_results || SEARCH_DEFAULTS.MAX_RESULTS,
        min_citations: project.filters.min_citations,
        date_from: project.filters.date_from,
        date_to: project.filters.date_to,
        inclusion_criteria: project.filters.inclusion_criteria,
        extraction_fields: project.filters.extraction_fields || []
      })
    } catch (error) {
      console.error('Failed to load project:', error)
      const errorMessage = error instanceof Error 
        ? `Failed to load project: ${error.message}`
        : 'Failed to load project: Unknown error'
      setError(errorMessage)
    }
  }, [fetchWithAuth, user?.id])

  useEffect(() => {
    const projectId = searchParams.get('project')
    if (projectId) {
      handleProjectSelect(projectId)
    }
  }, [searchParams, handleProjectSelect])

  const handleSearch = async (params: SearchParams) => {
    setIsLoading(true)
    setError('')
    setResults(null)
    setCurrentQuery(params.query)
    setCurrentFilters(params)
    setSearchParams(params) // Persist to zustand
    try {
      const data = await fetchWithAuth('/api/search', {
        method: 'POST',
        body: JSON.stringify({ ...params, screening_enabled: screeningEnabled }),
      })
      setResults(data)
    } catch (error) {
      console.error('Search failed:', error)
      const errorMessage = error instanceof Error 
        ? `Search failed: ${error.message}`
        : 'Search failed: Unknown error'
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="page-container">
      <div>
        <h1 className="page-header">Search</h1>
        <p className="page-description">
          Search and screen policy and academic research data with AI
        </p>
      </div>
      <SearchForm 
        onSearch={handleSearch} 
        isLoading={isLoading} 
        screeningEnabled={screeningEnabled}
        onScreeningEnabledChange={setScreeningEnabled}
        initialQuery={currentQuery}
        initialFilters={currentFilters}
      />
      {error && <ErrorMessage message={error} />}
      {results && (
        <>
          <SearchSummary results={results} />
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">Results</h2>
            <DownloadButton 
              downloadKey={results.download_key} 
              className="ml-4"
            />
          </div>
          <PapersList papers={results.papers} />
          <AiSummary 
            papers={results.papers} 
            extractionFields={Object.keys(results.papers?.[0] || {}).filter(k => k.startsWith('extra_field_'))} 
          />
        </>
      )}
    </div>
  )
}