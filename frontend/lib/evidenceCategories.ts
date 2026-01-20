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
 * Evidence type configuration - single source of truth for all evidence-related mappings.
 * Each entry contains: short key, full category name, short display name, full name for explanations, and colors.
 */
interface EvidenceTypeConfig {
  key: string           // Short key used in evidence_mix (e.g., 'systematic_review')
  category: string      // Full category name from backend (e.g., 'Systematic Review and Meta-Analysis')
  shortName: string     // Short display name for tables (e.g., 'SR/MA')
  tableName: string     // Name for category badges in tables (e.g., 'Systematic Review')
  fullName: string      // Full name for explanations (e.g., 'systematic reviews/meta-analyses')
  colors: EvidenceCategoryColors
}

const EVIDENCE_TYPES: EvidenceTypeConfig[] = [
  {
    key: 'systematic_review',
    category: 'Systematic Review and Meta-Analysis',
    shortName: 'SR/MA',
    tableName: 'Systematic Review',
    fullName: 'systematic reviews/meta-analyses',
    colors: { bg: 'bg-[#0F294A]', text: 'text-white' },
  },
  {
    key: 'rct',
    category: 'RCTs and Quasi-Experimental Studies',
    shortName: 'RCT',
    tableName: 'RCT/Quasi-Exp',
    fullName: 'RCTs/quasi-experimental studies',
    colors: { bg: 'bg-[#9A1BBE]', text: 'text-white' },
  },
  {
    key: 'observational',
    category: 'Observational Research Studies',
    shortName: 'Observational',
    tableName: 'Observational',
    fullName: 'observational studies',
    colors: { bg: 'bg-[#0000FF]', text: 'text-white' },
  },
  {
    key: 'modelling',
    category: 'Modelling & Simulation',
    shortName: 'Modelling',
    tableName: 'Modelling',
    fullName: 'modelling/simulation studies',
    colors: { bg: 'bg-[#18A48C]', text: 'text-white' },
  },
  {
    key: 'policy',
    category: 'Policy Syntheses & Guidance Documents',
    shortName: 'Policy',
    tableName: 'Policy Guidance',
    fullName: 'policy syntheses',
    colors: { bg: 'bg-[#97D9E3]', text: 'text-gray-900' },
  },
  {
    key: 'qualitative',
    category: 'Qualitative & Contextual Evidence',
    shortName: 'Qualitative',
    tableName: 'Qualitative',
    fullName: 'qualitative evidence',
    colors: { bg: 'bg-[#A59BEE]', text: 'text-gray-900' },
  },
  {
    key: 'opinion',
    category: 'Expert Opinion and Commentary',
    shortName: 'Opinion',
    tableName: 'Expert Opinion',
    fullName: 'expert opinion',
    colors: { bg: 'bg-[#F6A4B7]', text: 'text-gray-900' },
  },
  {
    key: 'unknown',
    category: 'Unknown / Insufficient information',
    shortName: 'Unknown',
    tableName: 'Unknown',
    fullName: 'unclassified evidence',
    colors: { bg: 'bg-[#f8f5f4]', text: 'text-gray-700' },
  },
]

const DEFAULT_COLORS: EvidenceCategoryColors = { bg: 'bg-gray-100', text: 'text-gray-700' }

// Derived lookups (computed once at module load)
const byCategory = new Map(EVIDENCE_TYPES.map(t => [t.category, t]))
const byKey = new Map(EVIDENCE_TYPES.map(t => [t.key, t]))

/** Evidence types in order of strength (strongest first, excluding unknown) */
const EVIDENCE_TYPE_ORDER = EVIDENCE_TYPES.filter(t => t.key !== 'unknown').map(t => t.key)

// Legacy exports for backward compatibility
export const EVIDENCE_CATEGORY_COLORS: Record<string, EvidenceCategoryColors> =
  Object.fromEntries(EVIDENCE_TYPES.map(t => [t.category, t.colors]))

export const EVIDENCE_CATEGORY_SHORT_NAMES: Record<string, string> =
  Object.fromEntries(EVIDENCE_TYPES.map(t => [t.category, t.tableName]))

export const EVIDENCE_TYPE_SHORT_NAMES: Record<string, string> =
  Object.fromEntries(EVIDENCE_TYPES.map(t => [t.key, t.shortName]))

export const EVIDENCE_MIX_COLORS: Record<string, EvidenceCategoryColors> =
  Object.fromEntries(EVIDENCE_TYPES.map(t => [t.key, t.colors]))

/** @deprecated Use EVIDENCE_TYPE_SHORT_NAMES instead */
export const EVIDENCE_MIX_DISPLAY_NAMES = EVIDENCE_TYPE_SHORT_NAMES

/**
 * Get display name for an evidence mix key.
 */
export function getEvidenceMixDisplayName(key: string): string {
  return byKey.get(key)?.shortName || key
}

/**
 * Get colors for an evidence mix key.
 */
export function getEvidenceMixColors(key: string): EvidenceCategoryColors {
  return byKey.get(key)?.colors || DEFAULT_COLORS
}

/**
 * Get colors for an evidence category, with fallback for unknown categories.
 */
export function getEvidenceCategoryColors(category: string): EvidenceCategoryColors {
  return byCategory.get(category)?.colors || DEFAULT_COLORS
}

/**
 * Get short display name for an evidence category, with fallback to full name.
 */
export function getEvidenceCategoryShortName(category: string): string {
  return byCategory.get(category)?.tableName || category
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

  if (evidenceMix && Object.keys(evidenceMix).length > 0) {
    const presentTypes = EVIDENCE_TYPE_ORDER
      .filter(key => evidenceMix[key] && evidenceMix[key] > 0)
      .map(key => byKey.get(key)?.fullName || key)

    if (presentTypes.length > 0) {
      parts.push(`Evidence includes ${presentTypes.join(', ')}`)
    }
  } else if (stars === 0) {
    parts.push('No qualifying evidence')
  }

  if (capMessage) {
    parts.push(capMessage)
  }

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

  const orderWithUnknown = [...EVIDENCE_TYPE_ORDER, 'unknown']

  return orderWithUnknown
    .filter(key => evidenceMix[key] && evidenceMix[key] > 0)
    .map(key => `${evidenceMix[key]} ${byKey.get(key)?.shortName || key}`)
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

  const seenDocIds = new Set<string>()
  const counts: Record<string, number> = {}

  for (const intervention of detailedInterventions) {
    const docId = intervention.source_documents?.[0]?.doc_id
    if (!docId || seenDocIds.has(docId)) {
      continue
    }

    seenDocIds.add(docId)

    const category = intervention.evidence_category
    if (category) {
      const key = byCategory.get(category)?.key || 'unknown'
      counts[key] = (counts[key] || 0) + 1
    }
  }

  return counts
}
