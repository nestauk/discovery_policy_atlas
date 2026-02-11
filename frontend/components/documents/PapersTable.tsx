'use client'

import { useMemo } from 'react'
import { Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Paper } from '@/types/search'
import { Check, X } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { StarRating } from '@/components/ui/star-rating'
import { getEvidenceCategoryColors, getEvidenceCategoryShortName } from '@/lib/evidenceCategories'

interface PapersTableProps {
  papers: Paper[]
  showAdditionalColumns?: boolean
  highlightNonRelevant?: boolean
}

interface DataType extends Paper {
  key: string
  authorsDisplay: string
  topicsDisplay: string
  relevanceDisplay: string
}

export function PapersTable({ papers, showAdditionalColumns = false, highlightNonRelevant = false }: PapersTableProps) {
  // Transform papers data for the table
  const tableData: DataType[] = useMemo(() => {
    return papers.map((paper) => ({
      ...paper,
      key: paper.id,
      authorsDisplay: paper.authors?.join(', ') || 'Unknown',
      topicsDisplay: paper.topics?.slice(0, 2).join(', ') + (paper.topics && paper.topics.length > 2 ? ` +${paper.topics.length - 2} more` : ''),
      relevanceDisplay: paper.is_relevant ? 'Relevant' : 'Not Relevant'
    }))
  }, [papers])

  // Get extracted fields from the first paper (assuming all papers have the same extraction fields)
  const extractedFields = useMemo(() => {
    if (!papers.length) return []
    
    const firstPaper = papers[0]
    const fields = Object.keys(firstPaper).filter(key => 
      key.startsWith('extra_field_') && firstPaper[key as keyof Paper]
    )
    
    return fields.map((field, index) => ({
      key: field,
      title: `Extra Field ${index + 1}`,
      dataIndex: field,
      width: '10%',
      sorter: (a: DataType, b: DataType) => {
        const aValue = String(a[field as keyof DataType] || 'N/A')
        const bValue = String(b[field as keyof DataType] || 'N/A')
        return aValue.localeCompare(bValue)
      },
      render: (text: string, record: DataType) => (
        <div className="text-sm text-gray-700 whitespace-normal leading-tight" title={String(record[field as keyof DataType] || '')}>
          {String(record[field as keyof DataType] || 'N/A')}
        </div>
      ),
    }))
  }, [papers])

  // Build columns conditionally
  const baseColumns: ColumnsType<DataType> = [
    {
      title: 'Year',
      dataIndex: 'publication_year',
      key: 'publication_year',
      width: '6%',
      sorter: (a, b) => a.publication_year - b.publication_year,
      render: (text) => (
        <span>{text && text > 0 ? text : 'Unknown'}</span>
      ),
    },
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      width: '20%',
      render: (text, record) => {
        const maxLength = 80 // Truncate after 80 characters for titles
        // Prioritize landing_page_url, fallback to DOI, then overton_url
        const linkUrl = record.landing_page_url || (record.doi ? `${record.doi}` : record.overton_url)
        
        return linkUrl ? (
          <a 
            href={linkUrl} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 hover:underline"
            title={text} // Show full title on hover
          >
            {text.length > maxLength 
              ? `${text.substring(0, maxLength)}...` 
              : text
            }
          </a>
        ) : (
          <span title={text}>
            {text.length > maxLength 
              ? `${text.substring(0, maxLength)}...` 
              : text
            }
          </span>
        )
      },
      sorter: (a, b) => a.title.localeCompare(b.title),
    },
    {
      title: 'Top Line',
      dataIndex: 'top_line',
      key: 'top_line',
      width: '20%',
      render: (text, record) => (
        <div className="text-sm text-gray-700 whitespace-normal leading-tight">
          {record.top_line || 'No summary available'}
        </div>
      ),
    },
    {
      title: 'Country',
      dataIndex: 'source_country',
      key: 'source_country',
      width: '8%',
      sorter: (a, b) => (a.source_country || 'Academic').localeCompare(b.source_country || 'Academic'),
      render: (text) => (
        <span>{text || 'Academic'}</span>
      ),
    },
    {
      title: 'Authors',
      dataIndex: 'authorsDisplay',
      key: 'authors',
      width: '12%',
      sorter: (a, b) => a.authorsDisplay.localeCompare(b.authorsDisplay),
      render: (text, record) => {
        const authorsText = record.authors?.join(', ') || 'Unknown'
        const maxLength = 60 // Truncate after 60 characters
        
        return (
          <div className="text-sm text-gray-700 whitespace-normal leading-tight" title={authorsText}>
            {authorsText.length > maxLength 
              ? `${authorsText.substring(0, maxLength)}...` 
              : authorsText
            }
          </div>
        )
      },
    },
    {
      title: 'Citations',
      dataIndex: 'cited_by_count',
      key: 'cited_by_count',
      width: '6%',
      sorter: (a, b) => a.cited_by_count - b.cited_by_count,
      render: (text) => (
        <span className={text > 100 ? 'text-green-600 font-semibold' : ''}>
          {text}
        </span>
      ),
    },
    {
      title: 'Evidence Category',
      dataIndex: 'evidence_category',
      key: 'evidence_category_base',
      width: '10%',
      defaultSortOrder: 'ascend',
      sorter: (a, b) => {
        const aRank = a.evidence_category_rank ?? 999
        const bRank = b.evidence_category_rank ?? 999
        return aRank - bRank
      },
      render: (_text, record) => {
        const category = record.evidence_category
        if (!category) {
          return <span className="text-gray-400 text-xs">-</span>
        }
        const colors = getEvidenceCategoryColors(category)
        const displayName = getEvidenceCategoryShortName(category)
        // Build tooltip: category name + reasoning (if available)
        const tooltipContent = record.evidence_category_reasoning
          ? `${category}\n\n${record.evidence_category_reasoning}`
          : category
        return (
          <Tooltip content={tooltipContent}>
            <span
              className="inline-block px-2 py-1 rounded text-xs font-medium cursor-help whitespace-normal leading-tight"
              style={{ backgroundColor: colors.bg, color: colors.text }}
            >
              {displayName}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: 'Evidence Strength',
      dataIndex: 'evidence_category',
      key: 'evidence_strength',
      width: '10%',
      sorter: (a, b) => (a.evidence_strength ?? 0) - (b.evidence_strength ?? 0),
      render: (_text, record) => {
        const score = record.evidence_strength
        const displayScore = score === 0 ? null : score ?? null
        const tooltip = record.evidence_strength_justification
        return (
          <StarRating
            stars={displayScore}
            size="sm"
            tooltip={tooltip}
          />
        )
      },
    },
    {
      title: 'Impact Score',
      dataIndex: 'impact_score',
      key: 'impact_score',
      width: '10%',
      sorter: (a, b) => (a.impact_score ?? 0) - (b.impact_score ?? 0),
      render: (text, record) => {
        const tooltip = formatImpactScoreTooltip(record)
        return (
          <StarRating
            stars={record.impact_score}
            size="sm"
            tooltip={tooltip}
          />
        )
      },
    },
    {
      title: 'Relevance',
      dataIndex: 'confidence',
      key: 'confidence',
      width: '8%',
      sorter: (a, b) => (a.confidence || 0) - (b.confidence || 0),
      defaultSortOrder: 'descend',
      render: (text, record) => {
        const relevanceContent = (
          <div className="flex items-center gap-1">
            <span>{record.confidence ? (record.confidence * 100).toFixed(1) : 'N/A'}</span>
            {record.is_relevant ? (
              <Check className="h-3 w-3 text-green-600" />
            ) : (
              <X className="h-3 w-3 text-red-500" />
            )}
          </div>
        )

        // Show tooltip with relevance_reason if available
        if (record.relevance_reason) {
          return (
            <Tooltip content={record.relevance_reason}>
              <div className="cursor-help">
                {relevanceContent}
              </div>
            </Tooltip>
          )
        }

        return relevanceContent
      },
    },
  ];

  const showCalcDetails =
    process.env.NEXT_PUBLIC_SHOW_IMPACT_SCORE_DETAILS === 'true'

  type OutcomeDriver = {
    outcome: string
    netContribution: number
    avgSimilarity: number | null
    magnitudeEstimate: string | null
  }

  const effectLabel = (netMag: number): string => {
    const abs = Math.abs(netMag)
    const strength =
      abs >= 0.66
        ? 'substantial'
        : abs >= 0.5
          ? 'large'
          : abs >= 0.33
            ? 'moderate'
            : abs >= 0.12
              ? 'marginal'
              : 'no clear'

    if (abs < 0.12) return 'Mixed / no clear effect'
    if (netMag > 0) return `${strength} positive effect`
    return `${strength} negative effect`
  }

  const fitLabel = (t: number): string => {
    if (t >= 0.75) return 'Good fit'
    if (t >= 0.5) return 'Moderate fit'
    return 'Limited fit'
  }

  const causalityStrengthLabel = (avg: number): string => {
    if (avg >= 0.95) return 'Strong'
    if (avg >= 0.85) return 'Moderate'
    return 'Weak'
  }

  const matchLabel = (value: unknown): string => {
    if (typeof value !== 'string' || !value.trim()) return 'Unknown'
    const v = value.trim().toLowerCase()
    if (v === 'match') return 'Match'
    if (v === 'similar') return 'Similar'
    if (v === 'comparable') return 'Comparable'
    if (v === 'partial') return 'Partial'
    if (v === 'mismatch') return 'Mismatch'
    return 'Unknown'
  }

  const magnitudeLabel = (value: string | null): string | null => {
    if (!value) return null
    const v = value.trim().toLowerCase()
    if (v === 'transformational') return 'substantial'
    if (v === 'substantial') return 'large'
    return v
  }

  const formatImpactScoreTooltip = (record: DataType): React.ReactNode | undefined => {
    const breakdown = record.impact_score_breakdown
    const tBreakdown = record.transferability_breakdown

    if (!breakdown && !tBreakdown && !record.impact_score_label) {
      return undefined
    }

    const b = (breakdown && typeof breakdown === 'object' ? (breakdown as Record<string, unknown>) : null)
    const tb = (tBreakdown && typeof tBreakdown === 'object' ? (tBreakdown as Record<string, unknown>) : null)

    const note = b && typeof b.note === 'string' ? b.note : null
    const netMag = b && typeof b.net_magnitude === 'number' ? b.net_magnitude : null
    const outcomesUsed = b && typeof b.outcomes_used === 'number' ? b.outcomes_used : null
    const avgCausalWeight =
      b && typeof b.avg_causal_weight === 'number' ? b.avg_causal_weight : null

    const geo = tb ? matchLabel(tb.geography) : 'Unknown'
    const pop = tb ? matchLabel(tb.population) : 'Unknown'
    const setting = tb ? matchLabel(tb.inner_setting) : 'Unknown'
    const constraintsProvided = tb ? tb.constraints_provided === true : false
    const exceedsConstraintsRaw = tb ? tb.exceeds_constraints : null
    const constraintLevelsRaw = tb ? tb.constraint_levels : null
    const implementationEvidenceRaw = tb ? tb.implementation_evidence : null
    const extractedContextRaw = tb ? tb.extracted_context : null
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
    const extractedContext =
      extractedContextRaw && typeof extractedContextRaw === 'object'
        ? (extractedContextRaw as Record<string, unknown>)
        : {}

    const transferability =
      typeof record.transferability_score === 'number' ? record.transferability_score : null

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
        // Keep the magnitude bucket from the strongest single contribution for this outcome.
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

    const outcomeMatchLabel = (sim: number): string => {
      if (sim >= 0.85) return 'Direct match'
      if (sim >= 0.75) return 'Proxy measure'
      if (sim >= 0.5) return 'Contributing factor'
      if (sim >= 0.2) return 'Weak link'
      return 'Unrelated'
    }

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
      typeof record.impact_score_label === 'string' && record.impact_score_label.trim()
        ? record.impact_score_label
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
                const mag = displayMag ? ` (${displayMag})` : ''
                return (
                  <li key={d.outcome}>
                    {d.outcome}: {direction}{mag}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {showCalcDetails ? (
          <div className="border-t border-neutral-700 pt-2 space-y-1">
            <div className="font-medium">Calculation details (dev)</div>
            <div>net_magnitude: {netMag != null ? netMag.toFixed(3) : 'n/a'}</div>
            <div>transferability: {transferability != null ? transferability.toFixed(3) : 'n/a'}</div>
            <div>avg_causal_weight: {avgCausalWeight != null ? avgCausalWeight.toFixed(3) : 'n/a'}</div>
            <div>context: geography={geo}, population={pop}, setting={setting}</div>
            <div>
              extracted: countries={JSON.stringify(extractedContext.countries ?? [])}, populations={JSON.stringify(extractedContext.populations ?? [])}, settings={JSON.stringify(extractedContext.settings ?? [])}
            </div>
            <div>
              {`constraints: cost=${String(constraintLevels?.cost ?? 'n/a')}, staffing=${String(constraintLevels?.staffing ?? 'n/a')}, complexity=${String(constraintLevels?.implementation_complexity ?? 'n/a')}`}
            </div>
            <div>
              {`evidence: cost=${String(implementationEvidence?.cost ?? 'n/a')}, staffing=${String(implementationEvidence?.staffing ?? 'n/a')}, complexity=${String(implementationEvidence?.implementation_complexity ?? 'n/a')}`}
            </div>
            {showOutcomeMatch && bestMatch != null ? (
              <div>
                best_outcome_similarity: {bestMatch.similarity.toFixed(2)} (
                {outcomeMatchLabel(bestMatch.similarity)})
              </div>
            ) : null}
            {drivers.length ? (
              <div>
                drivers: {drivers.map((d) => `${d.outcome}=${d.netContribution.toFixed(2)}`).join(' | ')}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    )
  }

  // Conditional columns (Study Type, Sample Size, Source, and Status)
  const conditionalColumns: ColumnsType<DataType> = showAdditionalColumns ? [
    {
      title: 'Sample Size',
      dataIndex: 'sample_size',
      key: 'sample_size',
      width: '8%',
      sorter: (a, b) => (a.sample_size || 0) - (b.sample_size || 0),
      render: (_text, record) => {
        const sampleSize = record.sample_size
        if (!sampleSize || sampleSize <= 0) {
          return <span className="text-gray-400 text-xs">-</span>
        }
        
        // Format large numbers with commas
        const formatted = sampleSize.toLocaleString()
        
        return (
          <span className="text-sm text-gray-700">
            {formatted}
          </span>
        )
      },
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      width: '6%',
      sorter: (a, b) => (a.source || '').localeCompare(b.source || ''),
      render: (_text, record) => {
        const source = record.source || 'unknown'
        let displayText = source
        
        if (source === 'openalex') {
          displayText = 'OpenAlex'
        } else if (source === 'overton') {
          displayText = 'Overton'
        }
        
        return (
          <span className="text-sm text-gray-700">
            {displayText}
          </span>
        )
      },
    },
    {
      title: 'Status',
      dataIndex: 'extraction_status',
      key: 'extraction_status',
      width: '8%',
      sorter: (a, b) => {
        const getStatusPriority = (status: string, textSource?: string) => {
          if (status === 'completed') return textSource === 'full_text' ? 3 : 2
          if (status === 'skipped') return 1
          return 0 // failed, not processed, unknown
        }

        const aPriority = getStatusPriority(a.extraction_status || 'unknown', a.text_source)
        const bPriority = getStatusPriority(b.extraction_status || 'unknown', b.text_source)
        return aPriority - bPriority
      },
      render: (_text, record) => {
        const status = record.extraction_status || 'unknown'
        const textSource = record.text_source
        
        let color = 'text-gray-500'
        let bgColor = 'bg-gray-100'
        let displayText = 'not processed'
        
        if (status === 'completed') {
          color = 'text-green-700'
          bgColor = 'bg-green-100'
          if (textSource === 'full_text') {
            displayText = 'completed: full-text'
          } else if (textSource === 'abstract') {
            displayText = 'completed: abstract'
          } else {
            displayText = 'completed'
          }
        } else if (status === 'failed') {
          color = 'text-gray-600'
          bgColor = 'bg-gray-100'
          displayText = 'not processed'
        } else if (status === 'skipped') {
          color = 'text-yellow-700'
          bgColor = 'bg-yellow-100'
          displayText = 'skipped'
        } else {
          // unknown or any other status
          displayText = 'not processed'
        }
        
        return (
          <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${color} ${bgColor}`}>
            {displayText}
          </span>
        )
      },
    },
  ] : [];

  // Combine all columns
  const columns: ColumnsType<DataType> = [
    ...baseColumns,
    ...conditionalColumns,
    // Add extracted fields as additional columns
    ...extractedFields
  ]

  return (
    <div className="space-y-4">
      
      <Table
        columns={columns}
        dataSource={tableData}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} items`,
        }}
        scroll={{ x: 1200 }}
        size="small"
        bordered
        rowClassName={(record) => {
          // When showing all docs (highlightNonRelevant=true), gray out non-relevant/non-evidence rows
          const isRelevantEvidence = record.is_relevant_evidence !== false && record.is_relevant !== false && record.is_evidence !== false
          if (highlightNonRelevant && !isRelevantEvidence) {
            return 'bg-slate-100 opacity-60'
          }
          return 'bg-white'
        }}
        sortDirections={['descend', 'ascend']}
      />
    </div>
  )
} 
