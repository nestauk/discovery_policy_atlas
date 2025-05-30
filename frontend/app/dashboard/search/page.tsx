'use client'

import { useState } from 'react'
import { SearchForm } from '@/components/search/search-form'
import { SearchSummary } from '@/components/search/search-summary'
import { PapersList } from '@/components/search/papers-list'
import { ErrorMessage } from '@/components/search/error-message'
import { AiSummary } from '@/components/search/ai-summary'
import type { SearchParams, SearchResult } from '@/types/search'

export default function SearchPage() {
  const [results, setResults] = useState<SearchResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [screeningEnabled, setScreeningEnabled] = useState(true)

  const handleSearch = async (params: SearchParams) => {
    setIsLoading(true)
    setError('')
    setResults(null)

    try {
      const response = await fetch('http://localhost:8000/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, screening_enabled: screeningEnabled }),
      })

      if (!response.ok) throw new Error('Search failed')

      const data: SearchResult = await response.json()
      setResults(data)
    } catch (err) {
      setError('Failed to search. Please try again.')
      console.error('Search error:', err)
    } finally {
      setIsLoading(false)
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