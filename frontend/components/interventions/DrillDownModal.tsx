'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Finding } from '@/types/search'
import { useAPI } from '@/lib/api'
import { useAnalysisProjectStore as useProjectStore } from '@/lib/analysisProjectStore'

interface DrillDownModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  interventionName?: string
  issueTheme?: string
}

export function DrillDownModal({ open, onOpenChange, interventionName, issueTheme }: DrillDownModalProps) {
  const { fetchWithAuth } = useAPI()
  const { activeProject } = useProjectStore()
  const [findings, setFindings] = useState<Finding[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const heading = useMemo(() => interventionName || issueTheme || 'Details', [interventionName, issueTheme])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!open || !activeProject?.id) return
      if (!interventionName && !issueTheme) return
      setLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams()
        if (interventionName) {
          params.append('intervention_name', interventionName)
        }
        if (issueTheme) {
          params.append('issue_theme', issueTheme)
        }
        const data = await fetchWithAuth(`api/analysis-projects/${activeProject.id}/findings?${params.toString()}`)
        if (!cancelled) setFindings(data as Finding[])
      } catch (e: unknown) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : 'Failed to load findings'
          setError(msg)
          setFindings(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [open, activeProject?.id, interventionName, issueTheme, fetchWithAuth])

  // Deduplicate findings (issues vs interventions use slightly different keys)
  const uniqueFindings = useMemo(() => {
    if (!findings) return [] as Finding[]
    const normalise = (s: unknown) => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase()
    const isInterv = Boolean(interventionName)
    const map = new Map<string, Finding>()
    for (const f of findings) {
      const baseId = normalise((f.Url as string) || f.SourceTitle)
      let key: string
      if (isInterv) {
        key = [
          baseId,
          normalise(f.Intervention),
          normalise(f.Outcome),
          normalise(f.EffectDirection),
        ].join('::')
      } else {
        const firstEvidence = Array.isArray(f.Evidence) && f.Evidence.length > 0 ? f.Evidence[0] : ''
        key = [baseId, normalise(firstEvidence)].join('::')
      }

      if (!map.has(key)) {
        map.set(key, { ...f, Evidence: Array.isArray(f.Evidence) ? [...f.Evidence] : [] })
      } else {
        const existing = map.get(key) as Finding
        const merged = new Set<string>([...(existing.Evidence || []), ...((f.Evidence || []) as string[])])
        existing.Evidence = Array.from(merged)
        map.set(key, existing)
      }
    }
    return Array.from(map.values())
  }, [findings, interventionName])

  // For issues: only keep narrative issue evidence (exclude quantitative intervention results)
  const displayFindings = useMemo(() => {
    const isInterv = Boolean(interventionName)
    if (isInterv) return uniqueFindings
    const filtered = uniqueFindings.filter((f) => {
      const hasQuant = Boolean(f.Outcome || f.EffectDirection || f.EffectSize || f.StudyDesign)
      const hasEvidence = Array.isArray(f.Evidence) && f.Evidence.length > 0
      return !hasQuant && hasEvidence
    })
    return filtered.length > 0 ? filtered : uniqueFindings
  }, [uniqueFindings, interventionName])

  const isIntervention = Boolean(interventionName)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{heading}</DialogTitle>
          <DialogDescription>
            Detailed evidence extracted from source documents.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[70vh] overflow-y-auto pr-2">
          {loading && <p>Loading details...</p>}
          {error && <p className="text-red-600">{error}</p>}
          {!loading && !error && (
            <div className="space-y-4">
              {displayFindings.map((f, idx) => (
                <Card key={idx} className="border-gray-200 break-words">
                  <CardHeader className="pb-3 space-y-1">
                    {/* Prominent label (issue or intervention) */}
                    <CardTitle className="text-lg font-semibold text-slate-900">
                      {isIntervention ? (interventionName || f.Intervention || 'Intervention') : (issueTheme || 'Issue')}
                    </CardTitle>
                    {/* Subtle source information */}
                    <div className="mt-1 text-sm text-slate-700 line-clamp-2 break-words">
                      {f.SourceTitle || 'Unknown Source'}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 min-w-0">
                      {typeof f.Year === 'number' && <span>{f.Year}</span>}
                      {f.Source && <span className="capitalize">{f.Source}</span>}
                      {f.Url && (
                        <a href={f.Url} target="_blank" rel="noreferrer" className="text-blue-600 hover:text-blue-800 hover:underline truncate max-w-full">
                          {f.Url}
                        </a>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm overflow-hidden">
                    {isIntervention ? (
                      <>
                        {(f.Outcome || f.EffectDirection || f.EffectSize || f.PValue || f.Uncertainty || f.StudyDesign) && (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <div>
                              <span className="text-slate-500">Outcome:</span>{' '}
                              <span className="font-medium">{f.Outcome || '—'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500">Effect:</span>{' '}
                              <span className="font-medium">{f.EffectDirection || '—'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500">Effect size:</span>{' '}
                              <span className="font-medium">{f.EffectSize ? `${f.EffectSize}${f.EffectSizeType ? ` (${f.EffectSizeType})` : ''}` : '—'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500">P-value:</span>{' '}
                              <span className="font-medium">{f.PValue || '—'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500">Uncertainty:</span>{' '}
                              <span className="font-medium">{f.Uncertainty ? `±${f.Uncertainty}` : '—'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500">Design:</span>{' '}
                              <span className="font-medium">{f.StudyDesign || '—'}</span>
                            </div>
                          </div>
                        )}
                        {Array.isArray(f.Evidence) && f.Evidence.length > 0 && (
                          <div className="bg-white rounded p-3 border break-words">
                            <div className="text-xs text-gray-500 mb-2">Supporting Evidence</div>
                            <div className="space-y-3">
                              {f.Evidence.map((e, i) => (
                                <blockquote key={i} className="italic border-l-2 border-slate-200 pl-3 text-slate-800 whitespace-pre-wrap break-words">
                                  “{e}”
                                </blockquote>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        {Array.isArray(f.Evidence) && f.Evidence.length > 0 && (
                          <div className="bg-white rounded p-3 border break-words">
                            <div className="text-xs text-gray-500 mb-2">Supporting Evidence</div>
                            <div className="space-y-3">
                              {f.Evidence.map((e, i) => (
                                <blockquote key={i} className="italic border-l-2 border-slate-200 pl-3 text-slate-800 whitespace-pre-wrap break-words">
                                  “{e}”
                                </blockquote>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* For issues, we intentionally omit quantitative study fields */}
                      </>
                    )}
                  </CardContent>
                </Card>
              ))}
              {!findings?.length && (
                <p className="text-sm text-muted-foreground">No findings found.</p>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}


