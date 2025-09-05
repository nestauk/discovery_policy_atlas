'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
  const { getAnalysisFindings } = useAPI()
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
        const data = await getAnalysisFindings(activeProject.id, {
          intervention_name: interventionName,
          issue_theme: issueTheme,
        })
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
  // Intentionally exclude getAnalysisFindings to avoid unstable deps causing refetch loops
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeProject?.id, interventionName, issueTheme])

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
              {findings?.map((f, idx) => (
                <Card key={idx}>
                  <CardHeader>
                    <CardTitle className="text-base">
                      {f.SourceTitle || 'Unknown Source'}
                    </CardTitle>
                    {f.Url && (
                      <a href={f.Url} target="_blank" rel="noreferrer" className="text-sm text-blue-600 hover:underline break-all">{f.Url}</a>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex flex-wrap gap-2">
                      {f.Intervention && <Badge variant="secondary">{f.Intervention}</Badge>}
                      {f.StudyDesign && <Badge variant="outline">{f.StudyDesign}</Badge>}
                      {typeof f.Year === 'number' && <Badge variant="outline">{f.Year}</Badge>}
                      {f.Source && <Badge variant="outline">{f.Source}</Badge>}
                    </div>
                    {(f.Outcome || f.EffectDirection || f.EffectSize) && (
                      <div>
                        <div><strong>Outcome:</strong> {f.Outcome || 'Not specified'}</div>
                        <div><strong>Effect Direction:</strong> {f.EffectDirection || 'Not specified'}</div>
                        <div><strong>Effect Size:</strong> {f.EffectSize || 'Not specified'} {f.EffectSizeType ? `(${f.EffectSizeType})` : ''}</div>
                        <div><strong>P-Value:</strong> {f.PValue || 'Not specified'}</div>
                        <div><strong>Uncertainty:</strong> {f.Uncertainty || 'Not specified'}</div>
                      </div>
                    )}
                    {f.Evidence?.length ? (
                      <div>
                        <strong>Evidence:</strong>
                        <ul className="list-disc pl-5">
                          {f.Evidence.map((e, i) => (
                            <li key={i} className="leading-relaxed">{e}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
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


