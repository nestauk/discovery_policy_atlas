/**
 * Shared utilities for evidence category display across intervention tables.
 *
 * This file centralizes evidence category color mapping and display names
 * to ensure consistency between InterventionsTable and NavigatorInterventionsTable.
 */

export interface EvidenceCategoryColors {
  bg: string
  text: string
}

/**
 * Color coding by evidence strength, matching the Documents tab styling.
 */
export const EVIDENCE_CATEGORY_COLORS: Record<string, EvidenceCategoryColors> = {
  'Systematic Review and Meta-Analysis': { bg: 'bg-[#0F294A]', text: 'text-white' },
  'RCTs and Quasi-Experimental Studies': { bg: 'bg-[#9A1BBE]', text: 'text-white' },
  'Observational Research Studies': { bg: 'bg-[#0000FF]', text: 'text-white' },
  'Modelling & Simulation': { bg: 'bg-[#18A48C]', text: 'text-white' },
  'Policy Syntheses & Guidance Documents': { bg: 'bg-[#97D9E3]', text: 'text-gray-900' },
  'Qualitative & Contextual Evidence': { bg: 'bg-[#A59BEE]', text: 'text-gray-900' },
  'Expert Opinion and Commentary': { bg: 'bg-[#F6A4B7]', text: 'text-gray-900' },
  'Unknown / Insufficient information': { bg: 'bg-[#f8f5f4]', text: 'text-gray-700' },
}

/**
 * Short display names for evidence categories (used in compact table views).
 */
export const EVIDENCE_CATEGORY_SHORT_NAMES: Record<string, string> = {
  'Systematic Review and Meta-Analysis': 'Systematic Review',
  'RCTs and Quasi-Experimental Studies': 'RCT/Quasi-Exp',
  'Observational Research Studies': 'Observational',
  'Modelling & Simulation': 'Modelling',
  'Policy Syntheses & Guidance Documents': 'Policy Guidance',
  'Qualitative & Contextual Evidence': 'Qualitative',
  'Expert Opinion and Commentary': 'Expert Opinion',
  'Unknown / Insufficient information': 'Unknown',
}

/**
 * Map full evidence category names to short keys for counting.
 */
const EVIDENCE_CATEGORY_TO_KEY: Record<string, string> = {
  'Systematic Review and Meta-Analysis': 'systematic_review',
  'RCTs and Quasi-Experimental Studies': 'rct',
  'Observational Research Studies': 'observational',
  'Modelling & Simulation': 'modelling',
  'Policy Syntheses & Guidance Documents': 'policy',
  'Qualitative & Contextual Evidence': 'qualitative',
  'Expert Opinion and Commentary': 'opinion',
  'Unknown / Insufficient information': 'unknown',
}

/**
 * Maps short keys to full category names (inverse of EVIDENCE_CATEGORY_TO_KEY).
 */
const KEY_TO_EVIDENCE_CATEGORY = Object.fromEntries(
  Object.entries(EVIDENCE_CATEGORY_TO_KEY).map(([category, key]) => [key, category])
) as Record<string, string>

/**
 * Short names for evidence types (used in evidence mix display and explanations).
 * These match the keys returned from the backend evidence_mix field.
 */
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

/**
 * Get display name for an evidence mix key.
 */
export function getEvidenceMixDisplayName(key: string): string {
  return EVIDENCE_TYPE_SHORT_NAMES[key] || key
}

/**
 * Get colors for an evidence mix key (derived from category colors).
 */
export function getEvidenceMixColors(key: string): EvidenceCategoryColors {
  const fullCategory = KEY_TO_EVIDENCE_CATEGORY[key]
  return fullCategory
    ? getEvidenceCategoryColors(fullCategory)
    : { bg: 'bg-gray-100', text: 'text-gray-700' }
}

/**
 * Get colors for an evidence category, with fallback for unknown categories.
 */
export function getEvidenceCategoryColors(category: string): EvidenceCategoryColors {
  return EVIDENCE_CATEGORY_COLORS[category] || { bg: 'bg-gray-100', text: 'text-gray-700' }
}

/**
 * Get short display name for an evidence category, with fallback to full name.
 */
export function getEvidenceCategoryShortName(category: string): string {
  return EVIDENCE_CATEGORY_SHORT_NAMES[category] || category
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
    .map(key => `${evidenceMix[key]} ${EVIDENCE_TYPE_SHORT_NAMES[key]}`)
    .join(', ')
}

/**
 * Compute evidence mix from detailed interventions, counting unique documents only.
 * Deduplicates by doc_id to avoid counting the same document multiple times
 * when it has multiple interventions.
 */
export function computeEvidenceMixFromInterventions(
  detailedInterventions?: Array<{
    evidence_category?: string
    source_documents?: Array<{ doc_id?: string }>
  }>
): Record<string, number> {
  if (!detailedInterventions || detailedInterventions.length === 0) {
    return {}
  }

  // Track unique documents by doc_id
  const seenDocIds = new Set<string>()
  const counts: Record<string, number> = {}

  for (const intervention of detailedInterventions) {
    // Get doc_id from source_documents (typically first entry)
    const docId = intervention.source_documents?.[0]?.doc_id
    if (!docId || seenDocIds.has(docId)) {
      continue // Skip if no doc_id or already counted
    }

    seenDocIds.add(docId)

    // Count by evidence category
    const category = intervention.evidence_category
    if (category) {
      const key = EVIDENCE_CATEGORY_TO_KEY[category] || 'unknown'
      counts[key] = (counts[key] || 0) + 1
    }
  }

  return counts
}
