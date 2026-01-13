'use client'

import React from 'react'
import { TierBadge } from '@/components/ui/tier-badge'
import { Badge } from '@/components/ui/badge'
import { ExternalLink } from 'lucide-react'

interface ResultSummary {
  outcome: string
  direction: string
  effect_size?: string
  effect_size_type?: string
  p_value?: string
  uncertainty?: string
  result_text?: string
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
  sample_size?: number | string | null
  impact_score?: number
  evidence_score?: number
  results_summary?: ResultSummary[]
  documents?: SourceDocument[]
  population_measured?: string
}

interface InterventionCardProps {
  intervention: InterventionCardData
  studyCount?: number
  showStudyLink?: boolean
}

function formatDirection(direction: string): string {
  const d = direction?.toLowerCase()
  if (d === 'increase') return 'increased'
  if (d === 'decrease') return 'decreased'
  if (d === 'no change' || d === 'null' || d === 'no_change') return 'showed no significant change in'
  return 'affected'
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
  
  const contextParts: string[] = []
  
  const population = intervention.population_measured || 
    intervention.results_summary?.[0]?.population_measured
  if (population && population !== 'null') {
    contextParts.push(`for ${population}`)
  }
  
  if (intervention.country && intervention.country !== 'Unknown' && intervention.country !== 'null') {
    contextParts.push(`in ${intervention.country}`)
  }
  
  if (contextParts.length > 0) {
    parts.push(contextParts.join(' '))
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
  
  if (validResults.length === 1) {
    const r = validResults[0]
    
    if (r.result_text && r.result_text !== 'null' && r.result_text.length < 200) {
      let text = r.result_text.trim()
      if (!text.endsWith('.')) text += '.'
      return text
    }
    
    const direction = formatDirection(r.direction)
    let sentence = `The intervention ${direction} ${r.outcome}`
    
    if (r.effect_size && r.effect_size !== 'null' && r.effect_size !== 'n/a') {
      sentence += ` (effect size: ${r.effect_size})`
    }
    
    if (r.p_value && r.p_value !== 'null' && r.p_value !== 'n/a') {
      sentence += `, p${r.p_value.startsWith('<') || r.p_value.startsWith('=') ? '' : '='}${r.p_value}`
    }
    
    sentence += '.'
    return sentence
  }
  
  const outcomeDescriptions = validResults.slice(0, 3).map(r => {
    const direction = formatDirection(r.direction)
    let desc = `${direction} ${r.outcome}`
    if (r.effect_size && r.effect_size !== 'null' && r.effect_size !== 'n/a') {
      desc += ` (${r.effect_size})`
    }
    return desc
  })
  
  if (outcomeDescriptions.length === 1) {
    return `The intervention ${outcomeDescriptions[0]}.`
  }
  
  if (outcomeDescriptions.length === 2) {
    return `The intervention ${outcomeDescriptions[0]} and ${outcomeDescriptions[1]}.`
  }
  
  const lastOutcome = outcomeDescriptions.pop()
  return `The intervention ${outcomeDescriptions.join(', ')}, and ${lastOutcome}.`
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
  const outcomeSentence = generateOutcomeSentence(intervention.results_summary)
  
  const primaryDoc = intervention.documents?.[0]
  const studyTitle = primaryDoc?.title || ''
  
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5 hover:border-gray-200 transition-colors">
      <div className="flex justify-between items-start gap-4 mb-3">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <h3 className="text-base font-semibold text-gray-900 leading-snug">
            {intervention.name}
          </h3>
          {intervention.type && intervention.type !== 'Unknown' && (
            <Badge 
              variant="outline" 
              className="shrink-0 text-xs font-medium uppercase tracking-wide text-gray-500 bg-gray-50"
            >
              {intervention.type}
            </Badge>
          )}
        </div>
        
        <div className="shrink-0 flex items-center gap-3">
          {intervention.impact_score != null && (
            <TierBadge score={intervention.impact_score} label="Impact" />
          )}
          {intervention.evidence_score != null && (
            <TierBadge score={intervention.evidence_score} label="Evidence" />
          )}
        </div>
      </div>
      
      <div className="space-y-2 text-gray-600 leading-relaxed">
        {interventionSentence && (
          <p>{interventionSentence}</p>
        )}
        {outcomeSentence && (
          <p>{outcomeSentence}</p>
        )}
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

