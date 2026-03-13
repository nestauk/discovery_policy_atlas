'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import { Card, CardContent } from '@/components/ui/card'
import { ChevronDown, ChevronRight, HelpCircle, Star } from 'lucide-react'
import { fetchEvidenceCategories, getEvidenceCategories, type EvidenceCategory } from '@/lib/evidenceCategories'

interface FAQItem {
  id: string
  question: string
  answer: string | React.ReactNode
}

const StarRating = ({ rating }: { rating: number }) => (
  <div className="flex items-center gap-1">
    {[...Array(5)].map((_, i) => (
      <Star 
        key={i} 
        className={`h-4 w-4 ${i < rating ? 'text-yellow-400 fill-current' : 'text-slate-300'}`} 
      />
    ))}
    <span className="ml-2 text-sm font-medium text-slate-600">{rating}/5</span>
  </div>
)

// Definitions and examples for each evidence category (FAQ-specific content)
const CATEGORY_DETAILS: Record<string, { definition: string; examples: string | null }> = {
  'systematic_review': {
    definition: "A systematic review collects all available studies on a topic, evaluates their quality, and synthesises results. This is often through statistical meta-analysis. This provides the most robust evidence by combining findings across multiple studies.",
    examples: "Cochrane reviews, PRISMA compliant analyses, pooled effect estimates across RCTs",
  },
  'rct': {
    definition: "Randomised controlled trials (RCTs) minimise bias through random assignment to treatment and control groups. Quasi-experimental designs estimate causal impact without full randomisation, using methods like difference-in-differences or regression discontinuity.",
    examples: "Clinical trials with treatment/control arms, natural experiments, propensity score matching studies",
  },
  'observational': {
    definition: "Observational studies draw inferences without researcher control over treatment assignment. They can identify associations but have weaker causal certainty due to potential confounding.",
    examples: "Cohort studies, case-control studies, cross-sectional surveys, longitudinal analyses",
  },
  'modelling': {
    definition: "Uses mathematical or computational models to simulate outcomes, forecast impacts, or explore scenarios. Valuable for projections but does not provide direct empirical evidence.",
    examples: "Economic models, scenario analyses, forecasting studies, agent-based simulations",
  },
  'policy': {
    definition: "Documents that aggregate and interpret existing evidence into actionable insights for policymakers or practitioners. They synthesise rather than generate primary evidence.",
    examples: "Government white papers, think tank policy briefs, sectoral guidance documents",
  },
  'qualitative': {
    definition: "Research gathering non-numerical data to understand attitudes, beliefs, and real-world implementation. Rich in context but not designed to establish causal relationships.",
    examples: "Interview studies, focus groups, case studies, thematic analyses, lived experience reports",
  },
  'opinion': {
    definition: "Publications where experts provide interpretation or guidance based on professional experience rather than new empirical data. May reference literature but lacks systematic methodology.",
    examples: "Editorials, thought leadership pieces, consultation responses, viewpoint essays",
  },
}

const EvidenceCategoryCard = ({ category }: { category: EvidenceCategory }) => {
  const details = CATEGORY_DETAILS[category.key]
  if (!details) return null

  return (
    <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
      <div className="flex items-center gap-3 mb-2">
        <span
          className="px-3 py-1 rounded-full text-sm font-medium"
          style={{ backgroundColor: category.bg_color, color: category.text_color }}
        >
          {category.short_name}
        </span>
        <span className="text-sm font-medium text-slate-500">Score: {category.score}/5</span>
      </div>
      <p className="text-sm text-slate-700 mb-2">{details.definition}</p>
      {details.examples && (
        <p className="text-xs text-slate-500"><span className="font-medium">Examples:</span> {details.examples}</p>
      )}
    </div>
  )
}

const EvidenceStrengthFAQ = () => {
  const [categories, setCategories] = useState<EvidenceCategory[]>(getEvidenceCategories())
  const [showDefinitions, setShowDefinitions] = useState(false)

  useEffect(() => {
    fetchEvidenceCategories().then(setCategories)
  }, [])

  // Filter to only show categories that have definitions (excludes any missing)
  const displayCategories = categories.filter(c => CATEGORY_DETAILS[c.key])

  return (
    <div className="space-y-6">
      <p className="text-slate-700 leading-relaxed">
        Documents are classified by study design into categories following a standard evidence hierarchy.
These categories form the basis for a score (1–5) reflecting evidence strength for establishing causality.
      </p>

      {/* Evidence Pyramid Image */}
      <div className="flex justify-center py-4">
        <Image
          src="/images/evidence-pyramid.png"
          alt="Evidence hierarchy pyramid showing study types ranked by methodological strength"
          className="max-w-md w-full rounded-lg border border-slate-200"
          width={768}
          height={768}
        />
      </div>

      {/* Collapsible Category Definitions */}
      <button
        onClick={() => setShowDefinitions(!showDefinitions)}
        className="flex items-center gap-2 text-slate-700 hover:text-slate-900 transition-colors"
      >
        {showDefinitions ? (
          <ChevronDown className="h-5 w-5" />
        ) : (
          <ChevronRight className="h-5 w-5" />
        )}
        <span className="text-lg font-semibold">Category Definitions</span>
      </button>

      {showDefinitions && (
        <div className="space-y-3">
          {displayCategories.map((category) => (
            <EvidenceCategoryCard key={category.key} category={category} />
          ))}
        </div>
      )}
    </div>
  )
}

const ImpactAssessmentFAQ = () => (
  <div className="space-y-4">
    <p className="text-slate-700 leading-relaxed">
      Impact assessment summarises what the evidence suggests an intervention does, and how likely those effects are to translate to the target context.
      It is broken into:
    </p>

    <ul className="list-disc pl-5 text-slate-700 leading-relaxed space-y-2">
      <li>
        <span className="font-medium text-slate-900">Verdict</span>: whether outcomes are positive, negative, or neutral (and “contested” when findings disagree).
      </li>
      <li>
        <span className="font-medium text-slate-900">Magnitude</span>: assessment of effect size measurements reported across sources.
      </li>
      <li>
        <span className="font-medium text-slate-900">Transferability</span>: comparison of population, setting and geography against the target context, plus any cost/staffing/complexity constraints you specify.
      </li>
      <li>
        <span className="font-medium text-slate-900">Implementation</span>: estimated staffing, costs, and complexity of delivery.
      </li>
      <li>
        <span className="font-medium text-slate-900">Risks</span>: unintended consequences and risk themes.
      </li>
    </ul>

    <p className="text-slate-700 leading-relaxed">
      We show two outputs:
      <br />
      <span className="font-medium text-slate-900">Impact Score (1–5)</span> for quick comparison, based on magnitude and transferability.
      <br />
      <span className="font-medium text-slate-900">Impact Profile</span> for the detailed breakdown behind the score.
    </p>
    
    <p className="text-slate-700 leading-relaxed">
      Sometimes the Impact Score is shown as N/A because we don’t have enough extracted outcome information to calculate it.
      This is usually due to limited access to full text: if we only have an abstract or metadata (and not the full paper/report), we often can’t extract the outcomes and results needed for scoring.
    </p>

    <div className="space-y-3">
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={5} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Large beneficial effects with high transferability</p>
          <p className="text-sm text-slate-600">Stronger sources point in the same direction, effects are meaningful, and the population/setting/geography closely match the target context.</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={4} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Clear beneficial effects with generally good fit</p>
          <p className="text-sm text-slate-600">Evidence is fairly consistent, but there are some limits (for example, uncertainty on magnitude, transferability, or implementation constraints).</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={3} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Modest or mixed effects, or material transferability constraints</p>
          <p className="text-sm text-slate-600">The direction may be uncertain or effects are smaller, and/or the evidence context differs meaningfully from the target context.</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={2} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Small, inconsistent, or highly context-dependent effects</p>
          <p className="text-sm text-slate-600">Findings vary across sources, effects look fragile, or transferability to the target context is low.</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={1} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">No relevant evidence, or possible net harm</p>
          <p className="text-sm text-slate-600">There are no relevant outcome signals for your question, or higher-quality sources suggest negative effects.</p>
        </div>
      </div>
    </div>
  </div>
)

const faqItems: FAQItem[] = [
  {
    id: '1',
    question: 'How do I start a new analysis project?',
    answer: 'To create a new analysis project, go to the Search page and enter your research query. The system will automatically create a project and begin searching for relevant evidence. You can then review the results and refine your search as needed.'
  },
  {
    id: '2',
    question: 'How is evidence strength assessed?',
    answer: <EvidenceStrengthFAQ />
  },
  {
    id: '3',
    question: 'How is impact assessed?',
    answer: <ImpactAssessmentFAQ />
  }
]

export default function FAQPage() {
  const [openItems, setOpenItems] = useState<string[]>([])

  const toggleItem = (id: string) => {
    setOpenItems(prev => 
      prev.includes(id) 
        ? prev.filter(item => item !== id)
        : [...prev, id]
    )
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Frequently Asked Questions</h1>
          </div>
        </div>
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="space-y-4">
            {faqItems.map((item) => (
              <Card key={item.id} className="border-slate-200 hover:border-blue-300 transition-colors">
                <CardContent className="p-0">
                  <button
                    onClick={() => toggleItem(item.id)}
                    className="w-full p-6 text-left flex items-center justify-between hover:bg-slate-50 transition-colors"
                  >
                    <h3 className="text-lg font-semibold text-slate-900 pr-4">
                      {item.question}
                    </h3>
                    {openItems.includes(item.id) ? (
                      <ChevronDown className="h-5 w-5 text-slate-500 flex-shrink-0" />
                    ) : (
                      <ChevronRight className="h-5 w-5 text-slate-500 flex-shrink-0" />
                    )}
                  </button>
                  
                  {openItems.includes(item.id) && (
                    <div className="px-6 pb-6 pt-0">
                      <div className="border-t border-slate-200 pt-4">
                        {typeof item.answer === 'string' ? (
                          <p className="text-slate-700 leading-relaxed">
                            {item.answer}
                          </p>
                        ) : (
                          item.answer
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mt-12 text-center">
            <div className="bg-slate-50 rounded-lg p-8">
              <HelpCircle className="h-12 w-12 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">Still have questions?</h3>
              <p className="text-slate-600 mb-6">
                Contact us for assistance.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}