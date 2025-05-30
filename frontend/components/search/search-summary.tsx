import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SearchResult } from '@/types/search'

interface SearchSummaryProps {
  results: SearchResult
}

export function SearchSummary({ results }: SearchSummaryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Search Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="summary-grid">
          <div>
            <p className="summary-value">{results.total_found}</p>
            <p className="summary-label">Papers Found</p>
          </div>
          <div>
            <p className="summary-value">{results.total_screened}</p>
            <p className="summary-label">Screened by AI</p>
          </div>
          <div>
            <p className="summary-value-highlight">{results.total_relevant}</p>
            <p className="summary-label">Relevant Papers</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}