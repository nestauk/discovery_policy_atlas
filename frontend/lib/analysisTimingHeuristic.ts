const SYNTHESIS_STEP_SECONDS = [119, 133, 518, 304] as const

export const ANALYSIS_TIMING_HEURISTIC = {
  retrievalOverheadMinutes: 2,
  defaultRelevantRatio: 0.6,
  extractionSecondsPerRelevantDocument: 15,
  synthesisStepSeconds: SYNTHESIS_STEP_SECONDS,
  synthesisSeconds: SYNTHESIS_STEP_SECONDS.reduce((sum, seconds) => sum + seconds, 0),
} as const

export function estimateTotalAnalysisMinutes(maxResults: number, sourceCount: number): number {
  const effectiveSources = Math.max(1, sourceCount)
  const configuredDocs = Math.max(1, maxResults * effectiveSources)
  const estimatedRelevantDocs = Math.max(
    1,
    Math.round(configuredDocs * ANALYSIS_TIMING_HEURISTIC.defaultRelevantRatio),
  )

  const extractionMinutes =
    (estimatedRelevantDocs * ANALYSIS_TIMING_HEURISTIC.extractionSecondsPerRelevantDocument) / 60
  const synthesisMinutes = ANALYSIS_TIMING_HEURISTIC.synthesisSeconds / 60

  return ANALYSIS_TIMING_HEURISTIC.retrievalOverheadMinutes + extractionMinutes + synthesisMinutes
}

type AnalysisDurationRange = { minMinutes: number; maxMinutes: number }

export function estimateAnalysisDurationRange(
  maxResults: number,
  sourceCount: number,
  options: {
    minMultiplier?: number
    maxMultiplier?: number
    roundingMinutes?: number
    minMinutesFloor?: number
    minSpreadMinutes?: number
  } = {},
): AnalysisDurationRange {
  const minMultiplier = options.minMultiplier ?? 0.7
  const maxMultiplier = options.maxMultiplier ?? 1.3
  const roundingMinutes = options.roundingMinutes ?? 5
  const minMinutesFloor = options.minMinutesFloor ?? 10
  const minSpreadMinutes = options.minSpreadMinutes ?? 5
  const baseMinutes = estimateTotalAnalysisMinutes(maxResults, sourceCount)
  const roundToStep = (value: number) => Math.round(value / roundingMinutes) * roundingMinutes
  const minMinutes = Math.max(minMinutesFloor, roundToStep(baseMinutes * minMultiplier))
  const maxMinutes = Math.max(minMinutes + minSpreadMinutes, roundToStep(baseMinutes * maxMultiplier))

  return { minMinutes, maxMinutes }
}

type RemainingRange = { min: number; max: number } | null
type RemainingRangeOptions = {
  varianceRatio?: number
  roundingMinutes?: number
  minSpreadMinutes?: number
  minMinutesFloor?: number
}

export interface ProjectProgressInfo {
  stage: string
  progress: number
  text: string
  remainingRange: RemainingRange
}

interface ProjectProgressInput {
  projectId?: string | null
  activeProject?: {
    status?: string
    search_query?: {
      max_results?: number
      limit?: number
      sources?: string[]
    }
    progress?: {
      stage_label: string
      step_index: number
      stage_started_at?: string | null
    } | null
  } | null
  documents: Array<{
    is_relevant?: boolean
    extraction_status?: string
  }>
  elapsedMinutes: number | null
}

function estimateRemainingRangeMinutes(
  baseMinutes: number,
  options: RemainingRangeOptions = {},
): { min: number; max: number } {
  const varianceRatio = options.varianceRatio ?? 0.3
  const roundingMinutes = options.roundingMinutes ?? 5
  const minSpreadMinutes = options.minSpreadMinutes ?? 5
  const minMinutesFloor = options.minMinutesFloor ?? 5
  const safeBaseMinutes = Math.max(0, baseMinutes)
  const roundToStep = (value: number) => Math.round(value / roundingMinutes) * roundingMinutes

  const min = Math.max(minMinutesFloor, roundToStep(safeBaseMinutes * (1 - varianceRatio)))
  const max = Math.max(min + minSpreadMinutes, roundToStep(safeBaseMinutes * (1 + varianceRatio)))

  return { min, max }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function computeProgressFromElapsedAndRemaining(
  elapsedMinutes: number | null,
  remainingMinutes: number,
  minProgress: number = 1,
  maxProgress: number = 95,
): number | null {
  if (elapsedMinutes === null) return null
  const safeElapsed = Math.max(0, elapsedMinutes)
  const safeRemaining = Math.max(0, remainingMinutes)
  const total = Math.max(1, safeElapsed + safeRemaining)
  return clamp(Math.round((safeElapsed / total) * 100), minProgress, maxProgress)
}

function getSynthesisEtaRangeOptions(remainingMinutes: number): RemainingRangeOptions {
  if (remainingMinutes <= 10) {
    return {
      varianceRatio: 0.1,
      roundingMinutes: 1,
      minSpreadMinutes: 1,
      minMinutesFloor: 1,
    }
  }
  if (remainingMinutes <= 20) {
    return {
      varianceRatio: 0.15,
      roundingMinutes: 1,
      minSpreadMinutes: 2,
      minMinutesFloor: 2,
    }
  }
  return {
    varianceRatio: 0.2,
    roundingMinutes: 5,
    minSpreadMinutes: 5,
    minMinutesFloor: 5,
  }
}

export function computeProjectProgressInfo({
  projectId,
  activeProject,
  documents,
  elapsedMinutes,
}: ProjectProgressInput): ProjectProgressInfo {
  if (!projectId || !activeProject) {
    return {
      stage: 'idle',
      progress: 0,
      text: 'No project selected',
      remainingRange: null,
    }
  }

  const status = activeProject.status ?? 'unknown'
  const backendProgress = activeProject.progress
  const configuredMaxResults = activeProject.search_query?.max_results ?? activeProject.search_query?.limit ?? 30
  const configuredSourcesCount = activeProject.search_query?.sources?.length ?? 2
  const configuredDocs = Math.max(1, configuredMaxResults * Math.max(1, configuredSourcesCount))
  const defaultRelevantRatio = ANALYSIS_TIMING_HEURISTIC.defaultRelevantRatio
  const observedRelevantDocs = documents.filter((doc) => doc.is_relevant !== false).length
  const estimatedRelevantDocs = Math.max(
    1,
    observedRelevantDocs > 0 ? observedRelevantDocs : Math.round(configuredDocs * defaultRelevantRatio),
  )
  const overheadMinutes = ANALYSIS_TIMING_HEURISTIC.retrievalOverheadMinutes
  const extractionMinutes =
    (estimatedRelevantDocs * ANALYSIS_TIMING_HEURISTIC.extractionSecondsPerRelevantDocument) / 60
  const synthesisMinutes = ANALYSIS_TIMING_HEURISTIC.synthesisSeconds / 60
  const estimatedTotalMinutes = overheadMinutes + extractionMinutes + synthesisMinutes
  const estimatedRemainingBaseMinutes =
    elapsedMinutes !== null
      ? Math.max(1, estimatedTotalMinutes - elapsedMinutes)
      : estimatedTotalMinutes

  if (status === 'created') {
    return {
      stage: 'created',
      progress: 0,
      text: 'Analysis not started',
      remainingRange: null,
    }
  }

  if (status === 'running') {
    if (documents.length === 0) {
      return {
        stage: 'retrieving',
        progress: computeProgressFromElapsedAndRemaining(elapsedMinutes, estimatedRemainingBaseMinutes) ?? 0,
        text: 'Retrieving and screening documents...',
        remainingRange: estimateRemainingRangeMinutes(estimatedRemainingBaseMinutes),
      }
    }

    const relevantDocs = documents.filter((doc) => doc.is_relevant !== false)
    const totalRelevantDocs = relevantDocs.length
    const extractedDocs = relevantDocs.filter(
      (doc) => doc.extraction_status === 'completed' || doc.extraction_status === 'success',
    ).length

    if (extractedDocs === 0) {
      return {
        stage: 'extracting',
        progress: computeProgressFromElapsedAndRemaining(elapsedMinutes, estimatedRemainingBaseMinutes) ?? 0,
        text: 'Extracting intervention data from documents...',
        remainingRange: estimateRemainingRangeMinutes(estimatedRemainingBaseMinutes),
      }
    }

    return {
      stage: 'extracting',
      progress: computeProgressFromElapsedAndRemaining(elapsedMinutes, estimatedRemainingBaseMinutes) ?? 0,
      text: `Extracting intervention data from documents... (${extractedDocs}/${totalRelevantDocs})`,
      remainingRange: estimateRemainingRangeMinutes(estimatedRemainingBaseMinutes),
    }
  }

  if (status === 'synthesising') {
    const synthesisStepSeconds = ANALYSIS_TIMING_HEURISTIC.synthesisStepSeconds
    const synthesisStepTotal = synthesisStepSeconds.length
    const stepIndex = clamp(backendProgress?.step_index || 1, 1, synthesisStepTotal)
    const expectedCurrentStepSeconds = synthesisStepSeconds[stepIndex - 1] || 1
    const stageStartedAtMs = backendProgress?.stage_started_at
      ? Date.parse(backendProgress.stage_started_at)
      : Number.NaN
    const elapsedInCurrentStepSeconds = Number.isNaN(stageStartedAtMs)
      ? 0
      : Math.max(0, (Date.now() - stageStartedAtMs) / 1000)
    const remainingCurrentStepSeconds = Math.max(0, expectedCurrentStepSeconds - elapsedInCurrentStepSeconds)
    const remainingFutureStepSeconds = synthesisStepSeconds
      .slice(stepIndex)
      .reduce((sum, seconds) => sum + seconds, 0)
    const synthesisRemainingMinutes = Math.max(
      1,
      (remainingCurrentStepSeconds + remainingFutureStepSeconds) / 60,
    )

    return {
      stage: 'synthesising',
      progress: computeProgressFromElapsedAndRemaining(elapsedMinutes, synthesisRemainingMinutes) ?? 0,
      text: backendProgress?.stage_label || 'Generating summary and insights...',
      remainingRange: estimateRemainingRangeMinutes(
        synthesisRemainingMinutes,
        getSynthesisEtaRangeOptions(synthesisRemainingMinutes),
      ),
    }
  }

  if (status === 'completed') {
    return {
      stage: 'completed',
      progress: 100,
      text: 'Analysis completed',
      remainingRange: null,
    }
  }

  if (status === 'failed') {
    return {
      stage: 'failed',
      progress: 0,
      text: 'Analysis failed',
      remainingRange: null,
    }
  }

  return {
    stage: 'unknown',
    progress: 0,
    text: 'Unknown status',
    remainingRange: null,
  }
}
