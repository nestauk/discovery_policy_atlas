'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
import { SearchForm } from '@/components/search/search-form'
import { SearchSummary } from '@/components/search/search-summary'
import { PapersList } from '@/components/search/papers-list'
import { ErrorMessage } from '@/components/search/error-message'
import { AiSummary } from '@/components/search/ai-summary'
import type { SearchParams, SearchResult } from '@/types/search'
import { useAPI } from '@/lib/api'

export default function SearchPage() {
  const searchParams = useSearchParams()
  const [results, setResults] = useState<SearchResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [screeningEnabled, setScreeningEnabled] = useState(true)
  const [currentQuery, setCurrentQuery] = useState('')
  const [currentFilters, setCurrentFilters] = useState<any>({})
  const { fetchWithAuth } = useAPI()
  const { user } = useUser()

  // Handle project selection from URL
  useEffect(() => {
    const projectId = searchParams.get('project')
    if (projectId) {
      handleProjectSelect(projectId)
    }
  }, [searchParams])

  const handleSearch = async (params: SearchParams) => {
    setIsLoading(true)
    setError('')
    setResults(null)
    setCurrentQuery(params.query)
    setCurrentFilters(params)

    try {
      const data = await fetchWithAuth('/api/search', {
        method: 'POST',
        body: JSON.stringify({ ...params, screening_enabled: screeningEnabled }),
      })
      setResults(data)
    } catch (err) {
      setError('Failed to search. Please try again.')
      console.error('Search error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleProjectSelect = async (projectId: string) => {
    try {
      const project = await fetchWithAuth(`/api/projects/${projectId}?clerk_user_id=${user?.id}`)
      console.log('Project loaded:', project)
      
      // Update current state
      setCurrentQuery(project.query)
      setCurrentFilters({
        source: project.filters.source || 'openalex',
        max_results: project.filters.max_results || 10,
        min_citations: project.filters.min_citations,
        date_from: project.filters.date_from,
        date_to: project.filters.date_to,
        inclusion_criteria: project.filters.inclusion_criteria,
        extraction_fields: project.filters.extraction_fields || [],
      })
      
      // Don't trigger search automatically
      // Let the user review and modify the parameters first
    } catch (error) {
      console.error('Error loading project:', error)
      setError('Failed to load project')
    }
  }

  return (
    <div className="page-container">
      <div>
        <h1 className="page-header">Search Papers</h1>
        <p className="page-description">
          Search and screen academic papers with AI
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