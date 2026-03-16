'use client'

import { Badge } from '@/components/ui/badge'
import { FileText } from 'lucide-react'

export interface PreviewDocument {
  id: string
  title: string
  year?: number
  source?: string
  evidence_category?: string
  is_relevant?: boolean
}

interface DocumentPreviewCardProps {
  documents: PreviewDocument[]
  totalCount: number
}

const categoryColors: Record<string, string> = {
  'Systematic review': 'bg-violet-100 text-violet-800',
  'Randomised controlled trial': 'bg-blue-100 text-blue-800',
  'Quasi-experimental study': 'bg-cyan-100 text-cyan-800',
  'Observational study': 'bg-amber-100 text-amber-800',
  'Qualitative research': 'bg-emerald-100 text-emerald-800',
  'Case study': 'bg-rose-100 text-rose-800',
  'Policy evaluation': 'bg-indigo-100 text-indigo-800',
}

export function DocumentPreviewCard({ documents, totalCount }: DocumentPreviewCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
        <FileText className="w-4 h-4 text-slate-500" />
        <span className="text-sm font-semibold text-slate-700">
          Top {documents.length} of {totalCount} sources
        </span>
      </div>
      <div className="divide-y divide-slate-100">
        {documents.map((doc) => (
          <div key={doc.id} className="px-4 py-2.5 flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-900 line-clamp-1">{doc.title}</p>
              <div className="flex items-center gap-2 mt-1">
                {doc.year && <span className="text-xs text-slate-500">{doc.year}</span>}
                {doc.source && (
                  <span className="text-xs text-slate-400">
                    {doc.source === 'openalex' ? 'Academic' : 'Grey lit.'}
                  </span>
                )}
              </div>
            </div>
            {doc.evidence_category && (
              <Badge
                variant="secondary"
                className={`text-[10px] flex-shrink-0 ${categoryColors[doc.evidence_category] || 'bg-slate-100 text-slate-600'}`}
              >
                {doc.evidence_category}
              </Badge>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
