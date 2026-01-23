/**
 * Evidence category utilities for display across intervention tables.
 *
 * This file provides evidence category display utilities, with data fetched
 * from the backend API to ensure consistency between frontend and backend.
 */

// Types for evidence category data
export interface EvidenceCategory {
  name: string
  key: string
  score: number
  rank: number
  short_name: string
  bg_color: string
  text_color: string
}

export interface EvidenceCategoryColors {
  bg: string
  text: string
}

// Cache for API data
let cachedCategories: EvidenceCategory[] | null = null
let fetchPromise: Promise<EvidenceCategory[]> | null = null

/**
 * Fetch evidence categories from the backend API.
 * Uses caching to avoid repeated requests.
 */
export async function fetchEvidenceCategories(): Promise<EvidenceCategory[]> {
  if (cachedCategories) {
    return cachedCategories
  }

  if (fetchPromise) {
    return fetchPromise
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const cleanBaseUrl = baseUrl.replace(/\/$/, '')

  fetchPromise = fetch(`${cleanBaseUrl}/api/config/evidence-categories`)
    .then(res => {
      if (!res.ok) throw new Error('Failed to fetch evidence categories')
      return res.json()
    })
    .then(data => {
      cachedCategories = data.categories
      return cachedCategories!
    })
    .catch(err => {
      console.error('Failed to fetch evidence categories:', err)
      // Fall back to static data on error
      cachedCategories = FALLBACK_CATEGORIES
      return cachedCategories
    })
    .finally(() => {
      fetchPromise = null
    })

  return fetchPromise
}

/**
 * Get cached categories synchronously (returns fallback if not yet fetched).
 * Call fetchEvidenceCategories() first to ensure data is loaded.
 */
export function getEvidenceCategories(): EvidenceCategory[] {
  return cachedCategories || FALLBACK_CATEGORIES
}

// Fallback static data (mirrors backend, used before API fetch completes)
const FALLBACK_CATEGORIES: EvidenceCategory[] = [
  { name: 'Systematic Review and Meta-Analysis', key: 'systematic_review', score: 5, rank: 1, short_name: 'Systematic Review', bg_color: '#0F294A', text_color: '#FFFFFF' },
  { name: 'RCTs and Quasi-Experimental Studies', key: 'rct', score: 4, rank: 2, short_name: 'RCT/Quasi-Exp', bg_color: '#9A1BBE', text_color: '#FFFFFF' },
  { name: 'Observational Research Studies', key: 'observational', score: 3, rank: 3, short_name: 'Observational', bg_color: '#0000FF', text_color: '#FFFFFF' },
  { name: 'Modelling & Simulation', key: 'modelling', score: 2, rank: 4, short_name: 'Modelling', bg_color: '#18A48C', text_color: '#FFFFFF' },
  { name: 'Policy Syntheses & Guidance Documents', key: 'policy', score: 2, rank: 5, short_name: 'Policy Guidance', bg_color: '#97D9E3', text_color: '#111827' },
  { name: 'Qualitative & Contextual Evidence', key: 'qualitative', score: 2, rank: 6, short_name: 'Qualitative', bg_color: '#A59BEE', text_color: '#111827' },
  { name: 'Expert Opinion and Commentary', key: 'opinion', score: 1, rank: 7, short_name: 'Expert Opinion', bg_color: '#F6A4B7', text_color: '#111827' },
  { name: 'Other (Non-evidence documents)', key: 'other', score: 0, rank: 8, short_name: 'Other', bg_color: '#F8F5F4', text_color: '#374151' },
  { name: 'Unknown / Insufficient information', key: 'unknown', score: 0, rank: 9, short_name: 'Unknown', bg_color: '#F8F5F4', text_color: '#374151' },
]

/**
 * Get colors for an evidence category, with fallback for unknown categories.
 * Returns raw hex values for use with inline styles (Tailwind can't handle dynamic class names).
 */
export function getEvidenceCategoryColors(category: string): EvidenceCategoryColors {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.name === category)
  if (found) {
    return {
      bg: found.bg_color,
      text: found.text_color,
    }
  }
  return { bg: '#F3F4F6', text: '#374151' }  // gray-100, gray-700
}

/**
 * Get colors for an evidence mix key (derived from category colors).
 * Returns raw hex values for use with inline styles.
 */
export function getEvidenceMixColors(key: string): EvidenceCategoryColors {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.key === key)
  if (found) {
    return {
      bg: found.bg_color,
      text: found.text_color,
    }
  }
  return { bg: '#F3F4F6', text: '#374151' }  // gray-100, gray-700
}

/**
 * Get short display name for an evidence category, with fallback to full name.
 */
export function getEvidenceCategoryShortName(category: string): string {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.name === category)
  return found?.short_name || category
}

/**
 * Get display name for an evidence mix key.
 */
export function getEvidenceMixDisplayName(key: string): string {
  // Short names for evidence mix display
  const shortNames: Record<string, string> = {
    'systematic_review': 'SR/MA',
    'rct': 'RCT',
    'observational': 'Observational',
    'modelling': 'Modelling',
    'policy': 'Policy',
    'qualitative': 'Qualitative',
    'opinion': 'Opinion',
    'unknown': 'Unknown',
  }
  return shortNames[key] || key
}

/**
 * Full names for evidence types (used in explanations).
 */
const EVIDENCE_TYPE_FULL_NAMES: Record<string, string> = {
  'systematic_review': 'systematic reviews/meta-analyses',
  'rct': 'RCTs/quasi-experimental studies',
  'observational': 'observational studies',
  'modelling': 'modelling/simulation studies',
  'policy': 'policy syntheses',
  'qualitative': 'qualitative evidence',
  'opinion': 'expert opinion',
  'unknown': 'unclassified evidence',
}

/** Evidence types in order of strength (strongest first) */
const EVIDENCE_TYPE_ORDER = [
  'systematic_review', 'rct', 'observational', 'modelling',
  'policy', 'qualitative', 'opinion'
] as const

/**
 * Generate an explanation for an intervention theme's evidence score.
 * DATA-DRIVEN: Only mentions evidence types actually present in the mix.
 */
export function getEvidenceScoreExplanation(
  stars: number,
  evidenceMix?: Record<string, number>,
  capMessage?: string | null,
): string {
  const parts: string[] = []

  // Build explanation based on ACTUAL evidence present, not star level
  if (evidenceMix && Object.keys(evidenceMix).length > 0) {
    const presentTypes = EVIDENCE_TYPE_ORDER
      .filter(key => evidenceMix[key] && evidenceMix[key] > 0)
      .map(key => EVIDENCE_TYPE_FULL_NAMES[key])

    if (presentTypes.length > 0) {
      parts.push(`Evidence includes ${presentTypes.join(', ')}`)
    }
  } else if (stars === 0) {
    parts.push('No qualifying evidence')
  }

  // Add cap explanation if present
  if (capMessage) {
    parts.push(capMessage)
  }

  // Add the explicit aggregation rule disclaimer
  parts.push('Rating reflects highest causal evidence present, not an average')

  return parts.join('. ') + '.'
}

/**
 * Format evidence mix for compact display (e.g., "1 SR/MA, 3 RCT, 2 Policy").
 */
export function formatEvidenceMixCompact(evidenceMix?: Record<string, number>): string {
  if (!evidenceMix || Object.keys(evidenceMix).length === 0) {
    return ''
  }

  // Order by evidence strength (highest first), including 'unknown' at the end
  const orderWithUnknown = [...EVIDENCE_TYPE_ORDER, 'unknown'] as const

  return orderWithUnknown
    .filter(key => evidenceMix[key] && evidenceMix[key] > 0)
    .map(key => `${evidenceMix[key]} ${getEvidenceMixDisplayName(key)}`)
    .join(', ')
}

// Legacy exports for backward compatibility (derived from categories)
// Now returns raw hex values for inline styles
export const EVIDENCE_CATEGORY_COLORS: Record<string, EvidenceCategoryColors> = Object.fromEntries(
  FALLBACK_CATEGORIES.map(c => [c.name, {
    bg: c.bg_color,
    text: c.text_color,
  }])
)

export const EVIDENCE_CATEGORY_SHORT_NAMES: Record<string, string> = Object.fromEntries(
  FALLBACK_CATEGORIES.map(c => [c.name, c.short_name])
)

export const EVIDENCE_TYPE_SHORT_NAMES: Record<string, string> = {
  'systematic_review': 'SR/MA',
  'rct': 'RCT',
  'observational': 'Observational',
  'modelling': 'Modelling',
  'policy': 'Policy',
  'qualitative': 'Qualitative',
  'opinion': 'Opinion',
  'unknown': 'Unknown',
}
