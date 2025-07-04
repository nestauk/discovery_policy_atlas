// Frontend constants - single source of truth for default values
// These should match the backend config values in backend/app/core/config.py
export const SEARCH_DEFAULTS = {
  MAX_RESULTS: 50,           // matches DEFAULT_MAX_RESULTS
  MAX_RESULTS_LIMIT: 1000,   // matches MAX_SEARCH_RESULTS
  SOURCE: 'overton' as const,
  SEMANTIC_SEARCH: true,
  DATE_FROM: '2020-01-01',
  get DATE_TO() {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  },
} as const

// Type for the source options
export type SearchSource = 'overton' | 'openalex' | 'mediacloud' 