'use client'

import { Card } from '@/components/ui/card'

interface Paper {
  id: string
  title: string
  abstract?: string
  content?: string
  extra_fields?: Record<string, string>
}

interface SearchResultsProps {
  papers?: Paper[]
  isLoading?: boolean
}

export function SearchResults({ papers = [], isLoading = false }: SearchResultsProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <Card key={i} className="p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
            <div className="h-4 bg-gray-200 rounded w-1/2" />
          </Card>
        ))}
      </div>
    )
  }

  if (!papers.length) {
    return null
  }

  return (
    <div className="space-y-4">
      {papers.map((paper) => (
        <Card key={paper.id} className="p-4">
          <h3 className="text-lg font-semibold mb-2">{paper.title}</h3>
          {paper.abstract && (
            <p className="text-gray-600 mb-2">{paper.abstract}</p>
          )}
          {paper.extra_fields && Object.entries(paper.extra_fields).length > 0 && (
            <div className="mt-2 space-y-1">
              {Object.entries(paper.extra_fields).map(([key, value]) => (
                <div key={key} className="text-sm">
                  <span className="font-medium">{key}:</span> {value}
                </div>
              ))}
            </div>
          )}
        </Card>
      ))}
    </div>
  )
} 