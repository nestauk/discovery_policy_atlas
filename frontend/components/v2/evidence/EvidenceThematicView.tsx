'use client'

import React, { useEffect, useMemo } from 'react'
import ThematicGroupAccordion from '@/components/v2/evidence/ThematicGroupAccordion'
import { useEvidenceStore } from '@/lib/evidenceStore'
import type { ThematicGroup } from '@/lib/evidenceStore'

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

  useEffect(() => {
    if (!projectId) return
    fetchThematicGroups(projectId, themeType)
  }, [projectId, themeType, fetchThematicGroups])

  const groups = themeType === 'intervention' ? interventionThematicGroups : issueThematicGroups
  const sortedGroups = useMemo(() => {
    const arr: ThematicGroup[] = Array.isArray(groups) ? [...groups] as ThematicGroup[] : []
    arr.sort((a: ThematicGroup, b: ThematicGroup) => (Number(b?.item_count) || 0) - (Number(a?.item_count) || 0))
    return arr
  }, [groups])

  if (isLoadingGroups) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div className="text-red-500">{String(error)}</div>
  }

  return (
    <ThematicGroupAccordion
      projectId={projectId}
      thematicGroups={sortedGroups}
      themeType={themeType}
    />
  )
}


