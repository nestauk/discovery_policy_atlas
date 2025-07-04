import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ExternalLink } from 'lucide-react'
import type { Paper } from '@/types/search'

interface PaperCardProps {
  paper: Paper
}

export function PaperCard({ paper }: PaperCardProps) { 
  // Helper to get the correct link for the title
  const getTitleLink = () => {
    if (paper.doi) {
      // If DOI is already a URL, use it; otherwise, construct the URL
      return paper.doi.startsWith('http') ? paper.doi : `https://doi.org/${paper.doi}`
    }
    return paper.overton_url
  }

  return (
    <Card className={paper.is_relevant ? 'paper-card-relevant' : 'paper-card'}>
      <CardHeader>
        <div className="space-y-2">
          <div className="flex items-start justify-between">
            <CardTitle className="paper-title">
              {getTitleLink() ? (
                <a 
                  href={getTitleLink()} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="paper-title-link"
                >
                  {paper.title}
                </a>
              ) : (
                paper.title
              )}
            </CardTitle>
            {/* Removed Relevant badge */}
          </div>
          {/* <PaperMetadata paper={paper} /> */}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <AuthorsList authors={paper.authors} />
        {paper.abstract && (
          <p className="paper-abstract">{paper.abstract}</p>
        )}
        
        {/* Overton-specific metadata */}
        {(paper.source_country || paper.source_type || paper.topics) && (
          <div className="flex flex-wrap gap-2">
            {paper.source_country && (
              <Badge variant="outline" className="text-xs">
                {paper.source_country}
              </Badge>
            )}
            {paper.source_type && (
              <Badge variant="outline" className="text-xs">
                {paper.source_type}
              </Badge>
            )}
            {paper.topics && paper.topics.slice(0, 3).map((topic, idx) => (
              <Badge key={idx} variant="secondary" className="text-xs">
                {topic}
              </Badge>
            ))}
            {paper.topics && paper.topics.length > 3 && (
              <Badge variant="outline" className="text-xs">
                +{paper.topics.length - 3} more topics
              </Badge>
            )}
          </div>
        )}
        
        <RelevanceInfo paper={paper} />
        {/* Show extracted extra fields if present */}
        {Object.entries(paper)
          .filter(([key, value]) => key.startsWith('extra_field_') && value && value !== '')
          .map(([key, value]) => (
            <div key={key} className="extracted-field-box">
              <span className="font-medium">{key.replace('extra_field_', 'Extracted Field ')}:</span> {value}
            </div>
        ))}
        {(paper.doi || paper.overton_url) && <PaperLink doi={paper.doi} overtonUrl={paper.overton_url} />}
      </CardContent>
    </Card>
  )
}

// function PaperMetadata({ paper }: { paper: Paper }) {
//   return (
//     <div className="paper-metadata">
//       <span>{paper.publication_year}</span>
//       <span><a href={paper.id} target="_blank">Link</a></span>
//       {paper.venue && (
//         <>
//           <span>•</span>
//           <span>{paper.venue}</span>
//         </>
//       )}
//     </div>
//   )
// }

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

function PaperLink({ doi, overtonUrl }: { doi?: string; overtonUrl?: string }) {
  const url = doi || overtonUrl
  const linkText = doi ? 'View Paper' : 'View Policy Document'
  
  return (
    <div className="pt-2">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="paper-link"
      >
        {linkText}
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  )
}