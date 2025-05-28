'use client'

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Loader2, ExternalLink } from 'lucide-react'

interface Paper {
  id: string
  title: string
  publication_year: number
  cited_by_count: number
  doi: string
  abstract?: string
  authors: Array<{
    author_position: string
    author: {
      display_name: string
    }
  }>
  primary_location?: {
    source?: {
      display_name: string
    }
  }
}

export default function SearchPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [results, setResults] = useState<Paper[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!searchTerm.trim()) return
  
    setIsLoading(true)
    setError('')
    setResults([])
  
    try {
      const response = await fetch('http://localhost:8000/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: searchTerm, per_page: 3 }),
      })
  
      if (!response.ok) {
        throw new Error('Search failed')
      }
  
      const data = await response.json()
      setResults(data.results || [])
    } catch (err) {
      setError('Failed to search. Please try again.')
      console.error('Search error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Search Papers</h1>
        <p className="text-muted-foreground mt-2">
          Search for academic papers using OpenAlex
        </p>
      </div>

      {/* Search Form */}
      <Card>
        <CardHeader>
          <CardTitle>Enter Search Terms</CardTitle>
          <CardDescription>
            Search for papers by title, abstract, or keywords
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="flex gap-4">
            <Input
              placeholder="e.g., climate change policy"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              disabled={isLoading}
              className="flex-1"
            />
            <Button type="submit" disabled={isLoading || !searchTerm.trim()}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Searching...
                </>
              ) : (
                'Search'
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Error Message */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Results</h2>
          {results.map((paper) => (
            <Card key={paper.id}>
              <CardHeader>
                <div className="space-y-2">
                  <CardTitle className="text-lg leading-tight">
                    {paper.title}
                  </CardTitle>
                  <CardDescription>
                    <div className="flex flex-wrap gap-2 text-sm">
                      <span>{paper.publication_year}</span>
                      <span>•</span>
                      <span>{paper.cited_by_count} citations</span>
                      {paper.primary_location?.source?.display_name && (
                        <>
                          <span>•</span>
                          <span>{paper.primary_location.source.display_name}</span>
                        </>
                      )}
                    </div>
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Authors */}
                <div className="flex flex-wrap gap-1">
                {paper.authors && paper.authors.length > 0 ? (
                    <>
                    {paper.authors.slice(0, 3).map((author, idx) => (
                        <Badge key={idx} variant="secondary">
                        {author.author?.display_name || 'Unknown Author'}
                        </Badge>
                    ))}
                    {paper.authors.length > 3 && (
                        <Badge variant="outline">+{paper.authors.length - 3} more</Badge>
                    )}
                    </>
                ) : (
                    <Badge variant="outline">No authors listed</Badge>
                )}
                </div>

                {/* Abstract */}
                {paper.abstract && (
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {paper.abstract}
                  </p>
                )}

                {/* DOI Link */}
                {paper.doi && (
                  <div className="pt-2">
                    <a
                      href={paper.doi}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-primary hover:underline inline-flex items-center gap-1"
                    >
                      View Paper
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}