import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ExternalLink } from 'lucide-react'
import type { Paper } from '@/types/search'

interface PaperCardProps {
  paper: Paper
}

export function PaperCard({ paper }: PaperCardProps) { 
  return (
    <Card className={paper.is_relevant ? 'paper-card-relevant' : 'paper-card'}>
      <CardHeader>
        <div className="space-y-2">
          <div className="flex items-start justify-between">
            <CardTitle className="paper-title">
              {paper.title}
            </CardTitle>
            {paper.is_relevant && (
              <Badge className="ml-2 badge-relevant">
                Relevant
              </Badge>
            )}
          </div>
          <PaperMetadata paper={paper} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <AuthorsList authors={paper.authors} />
        <RelevanceInfo paper={paper} />
        {paper.abstract && (
          <p className="paper-abstract">{paper.abstract}</p>
        )}
        {/* Show extracted extra fields if present */}
        {Object.entries(paper)
          .filter(([key, value]) => key.startsWith('extra_field_') && value && value !== '')
          .map(([key, value]) => (
            <div key={key} className="extracted-field-box">
              <span className="font-medium">{key.replace('extra_field_', 'Extracted Field ')}:</span> {value}
            </div>
        ))}
        {paper.doi && <PaperLink doi={paper.doi} />}
      </CardContent>
    </Card>
  )
}

function PaperMetadata({ paper }: { paper: Paper }) {
  return (
    <div className="paper-metadata">
      <span>{paper.publication_year}</span>
      <span>•</span>
      <span>{paper.cited_by_count} citations</span>
      {paper.venue && (
        <>
          <span>•</span>
          <span>{paper.venue}</span>
        </>
      )}
    </div>
  )
}

function AuthorsList({ authors }: { authors: string[] }) {
  if (!authors?.length) return null

  return (
    <div className="flex flex-wrap gap-1">
      {authors.slice(0, 3).map((author, idx) => (
        <Badge key={idx} variant="secondary">
          {author}
        </Badge>
      ))}
      {authors.length > 3 && (
        <Badge variant="outline">+{authors.length - 3} more</Badge>
      )}
    </div>
  )
}

function RelevanceInfo({ paper }: { paper: Paper }) {
  if (!paper.relevance_reason) return null

  return (
    <div className="ai-screening-box">
      <p className="font-medium">AI Screening:</p>
      <p>{paper.relevance_reason}</p>
      {paper.confidence && (
        <p className="text-xs mt-1">
          Confidence: {(paper.confidence * 100).toFixed(0)}%
        </p>
      )}
    </div>
  )
}

function PaperLink({ doi }: { doi: string }) {
  return (
    <div className="pt-2">
      <a
        href={doi}
        target="_blank"
        rel="noopener noreferrer"
        className="paper-link"
      >
        View Paper
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  )
}