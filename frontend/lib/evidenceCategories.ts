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
 * Evidence category scores (0-5) based on evidence strength methodology.
 * Individual documents get their star rating from their evidence category.
 */
export const EVIDENCE_CATEGORY_SCORES: Record<string, number> = {
  'Systematic Review and Meta-Analysis': 5,
  'RCTs and Quasi-Experimental Studies': 4,
  'Observational Research Studies': 3,
  'Modelling & Simulation': 2,
  'Policy Syntheses & Guidance Documents': 2,
  'Qualitative & Contextual Evidence': 2,
  'Expert Opinion and Commentary': 1,
  'Other (Non-evidence documents)': 0,
  'Unknown / Insufficient information': 0,
}

/**
 * Get the star rating (0-5) for an evidence category.
 */
export function getEvidenceCategoryScore(category: string | null | undefined): number | null {
  if (!category) return null
  return EVIDENCE_CATEGORY_SCORES[category] ?? null
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
 * Very short names for evidence mix display (used in intervention star ratings).
 * These match the keys returned from the backend evidence_mix field.
 */
export const EVIDENCE_MIX_DISPLAY_NAMES: Record<string, string> = {
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
 * Colors for evidence mix display (matching the evidence category colors by type).
 */
export const EVIDENCE_MIX_COLORS: Record<string, EvidenceCategoryColors> = {
  'systematic_review': { bg: 'bg-[#0F294A]', text: 'text-white' },
  'rct': { bg: 'bg-[#9A1BBE]', text: 'text-white' },
  'observational': { bg: 'bg-[#0000FF]', text: 'text-white' },
  'modelling': { bg: 'bg-[#18A48C]', text: 'text-white' },
  'policy': { bg: 'bg-[#97D9E3]', text: 'text-gray-900' },
  'qualitative': { bg: 'bg-[#A59BEE]', text: 'text-gray-900' },
  'opinion': { bg: 'bg-[#F6A4B7]', text: 'text-gray-900' },
  'unknown': { bg: 'bg-[#f8f5f4]', text: 'text-gray-700' },
}

/**
 * Get display name for an evidence mix key.
 */
export function getEvidenceMixDisplayName(key: string): string {
  return EVIDENCE_MIX_DISPLAY_NAMES[key] || key
}

/**
 * Get colors for an evidence mix key.
 */
export function getEvidenceMixColors(key: string): EvidenceCategoryColors {
  return EVIDENCE_MIX_COLORS[key] || { bg: 'bg-gray-100', text: 'text-gray-700' }
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

/**
 * Short names for evidence mix compact display.
 */
const EVIDENCE_TYPE_SHORT_NAMES: Record<string, string> = {
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
    const presentTypes: string[] = []

    // Check what's actually present (in order of strength)
    if (evidenceMix['systematic_review'] && evidenceMix['systematic_review'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['systematic_review'])
    }
    if (evidenceMix['rct'] && evidenceMix['rct'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['rct'])
    }
    if (evidenceMix['observational'] && evidenceMix['observational'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['observational'])
    }
    if (evidenceMix['modelling'] && evidenceMix['modelling'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['modelling'])
    }
    if (evidenceMix['policy'] && evidenceMix['policy'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['policy'])
    }
    if (evidenceMix['qualitative'] && evidenceMix['qualitative'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['qualitative'])
    }
    if (evidenceMix['opinion'] && evidenceMix['opinion'] > 0) {
      presentTypes.push(EVIDENCE_TYPE_FULL_NAMES['opinion'])
    }

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

  // Order by evidence strength (highest first)
  const order = ['systematic_review', 'rct', 'observational', 'modelling', 'policy', 'qualitative', 'opinion', 'unknown']

  return order
    .filter(key => evidenceMix[key] && evidenceMix[key] > 0)
    .map(key => `${evidenceMix[key]} ${EVIDENCE_TYPE_SHORT_NAMES[key]}`)
    .join(', ')
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
