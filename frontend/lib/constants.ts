// Frontend constants - single source of truth for default values
// These should match the backend config values in backend/app/core/config.py
export const SEARCH_DEFAULTS = {
  MAX_RESULTS: 50,           // matches DEFAULT_MAX_RESULTS
  MAX_RESULTS_LIMIT: 1000,   // matches MAX_SEARCH_RESULTS
  SOURCE: 'overton' as const,
  SEMANTIC_SEARCH: true,
} as const

// Type for the source options
export type SearchSource = 'overton' | 'openalex' | 'mediacloud' 