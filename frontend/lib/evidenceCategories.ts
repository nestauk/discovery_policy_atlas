/**
 * Evidence category utilities for display across the application.
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
 * Returns raw hex values for use with inline styles.
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
 * Get short display name for an evidence category, with fallback to full name.
 */
export function getEvidenceCategoryShortName(category: string): string {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.name === category)
  return found?.short_name || category
}

/**
 * Get rank for an evidence category (lower = stronger evidence).
 * Returns 999 for unknown categories.
 */
export function getEvidenceCategoryRank(category: string): number {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.name === category)
  return found?.rank || 999
}

/**
 * Get evidence categories excluding "Other" (non-evidence documents),
 * useful for display where we filter out non-evidence.
 */
export function getDisplayableCategories(): EvidenceCategory[] {
  return getEvidenceCategories().filter(c => c.key !== 'other')
}

// Legacy exports for backward compatibility
export const EVIDENCE_CATEGORY_SHORT_NAMES: Record<string, string> = Object.fromEntries(
  FALLBACK_CATEGORIES.map(c => [c.name, c.short_name])
)

/**
 * Color mapping using Tailwind classes (legacy).
 * Prefer getEvidenceCategoryColors() for new code.
 */
export const EVIDENCE_CATEGORY_COLORS: Record<string, EvidenceCategoryColors> = Object.fromEntries(
  FALLBACK_CATEGORIES.map(c => [c.name, { bg: `bg-[${c.bg_color}]`, text: c.text_color === '#FFFFFF' ? 'text-white' : 'text-gray-900' }])
)

/**
 * Get evidence mix display utilities.
 */
export function getEvidenceMixColors(key: string): EvidenceCategoryColors {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.key === key)
  if (found) {
    return { bg: found.bg_color, text: found.text_color }
  }
  return { bg: '#F3F4F6', text: '#374151' }
}

export function getEvidenceMixDisplayName(key: string): string {
  const categories = getEvidenceCategories()
  const found = categories.find(c => c.key === key)
  return found?.short_name || key
}
