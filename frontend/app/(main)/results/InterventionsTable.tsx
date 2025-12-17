'use client'

import { PolicyIntervention } from '@/types/search'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useMemo, useState } from 'react'
import { DrillDownModal } from '@/components/v2/results/DrillDownModal'

interface Props {
  interventions: PolicyIntervention[]
}

export function InterventionsTable({ interventions }: Props) {
  const [sortAsc, setSortAsc] = useState(false)
  const [selected, setSelected] = useState<PolicyIntervention | null>(null)
  const sorted = useMemo(() => {
    const arr = [...interventions]
    arr.sort((a, b) => {
      const af = a.frequency ?? (a.supporting_doc_ids?.length || 0)
      const bf = b.frequency ?? (b.supporting_doc_ids?.length || 0)
      return sortAsc ? af - bf : bf - af
    })
    return arr
  }, [interventions, sortAsc])

  return (
    <>
    <Card>
      <CardHeader>
        <CardTitle>Policy Interventions</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2 pr-4">Intervention</th>
                <th className="py-2 pr-4">Brief</th>
                <th className="py-2 pr-4">Impact Summary</th>
                <th className="py-2 text-right">
                  <button className="underline-offset-2 hover:underline" onClick={() => setSortAsc(v => !v)}>
                    Frequency {sortAsc ? '↑' : '↓'}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item, index) => (
                <tr key={index} className="border-b last:border-0 cursor-pointer hover:bg-muted/50" onClick={() => setSelected(item)}>
                  <td className="py-2 pr-4 font-medium">{item.intervention_name}</td>
                  <td className="py-2 pr-4 text-slate-700">{item.brief_description}</td>
                  <td className="py-2 pr-4 text-slate-700">{item.impact_summary}</td>
                  <td className="py-2 text-right">{item.frequency ?? (item.supporting_doc_ids?.length || 0)}</td>
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
        interventionName={selected?.intervention_name}
      />
    )}
    </>
  )
}


