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

/**
 * Get evidence type keys in order of strength (strongest first).
 * Derived from backend categories, excluding 'other' and 'unknown'.
 */
function getEvidenceTypeOrder(): string[] {
  return getEvidenceCategories()
    .filter(c => c.key !== 'other' && c.key !== 'unknown')
    .map(c => c.key)
}

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
    const presentTypes = getEvidenceTypeOrder()
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
  const orderWithUnknown = [...getEvidenceTypeOrder(), 'unknown']

  return orderWithUnknown
    .filter(key => evidenceMix[key] && evidenceMix[key] > 0)
    .map(key => `${evidenceMix[key]} ${getEvidenceMixDisplayName(key)}`)
    .join(', ')
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

/**
 * Concise chatbot aliases used in the fast-screen evidence badges.
 * Must stay in sync with EVIDENCE_CATEGORY_CHATBOT_ALIASES in the backend
 * (backend/app/services/analysis/evidence/category.py).
 */
const CHATBOT_ALIAS_TO_SHORT_NAME: Record<string, string> = {
  'SR/MA': 'Systematic Review',
  'RCT': 'RCT/Quasi-Exp',
  'Obs.': 'Observational',
  'Modelling': 'Modelling',
  'Policy': 'Policy Guidance',
  'Qual.': 'Qualitative',
  'Opinion': 'Expert Opinion',
  'Other': 'Other',
  'Unknown': 'Unknown',
}

/**
 * Get a colour map for all evidence badge names (both canonical short names
 * and concise chatbot aliases).  Used by the ChatInterface to render
 * colour-coded evidence badges in markdown tables.
 */
export function getEvidenceBadgeColors(): Record<string, { bg: string; text: string }> {
  const colors: Record<string, { bg: string; text: string }> = {}
  const categories = getEvidenceCategories()

  // Register canonical short names
  for (const cat of categories) {
    colors[cat.short_name] = { bg: cat.bg_color, text: cat.text_color }
  }

  // Register concise chatbot aliases, falling back to hardcoded defaults
  // in case the canonical name lookup fails (e.g. data not yet fetched)
  const ALIAS_FALLBACKS: Record<string, { bg: string; text: string }> = {
    'SR/MA': { bg: '#0F294A', text: '#FFFFFF' },
    'RCT': { bg: '#9A1BBE', text: '#FFFFFF' },
    'Obs.': { bg: '#0000FF', text: '#FFFFFF' },
    'Policy': { bg: '#97D9E3', text: '#111827' },
    'Qual.': { bg: '#A59BEE', text: '#111827' },
    'Opinion': { bg: '#F6A4B7', text: '#111827' },
  }

  for (const [alias, shortName] of Object.entries(CHATBOT_ALIAS_TO_SHORT_NAME)) {
    colors[alias] = colors[shortName] ?? ALIAS_FALLBACKS[alias] ?? { bg: '#F3F4F6', text: '#374151' }
  }

  return colors
}

/**
 * Build a regex that matches evidence badge tokens like "SR/MA (2)" or "Policy (5)".
 * Uses the keys from getEvidenceBadgeColors() so it matches both canonical and alias names.
 */
export function buildEvidenceBadgeRegex(badgeNames: string[]): RegExp {
  const escaped = badgeNames.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  return new RegExp(`(${escaped.join('|')})\\s*\\((\\d+)\\)`, 'g')
}
