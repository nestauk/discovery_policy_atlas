'use client'

import { PaperCard } from './paper-card'
import type { Paper } from '@/types/search'

interface PapersListProps {
  papers: Paper[]
}

export function PapersList({ papers }: PapersListProps) {
  return (
    <div className="space-y-4">
      {papers.map((paper) => (
        <PaperCard key={paper.id} paper={paper} />
      ))}
    </div>
  )
}