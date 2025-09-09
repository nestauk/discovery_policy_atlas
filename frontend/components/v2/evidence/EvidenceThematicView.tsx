'use client'

import React, { useEffect, useMemo, useState } from 'react'
import ThematicGroupAccordion from '@/components/v2/evidence/ThematicGroupAccordion'
import { useEvidenceStore, EvidenceItem, ThematicGroup } from '@/lib/evidenceStore'
import { fetchWithAuthExternal } from '@/lib/api'
import { InterventionsTable, type InterventionData } from '@/components/search/interventions-table'
import EvidenceIssuesTable from '@/components/v2/evidence/EvidenceIssuesTable'

type EvidenceThematicViewProps = {
  projectId: string
  themeType: 'intervention' | 'issue'
}

export default function EvidenceThematicView({ projectId, themeType }: EvidenceThematicViewProps) {
  const {
    fetchThematicGroups,
    isLoadingGroups,
    error,
    interventionThematicGroups,
    issueThematicGroups,
  } = useEvidenceStore()
  // Fallback state when synthesis/themes are not yet available
  const [fallbackLoading, setFallbackLoading] = useState(false)
  const [fallbackError, setFallbackError] = useState<string | null>(null)
  const [fallbackInterventions, setFallbackInterventions] = useState<InterventionData[] | null>(null)
  const [fallbackIssues, setFallbackIssues] = useState<EvidenceItem[] | null>(null)

  useEffect(() => {
    if (!projectId) return
    fetchThematicGroups(projectId, themeType)
  }, [projectId, themeType, fetchThematicGroups])

  const groups: ThematicGroup[] = themeType === 'intervention' ? interventionThematicGroups : issueThematicGroups
  const sortedGroups = useMemo(() => {
    const arr = Array.isArray(groups) ? [...groups] : []
    arr.sort((a: ThematicGroup, b: ThematicGroup) => (b?.item_count || 0) - (a?.item_count || 0))
    return arr
  }, [groups])

  // Load fallback content if no groups
  useEffect(() => {
    let cancelled = false
    type ExtractionRow = {
      id: string | number
      extraction_type?: string
      type?: string
      raw_data?: {
        supporting_evidence?: unknown[]
        explanation?: string
        description?: string
        label?: string
      }
      label?: string
      description?: string
      supporting_quote?: string
      analysis_document_id?: string | number
    }
    const loadFallback = async () => {
      if (!projectId) return
      if (sortedGroups.length > 0) return
      setFallbackLoading(true)
      setFallbackError(null)
      try {
        if (themeType === 'intervention') {
          const resp = await fetchWithAuthExternal(`api/analysis-projects/${projectId}/interventions`)
          if (!cancelled) setFallbackInterventions((resp?.interventions || []) as InterventionData[])
        } else {
          // Build ungrouped issues from analysis project extractions
          const data = await fetchWithAuthExternal(`api/analysis-projects/${projectId}`)
          const docs = data?.documents || []
          const docByUuid: Record<string, Record<string, unknown>> = {}
          for (const d of docs) {
            docByUuid[String(d.id)] = d
          }
          const extRows: ExtractionRow[] = (data?.extractions || []) as ExtractionRow[]
          const issues: EvidenceItem[] = []
          for (const row of extRows) {
            if ((row.extraction_type || row.type) !== 'issue') continue
            const raw = row.raw_data || {}
            const title = row.label || raw.label || ''
            if (!title) continue
            const desc = row.description || raw.explanation || raw.description || ''
            let supporting: string[] = []
            if (Array.isArray(raw.supporting_evidence)) {
              supporting = (raw.supporting_evidence as unknown[])
                .map((s) => String(s ?? ''))
                .filter((s): s is string => s.trim().length > 0)
            }
            if (row.supporting_quote) supporting = supporting.concat([row.supporting_quote])
            const doc = (docByUuid[String(row.analysis_document_id)] || {}) as Record<string, unknown>
            issues.push({
              id: row.id,
              title,
              brief_description: desc,
              frequency: 1,
              outcomes: [],
              supporting_evidence: supporting.filter(Boolean),
              countries: [],
              document: {
                doc_id: String(doc.doc_id || ''),
                title: typeof doc.title === 'string' ? doc.title : undefined,
                source: typeof doc.source === 'string' ? doc.source : undefined,
                landing_page_url: typeof doc.landing_page_url === 'string' ? doc.landing_page_url : undefined,
                year: typeof doc.year === 'number' ? doc.year : undefined,
                venue: typeof doc.venue === 'string' ? doc.venue : undefined,
                source_type: typeof doc.source_type === 'string' ? doc.source_type : undefined,
                source_country: typeof doc.source_country === 'string' ? doc.source_country : undefined,
              },
            })
          }
          if (!cancelled) setFallbackIssues(issues)
        }
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : 'Failed to load fallback content'
        if (!cancelled) setFallbackError(message)
      } finally {
        if (!cancelled) setFallbackLoading(false)
      }
    }
    loadFallback()
    return () => { cancelled = true }
  }, [projectId, themeType, sortedGroups.length])

  if (isLoadingGroups) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div className="text-red-500">{String(error)}</div>
  }

  // Fallback when no groups are available yet
  if (sortedGroups.length === 0) {
    if (fallbackLoading) return <div>Loading...</div>
    if (fallbackError) return <div className="text-red-500">{fallbackError}</div>
    if (themeType === 'intervention') {
      return <InterventionsTable interventions={fallbackInterventions || []} />
    }
    return <EvidenceIssuesTable issues={fallbackIssues || []} />
  }

  return (
    <ThematicGroupAccordion
      projectId={projectId}
      thematicGroups={sortedGroups}
      themeType={themeType}
    />
  )
}


