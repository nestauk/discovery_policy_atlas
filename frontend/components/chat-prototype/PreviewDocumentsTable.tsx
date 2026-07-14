'use client'

import { useMemo } from 'react'
import { Tooltip } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { getEvidenceCategoryColors, getEvidenceCategoryShortName } from '@/lib/evidenceCategories'
import { getEvidenceCategoryTooltipContent } from '@/lib/documentTooltips'

interface PreviewDoc {
  id: string
  title: string
  publication_year?: number
  evidence_category?: string
  evidence_category_reasoning?: string
  evidence_category_rank?: number
  evidence_strength?: number
  evidence_strength_justification?: string
  is_relevant?: boolean
  confidence?: number
  relevance_reason?: string
  landing_page_url?: string
  doi?: string
  overton_url?: string
  top_line?: string
  source?: string
  [key: string]: unknown
}

interface PreviewDocumentsTableProps {
  papers: PreviewDoc[]
  totalCount: number
  onOpenResultsPage?: () => void
}

export function PreviewDocumentsTable({
  papers,
  totalCount,
  onOpenResultsPage,
}: PreviewDocumentsTableProps) {
  const previewItems = useMemo(
    () =>
      papers.map((paper, index) => ({
        ...paper,
        rank: index + 1,
        url: paper.landing_page_url || (paper.doi ? paper.doi : paper.overton_url),
        sourceLabel:
          paper.source === 'openalex'
            ? 'Academic'
            : paper.source === 'overton'
              ? 'Policy'
              : paper.source || 'Unknown source',
    })),
    [papers]
  )
  const visibleItems = previewItems.slice(0, 3)

  return (
    <div className="w-full rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="px-4 py-3">
        <p className="text-sm font-medium text-slate-900">Strongest sources from the first pass</p>
        <p className="mt-1 text-sm leading-6 text-slate-600">
          A quick preview before you decide what to do next.
        </p>
      </div>

      <div className="divide-y divide-slate-200">
        {visibleItems.map((paper) => {
          const category = paper.evidence_category
          const colors = category ? getEvidenceCategoryColors(category) : null
          const displayName = category ? getEvidenceCategoryShortName(category) : null
          const tooltipContent = category
            ? getEvidenceCategoryTooltipContent(category, paper.evidence_category_reasoning)
            : null

          return (
            <div key={paper.id} className="px-4 py-3.5">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 text-xs font-semibold text-slate-400">#{paper.rank}</span>
                <div className="min-w-0 flex-1">
                  {paper.url ? (
                    <a
                      href={paper.url as string}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium leading-6 text-slate-900 hover:text-blue-700 hover:underline"
                    >
                      {paper.title}
                    </a>
                  ) : (
                    <p className="text-sm font-medium leading-6 text-slate-900">{paper.title}</p>
                  )}

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="rounded-full bg-slate-100 px-2 py-1 font-medium text-slate-700">
                      {paper.sourceLabel}
                    </span>
                    <span>{paper.publication_year && paper.publication_year > 0 ? paper.publication_year : 'Year unknown'}</span>
                  </div>

                  {paper.top_line && (
                    <p className="mt-2 text-sm leading-6 text-slate-600">{paper.top_line}</p>
                  )}
                </div>

                {displayName && colors && tooltipContent && (
                  <Tooltip content={tooltipContent}>
                    <span
                      className="inline-block max-w-[10rem] rounded px-2 py-1 text-xs font-medium leading-tight cursor-help text-right"
                      style={{ backgroundColor: colors.bg, color: colors.text }}
                    >
                      {displayName}
                    </span>
                  </Tooltip>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {onOpenResultsPage && totalCount > 3 && (
        <div className="border-t border-slate-200 px-4 py-3">
          <Button
            variant="outline"
            size="sm"
            onClick={onOpenResultsPage}
            className="rounded-full px-4"
          >
            View all {totalCount} documents
          </Button>
        </div>
      )}
    </div>
  )
}
