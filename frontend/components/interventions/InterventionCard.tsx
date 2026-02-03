'use client'

import React from 'react'
import { TierBadge } from '@/components/ui/tier-badge'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { ExternalLink } from 'lucide-react'
import { getEvidenceCategoryColors, getEvidenceCategoryShortName } from '@/lib/evidenceCategories'

// Helper functions for impact score tooltip (matching PapersTable format)
function matchLabel(val: unknown): string {
  if (typeof val === 'string') return val
  if (typeof val === 'object' && val !== null && 'label' in val) {
    const l = (val as { label?: unknown }).label
    return typeof l === 'string' ? l : 'Unknown'
  }
  return 'Unknown'
}

function causalityStrengthLabel(weight: number): string {
  if (weight >= 0.9) return 'Strong'
  if (weight >= 0.7) return 'Moderate'
  if (weight >= 0.5) return 'Weak'
  return 'Very weak'
}

function fitLabel(score: number): string {
  if (score >= 0.8) return 'Good fit'
  if (score >= 0.6) return 'Moderate fit'
  if (score >= 0.4) return 'Partial fit'
  return 'Poor fit'
}

function outcomeMatchLabel(sim: number): string {
  if (sim >= 0.85) return 'Direct match'
  if (sim >= 0.75) return 'Proxy measure'
  if (sim >= 0.5) return 'Contributing factor'
  if (sim >= 0.2) return 'Weak link'
  return 'Unrelated'
}

function effectLabel(netMag: number): string {
  if (netMag >= 0.8) return 'Large positive'
  if (netMag >= 0.5) return 'Moderate positive'
  if (netMag >= 0.2) return 'Small positive'
  if (netMag <= -0.8) return 'Large negative'
  if (netMag <= -0.5) return 'Moderate negative'
  if (netMag <= -0.2) return 'Small negative'
  return 'Mixed/unclear'
}

function magnitudeLabel(mag: string | null | undefined): string {
  if (!mag) return 'unknown'
  const v = mag.toLowerCase()
  if (v === 'transformational') return 'substantial'
  if (v === 'substantial') return 'large'
  return v
}

type OutcomeDriver = {
  outcome: string
  netContribution: number
  avgSimilarity?: number | null
  magnitudeEstimate?: string | null
}

interface ResultSummary {
  outcome: string
  direction: string
  effect_size?: string
  effect_size_type?: string
  p_value?: string
  uncertainty?: string
  result_text?: string
  supporting_quote?: string
  population_measured?: string
  subgroup_or_dose?: string
}

interface SourceDocument {
  doc_id: string
  title: string
  source: string
  landing_page_url?: string
}

export interface InterventionCardData {
  name: string
  type?: string
  country?: string
  description?: string
  study_type?: string
  evidence_category?: string
  evidence_category_reasoning?: string
  sample_size?: number | string | null
  impact_score?: number
  evidence_score?: number
  impact_score_label?: string
  impact_score_breakdown?: Record<string, unknown> | null
  transferability_score?: number
  transferability_breakdown?: Record<string, unknown> | null
  impact_justification?: string
  supporting_quote?: string
  results_summary?: ResultSummary[]
  documents?: SourceDocument[]
  population_measured?: string
}

interface InterventionCardProps {
  intervention: InterventionCardData
  studyCount?: number
  showStudyLink?: boolean
}

function formatImpactScoreTooltip(intervention: InterventionCardData): React.ReactNode | undefined {
  const breakdown = intervention.impact_score_breakdown
  const tBreakdown = intervention.transferability_breakdown

  // If no breakdown data, fall back to simple justification text
  if (!breakdown && !tBreakdown && !intervention.impact_score_label) {
    return intervention.impact_justification || undefined
  }

  const b = (breakdown && typeof breakdown === 'object' ? (breakdown as Record<string, unknown>) : null)
  const tb = (tBreakdown && typeof tBreakdown === 'object' ? (tBreakdown as Record<string, unknown>) : null)

  const note = b && typeof b.note === 'string' ? b.note : null
  const netMag = b && typeof b.net_magnitude === 'number' ? b.net_magnitude : null
  const outcomesUsed = b && typeof b.outcomes_used === 'number' ? b.outcomes_used : null
  const avgCausalWeight = b && typeof b.avg_causal_weight === 'number' ? b.avg_causal_weight : null

  const geo = tb ? matchLabel(tb.geography) : 'Unknown'
  const pop = tb ? matchLabel(tb.population) : 'Unknown'
  const setting = tb ? matchLabel(tb.inner_setting) : 'Unknown'
  const constraintsProvided = tb ? tb.constraints_provided === true : false
  const exceedsConstraintsRaw = tb ? tb.exceeds_constraints : null
  const constraintLevelsRaw = tb ? tb.constraint_levels : null
  const implementationEvidenceRaw = tb ? tb.implementation_evidence : null
  const exceededConstraints =
    exceedsConstraintsRaw && typeof exceedsConstraintsRaw === 'object'
      ? Object.entries(exceedsConstraintsRaw as Record<string, unknown>)
          .filter(([, v]) => v === true)
          .map(([k]) => k)
      : []
  const constraintLevels =
    constraintLevelsRaw && typeof constraintLevelsRaw === 'object'
      ? (constraintLevelsRaw as Record<string, unknown>)
      : {}
  const implementationEvidence =
    implementationEvidenceRaw && typeof implementationEvidenceRaw === 'object'
      ? (implementationEvidenceRaw as Record<string, unknown>)
      : {}

  const transferability = typeof intervention.transferability_score === 'number' ? intervention.transferability_score : null

  let drivers: OutcomeDriver[] = []
  const outcomeBreakdown = b?.outcome_breakdown
  if (Array.isArray(outcomeBreakdown) && outcomeBreakdown.length > 0) {
    const grouped = new Map<
      string,
      { net: number; simSum: number; simCount: number; mag: string | null; magWeight: number }
    >()
    for (const item of outcomeBreakdown) {
      if (!item || typeof item !== 'object') continue
      const obj = item as Record<string, unknown>
      const outcome = typeof obj.outcome === 'string' ? obj.outcome : ''
      const contribution = typeof obj.contribution === 'number' ? obj.contribution : null
      const similarity = typeof obj.similarity === 'number' ? obj.similarity : null
      const magnitudeEstimate = typeof obj.magnitude === 'string' ? obj.magnitude : null
      if (!outcome || contribution == null) continue
      const existing =
        grouped.get(outcome) || { net: 0, simSum: 0, simCount: 0, mag: null, magWeight: 0 }
      existing.net += contribution
      if (similarity != null) {
        existing.simSum += similarity
        existing.simCount += 1
      }
      const absWeight = Math.abs(contribution)
      if (absWeight > existing.magWeight && magnitudeEstimate) {
        existing.mag = magnitudeEstimate
        existing.magWeight = absWeight
      }
      grouped.set(outcome, existing)
    }
    const hasTargetOutcomes = outcomeBreakdown.some((item) => {
      const obj = item as Record<string, unknown>
      const sim = typeof obj.similarity === 'number' ? obj.similarity : null
      return sim != null && sim < 0.999
    })

    drivers = Array.from(grouped.entries())
      .map(([outcome, meta]) => ({
        outcome,
        netContribution: meta.net,
        avgSimilarity: meta.simCount ? meta.simSum / meta.simCount : null,
        magnitudeEstimate: meta.mag,
      }))
      .sort((a, b) => {
        if (hasTargetOutcomes) {
          const simA = a.avgSimilarity ?? 0
          const simB = b.avgSimilarity ?? 0
          if (Math.abs(simA - simB) > 0.1) {
            return simB - simA
          }
        }
        return Math.abs(b.netContribution) - Math.abs(a.netContribution)
      })
      .slice(0, 2)
  }

  const bestMatch = (() => {
    if (!Array.isArray(outcomeBreakdown) || !outcomeBreakdown.length) return null
    let max = 0
    let causalWeight: number | null = null
    for (const item of outcomeBreakdown) {
      const obj = item as Record<string, unknown>
      const sim = typeof obj.similarity === 'number' ? obj.similarity : 0
      if (sim > max) {
        max = sim
        causalWeight = typeof obj.causal_weight === 'number' ? obj.causal_weight : null
      }
    }
    return max > 0 ? { similarity: max, causalWeight } : null
  })()

  const showOutcomeMatch = bestMatch != null && bestMatch.similarity < 0.999

  const filteredCausalAverage = (() => {
    if (!Array.isArray(outcomeBreakdown) || !outcomeBreakdown.length) return null
    let sum = 0
    let count = 0
    for (const item of outcomeBreakdown) {
      const obj = item as Record<string, unknown>
      const included = obj.included_in_score === true
      const causalWeight = typeof obj.causal_weight === 'number' ? obj.causal_weight : null
      if (included && causalWeight != null) {
        sum += causalWeight
        count += 1
      }
    }
    return count ? sum / count : null
  })()

  const headerLabel =
    typeof intervention.impact_score_label === 'string' && intervention.impact_score_label.trim()
      ? intervention.impact_score_label
      : 'Impact'

  return (
    <div className="space-y-2">
      <div className="font-medium">{headerLabel}</div>

      {note ? <div className="text-neutral-200">{note}</div> : null}

      <div className="space-y-1">
        {netMag != null ? (
          <div>
            <span className="font-medium">Net effect:</span> {effectLabel(netMag)}
          </div>
        ) : null}

        {(avgCausalWeight != null || filteredCausalAverage != null || bestMatch?.causalWeight != null) ? (
          <div>
            <span className="font-medium">Causality strength:</span>{' '}
            {causalityStrengthLabel(
              bestMatch?.causalWeight ??
                filteredCausalAverage ??
                avgCausalWeight ??
                0
            )}
          </div>
        ) : null}

        {transferability != null ? (
          <div>
            <span className="font-medium">Fit to your context:</span> {fitLabel(transferability)} ({geo} geography, {pop} population, {setting} setting)
          </div>
        ) : (
          <div>
            <span className="font-medium">Fit to your context:</span> Unknown ({geo} geography, {pop} population, {setting} setting)
          </div>
        )}

        {showOutcomeMatch && bestMatch != null ? (
          <div>
            <span className="font-medium">Outcome match:</span>{' '}
            {outcomeMatchLabel(bestMatch.similarity)}
          </div>
        ) : null}

        {constraintsProvided ? (
          <div>
            <span className="font-medium">Implementation constraints:</span>{' '}
            {(['cost', 'staffing', 'implementation_complexity'] as const)
              .filter((dim) => constraintLevels[dim])
              .map((dim) => {
                const rawValue = implementationEvidence[dim] as string | null | undefined
                const valueLabel = rawValue ? rawValue.toLowerCase() : 'unknown'
                const label = dim === 'implementation_complexity' ? 'complexity' : dim
                if (!rawValue) {
                  return `${label}: unknown`
                }
                const status = exceededConstraints.includes(dim) ? 'exceeds' : 'within'
                return `${label}: ${valueLabel} (${status})`
              })
              .join(', ') || 'Within your constraints'}
          </div>
        ) : null}

        {typeof outcomesUsed === 'number' ? (
          <div>
            <span className="font-medium">Primary outcomes:</span> {outcomesUsed}
          </div>
        ) : null}
      </div>

      {drivers.length ? (
        <div className="space-y-1">
          <div className="font-medium">Key outcomes</div>
          <ul className="list-disc pl-4 space-y-0.5">
            {drivers.map((d) => {
              const direction =
                d.netContribution > 0.12
                  ? 'positive'
                  : d.netContribution < -0.12
                  ? 'negative'
                  : 'mixed/unclear'
              const displayMag = magnitudeLabel(d.magnitudeEstimate)
              return (
                <li key={d.outcome}>
                  {d.outcome}: {direction} ({displayMag})
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function formatDirection(direction: string): string {
  const d = direction?.toLowerCase()
  if (d === 'increase') return 'increased'
  if (d === 'decrease') return 'decreased'
  if (d === 'no change' || d === 'null' || d === 'no_change') return 'showed no significant change in'
  return 'affected'
}

function formatEffectSize(effectSize: string, effectSizeType?: string): string {
  if (!effectSizeType) return effectSize
  
  // Special case for percentage: remove % from effect_size and use "percent" instead of "percentage"
  if (effectSizeType.toLowerCase() === 'percentage') {
    const cleanedSize = effectSize.replace(/%/g, '').trim()
    return `${cleanedSize} percent`
  }
  
  return `${effectSize} ${effectSizeType}`
}

function generateInterventionSentence(intervention: InterventionCardData): string {
  const parts: string[] = []
  
  if (intervention.description) {
    let desc = intervention.description.trim()
    if (desc.endsWith('.')) {
      desc = desc.slice(0, -1)
    }
    parts.push(desc)
  } else if (intervention.name) {
    parts.push(intervention.name)
  }
  
  // Only add country context - populations are handled in outcome sentences
  if (intervention.country && intervention.country !== 'Unknown' && intervention.country !== 'null') {
    parts.push(`in ${intervention.country}`)
  }
  
  let sentence = parts.join(' ')
  if (sentence && !sentence.endsWith('.')) {
    sentence += '.'
  }
  
  return sentence
}

function generateOutcomeSentence(results: ResultSummary[] | undefined): string {
  if (!results || results.length === 0) {
    return ''
  }
  
  const validResults = results.filter(r => 
    r.outcome && r.outcome !== 'null' && r.direction && r.direction !== 'null'
  )
  
  if (validResults.length === 0) {
    const firstWithText = results.find(r => r.result_text && r.result_text !== 'null')
    if (firstWithText?.result_text) {
      let text = firstWithText.result_text.trim()
      if (!text.endsWith('.')) text += '.'
      return text
    }
    return ''
  }
  
  // Check if all results share the same population (or no population)
  const uniquePopulations = new Set(
    validResults
      .map(r => r.population_measured)
      .filter(p => p && p !== 'null')
  )
  const hasMultiplePopulations = uniquePopulations.size > 1
  const singlePopulation = uniquePopulations.size === 1 ? Array.from(uniquePopulations)[0] : null
  
  if (validResults.length === 1) {
    const r = validResults[0]
    
    if (r.result_text && r.result_text !== 'null' && r.result_text.length < 200) {
      let text = r.result_text.trim()
      if (!text.endsWith('.')) text += '.'
      return text
    }
    
    const direction = formatDirection(r.direction)
    let sentence = `The intervention ${direction} ${r.outcome.toLowerCase()}`
    
    // Add population if present
    if (r.population_measured && r.population_measured !== 'null') {
      sentence += ` for ${r.population_measured}`
    }
    
    if (r.effect_size && r.effect_size !== 'null' && r.effect_size !== 'n/a') {
      const effectSizeText = formatEffectSize(r.effect_size, r.effect_size_type)
      sentence += ` (effect size: ${effectSizeText})`
    }
    
    if (r.p_value && r.p_value !== 'null' && r.p_value !== 'n/a') {
      sentence += `, p${r.p_value.startsWith('<') || r.p_value.startsWith('=') ? '' : '='}${r.p_value}`
    }
    
    sentence += '.'
    return sentence
  }
  
  // Multiple results - build descriptions with populations if they differ
  const outcomeDescriptions = validResults.slice(0, 3).map(r => {
    const direction = formatDirection(r.direction)
    let desc = `${direction} ${r.outcome.toLowerCase()}`
    
    // Include population for each outcome if populations differ across results
    if (hasMultiplePopulations && r.population_measured && r.population_measured !== 'null') {
      desc += ` (for ${r.population_measured})`
    }
    
    if (r.effect_size && r.effect_size !== 'null' && r.effect_size !== 'n/a') {
      const effectSizeText = formatEffectSize(r.effect_size, r.effect_size_type)
      desc += hasMultiplePopulations ? ` [${effectSizeText}]` : ` (${effectSizeText})`
    }
    return desc
  })
  
  let sentence: string
  if (outcomeDescriptions.length === 1) {
    sentence = `The intervention ${outcomeDescriptions[0]}`
  } else if (outcomeDescriptions.length === 2) {
    sentence = `The intervention ${outcomeDescriptions[0]} and ${outcomeDescriptions[1]}`
  } else {
    const lastOutcome = outcomeDescriptions.pop()
    sentence = `The intervention ${outcomeDescriptions.join(', ')}, and ${lastOutcome}`
  }
  
  // Add shared population at the end if all outcomes share the same population
  if (singlePopulation && !hasMultiplePopulations) {
    sentence += ` for ${singlePopulation}`
  }
  
  sentence += '.'
  return sentence
}

// Generate outcome sentence as JSX with bold outcomes
function generateOutcomeElements(results: ResultSummary[] | undefined): React.ReactNode {
  if (!results || results.length === 0) {
    return null
  }
  
  const validResults = results.filter(r => 
    r.outcome && r.outcome !== 'null' && r.direction && r.direction !== 'null'
  )
  
  if (validResults.length === 0) {
    const firstWithText = results.find(r => r.result_text && r.result_text !== 'null')
    if (firstWithText?.result_text) {
      let text = firstWithText.result_text.trim()
      if (!text.endsWith('.')) text += '.'
      return text
    }
    return null
  }
  
  // Check if all results share the same population (or no population)
  const uniquePopulations = new Set(
    validResults
      .map(r => r.population_measured)
      .filter(p => p && p !== 'null')
  )
  const hasMultiplePopulations = uniquePopulations.size > 1
  const singlePopulation = uniquePopulations.size === 1 ? Array.from(uniquePopulations)[0] : null
  
  if (validResults.length === 1) {
    const r = validResults[0]
    
    if (r.result_text && r.result_text !== 'null' && r.result_text.length < 200) {
      let text = r.result_text.trim()
      if (!text.endsWith('.')) text += '.'
      return text
    }
    
    const direction = formatDirection(r.direction)
    const parts: React.ReactNode[] = []
    parts.push(`The intervention ${direction} `)
    parts.push(<strong key="outcome">{r.outcome.toLowerCase()}</strong>)
    
    if (r.population_measured && r.population_measured !== 'null') {
      parts.push(` for ${r.population_measured}`)
    }
    
    if (r.effect_size && r.effect_size !== 'null' && r.effect_size !== 'n/a') {
      const effectSizeText = formatEffectSize(r.effect_size, r.effect_size_type)
      parts.push(` (effect size: ${effectSizeText})`)
    }
    
    if (r.p_value && r.p_value !== 'null' && r.p_value !== 'n/a') {
      parts.push(`, p${r.p_value.startsWith('<') || r.p_value.startsWith('=') ? '' : '='}${r.p_value}`)
    }
    
    parts.push('.')
    return <>{parts}</>
  }
  
  // Multiple results - build with bold outcomes
  const parts: React.ReactNode[] = ['The intervention ']
  
  validResults.slice(0, 3).forEach((r, index, arr) => {
    const direction = formatDirection(r.direction)
    const isLast = index === arr.length - 1
    const isSecondToLast = index === arr.length - 2
    
    parts.push(`${direction} `)
    parts.push(<strong key={`outcome-${index}`}>{r.outcome.toLowerCase()}</strong>)
    
    if (hasMultiplePopulations && r.population_measured && r.population_measured !== 'null') {
      parts.push(` (for ${r.population_measured})`)
    }
    
    if (r.effect_size && r.effect_size !== 'null' && r.effect_size !== 'n/a') {
      const effectSizeText = formatEffectSize(r.effect_size, r.effect_size_type)
      parts.push(hasMultiplePopulations ? ` [${effectSizeText}]` : ` (${effectSizeText})`)
    }
    
    if (!isLast) {
      if (arr.length === 2) {
        parts.push(' and ')
      } else if (isSecondToLast) {
        parts.push(', and ')
      } else {
        parts.push(', ')
      }
    }
  })
  
  if (singlePopulation && !hasMultiplePopulations) {
    parts.push(` for ${singlePopulation}`)
  }
  
  parts.push('.')
  return <>{parts}</>
}

function getStudyCitation(documents: SourceDocument[] | undefined): string {
  if (!documents || documents.length === 0) return ''
  
  const doc = documents[0]
  if (!doc.title) return doc.source || ''
  
  const yearMatch = doc.title.match(/\((\d{4})\)/)
  if (yearMatch) {
    const beforeYear = doc.title.substring(0, doc.title.indexOf(yearMatch[0])).trim()
    const lastComma = beforeYear.lastIndexOf(',')
    const authorPart = lastComma > 0 ? beforeYear.substring(0, lastComma) : beforeYear
    
    const authors = authorPart.split(/,|&|and/).map(a => a.trim()).filter(Boolean)
    if (authors.length > 0) {
      const firstAuthor = authors[0].split(' ').pop()
      if (authors.length === 1) {
        return `${firstAuthor} (${yearMatch[1]})`
      } else if (authors.length === 2) {
        const secondAuthor = authors[1].split(' ').pop()
        return `${firstAuthor} & ${secondAuthor} (${yearMatch[1]})`
      } else {
        return `${firstAuthor} et al. (${yearMatch[1]})`
      }
    }
  }
  
  if (doc.title.length > 50) {
    return doc.title.substring(0, 47) + '...'
  }
  return doc.title
}

export function InterventionCard({ 
  intervention, 
  studyCount: _studyCount = 1,
  showStudyLink = true 
}: InterventionCardProps) {
  const interventionSentence = generateInterventionSentence(intervention)
  const outcomeElements = generateOutcomeElements(intervention.results_summary)
  
  const primaryDoc = intervention.documents?.[0]
  const studyTitle = primaryDoc?.title || ''
  
  const hasMetadata = (intervention.country && intervention.country !== 'Unknown' && intervention.country !== 'null') || 
    intervention.sample_size

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5 hover:border-gray-200 transition-colors">
      {/* Intervention type at the top */}
      {intervention.type && intervention.type !== 'Unknown' && (
        <div className="mb-2">
          <Badge 
            variant="outline" 
            className="text-xs font-medium uppercase tracking-wide text-gray-500 bg-gray-50"
          >
            {intervention.type}
          </Badge>
        </div>
      )}

      <div className="flex justify-between items-start gap-4 mb-3">
        <h3 className="text-base font-semibold text-gray-900 leading-snug min-w-0">
          {intervention.name}
        </h3>
        
        <div className="shrink-0 flex items-center gap-3">
          {intervention.impact_score != null && (() => {
            const tooltip = formatImpactScoreTooltip(intervention)
            return tooltip ? (
              <Tooltip content={tooltip}>
                <span className="cursor-help">
                  <TierBadge score={intervention.impact_score} label="Impact" />
                </span>
              </Tooltip>
            ) : (
              <TierBadge score={intervention.impact_score} label="Impact" />
            )
          })()}
          {intervention.evidence_category && (() => {
            const colors = getEvidenceCategoryColors(intervention.evidence_category)
            // Build tooltip: category name + reasoning (if available) - same as documents table
            const tooltipContent = intervention.evidence_category_reasoning
              ? `${intervention.evidence_category}\n\n${intervention.evidence_category_reasoning}`
              : intervention.evidence_category
            return (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500">Evidence:</span>
                <Tooltip content={tooltipContent}>
                  <span 
                    className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium cursor-help"
                    style={{ backgroundColor: colors.bg, color: colors.text }}
                  >
                    {getEvidenceCategoryShortName(intervention.evidence_category)}
                  </span>
                </Tooltip>
              </div>
            )
          })()}
        </div>
      </div>

      {/* Metadata: Country, Sample Size */}
      {hasMetadata && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm mb-3">
          {intervention.country && intervention.country !== 'Unknown' && intervention.country !== 'null' && (
            <span className="text-gray-600">{intervention.country}</span>
          )}
          {intervention.sample_size && (
            <span className="text-gray-600">n={typeof intervention.sample_size === 'number' ? intervention.sample_size.toLocaleString() : intervention.sample_size}</span>
          )}
        </div>
      )}
      
      <div className="space-y-2 text-gray-700 leading-relaxed">
        {interventionSentence && (
          <p>{interventionSentence}</p>
        )}
        {outcomeElements && (
          <p>{outcomeElements}</p>
        )}
        {/* Supporting quote - check intervention level first, then results */}
        {(() => {
          // First check for quote at the intervention level (common for systematic reviews)
          let quote = intervention.supporting_quote?.trim()
          // If not found, look in results
          if (!quote) {
            quote = intervention.results_summary?.find(r => r.supporting_quote && r.supporting_quote.trim())?.supporting_quote
          }
          if (!quote) return null
          return (
            <blockquote className="border-l-2 border-gray-300 pl-3 italic text-gray-600 text-sm">
              &ldquo;{quote}&rdquo;
            </blockquote>
          )
        })()}
      </div>
      
      {showStudyLink && primaryDoc?.landing_page_url && studyTitle && (
        <a
          href={primaryDoc.landing_page_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 hover:underline"
        >
          {studyTitle.length > 80 ? studyTitle.substring(0, 77) + '...' : studyTitle}
          <ExternalLink size={14} className="shrink-0" />
        </a>
      )}
    </div>
  )
}

export { generateInterventionSentence, generateOutcomeSentence, getStudyCitation }

