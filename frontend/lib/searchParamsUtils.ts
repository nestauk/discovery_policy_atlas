// Utility functions for handling search parameters
// Follows DRY and Single Responsibility principles

import type { AnalysisProject } from './analysisProjectStore'

type SearchQuery = NonNullable<AnalysisProject['search_query']>

// Build URL parameters from search query (used by SearchPlanModal)
export function buildSearchParams(searchQuery: SearchQuery): string {
  const params = new URLSearchParams()
  
  const paramMap: Record<string, string | null> = {
    query: searchQuery.original_query || null,
    sub_questions: searchQuery.sub_questions ? JSON.stringify(searchQuery.sub_questions) : null,
    sources: searchQuery.sources?.join(',') || null,
    geography_filter: searchQuery.geography_filter ? JSON.stringify(searchQuery.geography_filter) : null,
    time_preset: searchQuery.time_preset || null,
    time_from: searchQuery.time_from || null,
    time_to: searchQuery.time_to || null,
    limit: searchQuery.limit?.toString() || null,
    scope: searchQuery.scope ? JSON.stringify(searchQuery.scope) : null,
    custom_focus: searchQuery.custom_focus ? JSON.stringify(searchQuery.custom_focus) : null,
    excludes: searchQuery.excludes ? JSON.stringify(searchQuery.excludes) : null,
    custom_excludes: searchQuery.custom_excludes ? JSON.stringify(searchQuery.custom_excludes) : null,
  }

  Object.entries(paramMap).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })

  return params.toString()
}

// Parse URL parameters into search state (used by ChatInterface)
export function parseSearchParams(searchParams: URLSearchParams) {
  const updates: Record<string, string | string[] | number | { academic: boolean; policy: boolean }> = {}

  const query = searchParams.get('query')
  if (query) {
    updates.researchQuestion = query

    // Parse arrays safely
    const parseJsonParam = (param: string | null) => {
      if (!param) return undefined
      try {
        return JSON.parse(param)
      } catch {
        return undefined
      }
    }

    const subQuestions = parseJsonParam(searchParams.get('sub_questions'))
    if (subQuestions) updates.subQuestions = subQuestions

    const geography = parseJsonParam(searchParams.get('geography_filter'))
    if (geography) updates.geography = geography

    const scope = parseJsonParam(searchParams.get('scope'))
    if (scope) updates.scope = scope

    const customFocus = parseJsonParam(searchParams.get('custom_focus'))
    if (customFocus) updates.customFocus = customFocus

    const excludes = parseJsonParam(searchParams.get('excludes'))
    if (excludes) updates.excludes = excludes

    const customExcludes = parseJsonParam(searchParams.get('custom_excludes'))
    if (customExcludes) updates.customExcludes = customExcludes

    // Parse sources
    const sources = searchParams.get('sources')
    if (sources) {
      const sourceList = sources.split(',')
      updates.access = {
        academic: sourceList.includes('openalex'),
        policy: sourceList.includes('overton'),
      }
    }

    // Parse simple values
    const timePreset = searchParams.get('time_preset')
    if (timePreset) updates.timePreset = timePreset

    const timeFrom = searchParams.get('time_from')
    if (timeFrom) updates.customFrom = timeFrom

    const timeTo = searchParams.get('time_to')
    if (timeTo) updates.customTo = timeTo

    const limit = searchParams.get('limit')
    if (limit) updates.maxResults = parseInt(limit, 10)
  }

  return updates
}