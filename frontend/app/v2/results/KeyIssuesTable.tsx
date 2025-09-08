'use client'

import { KeyIssue } from '@/types/search'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useMemo, useState } from 'react'
import { DrillDownModal } from '@/components/v2/results/DrillDownModal'

interface Props {
  issues: KeyIssue[]
}

export function KeyIssuesTable({ issues }: Props) {
  const [sortAsc, setSortAsc] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const sorted = useMemo(() => {
    const arr = [...issues]
    arr.sort((a, b) => (sortAsc ? a.frequency - b.frequency : b.frequency - a.frequency))
    return arr
  }, [issues, sortAsc])

  return (
    <>
    <Card>
      <CardHeader>
        <CardTitle>Key Issues</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2 pr-4">Issue/Theme</th>
                <th className="py-2 pr-4">Description</th>
                <th className="py-2 text-right">
                  <button className="underline-offset-2 hover:underline" onClick={() => setSortAsc(v => !v)}>
                    Frequency {sortAsc ? '↑' : '↓'}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((issue, index) => (
                <tr key={index} className="border-b last:border-0 cursor-pointer hover:bg-muted/50" onClick={() => setSelected(issue.issue_theme)}>
                  <td className="py-2 pr-4 font-medium">{issue.issue_theme}</td>
                  <td className="py-2 pr-4 text-slate-700">{issue.summary_description}</td>
                  <td className="py-2 text-right">{issue.frequency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
    {selected && (
      <DrillDownModal
        open={!!selected}
        onOpenChange={(o) => !o && setSelected(null)}
        issueTheme={selected || undefined}
      />
    )}
    </>
  )
}


