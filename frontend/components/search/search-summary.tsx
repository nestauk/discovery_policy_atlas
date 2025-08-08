import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SearchResult } from '@/types/search'

interface SearchSummaryProps {
  results: SearchResult
}

export function SearchSummary({ results }: SearchSummaryProps) {
  // Debug logging to see the full structure
  console.log('SearchSummary full results:', results)
  
  // The papers array contains only screened papers, so we need the backend totals
  const totalFound = results?.total_found ?? 0
  const totalRelevant = results?.total_relevant ?? results?.papers?.length ?? 0
  
  // If we don't have backend totals, show what we can calculate
  const hasBackendTotals = results?.total_found !== undefined
  
  console.log('SearchSummary calculated:', { 
    totalFound, 
    totalRelevant, 
    papersLength: results?.papers?.length,
    hasBackendTotals 
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Search Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="summary-grid">
          <div>
            <p className="summary-value">{totalFound}</p>
            <p className="summary-label">
              {hasBackendTotals ? 'Papers Retrieved' : 'Papers Found'}
            </p>
          </div>
          <div>
            <p className="summary-value-highlight">{totalRelevant}</p>
            <p className="summary-label">Relevant Papers</p>
          </div>
        </div>
        {!hasBackendTotals && (
          <p className="text-xs text-gray-500 mt-2">
            Note: Showing screened papers only. Backend totals not available.
          </p>
        )}
      </CardContent>
    </Card>
  )
}