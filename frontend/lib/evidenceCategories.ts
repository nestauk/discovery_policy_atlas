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

export const POLICY_EVIDENCE_CATEGORIES = new Set([
  'Policy Syntheses & Guidance Documents',
  'Qualitative & Contextual Evidence',
  'Expert Opinion and Commentary',
])

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

export function isPolicyEvidenceCategory(category?: string): boolean {
  return !!category && POLICY_EVIDENCE_CATEGORIES.has(category)
}
