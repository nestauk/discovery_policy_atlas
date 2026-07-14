'use client'

import { useState, useCallback, useEffect } from 'react'
import {
  Search,
  FileText,
  BookOpen,
  Target,
  Lightbulb,
  Lock,
  Loader2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import SearchWizard, { SearchContext, useWizard } from '@/components/search/SearchWizard'

// ---- Types ----

type SectionStatus = 'locked' | 'loading' | 'ready' | 'active'

interface SearchSummaryData {
  question: string
  useCase: string | null
  sources: string[]
  geography: string[]
}

// ---- Dummy Data ----
// Example: "What interventions reduce childhood obesity in low-income urban settings?"

const DUMMY_DOCS = [
  {
    id: '1',
    title: 'School-based physical activity programmes and childhood obesity: a systematic review',
    authors: ['Williams, S.', 'Patel, K.', 'Okafor, N.'],
    year: 2022,
    source: 'Academic',
    type: 'Systematic Review',
    relevance: 'High',
  },
  {
    id: '2',
    title: 'Subsidised fruit and vegetable programmes in low-income communities: evidence from UK pilots',
    authors: ['Hughes, E.', 'Davies, R.'],
    year: 2021,
    source: 'Policy',
    type: 'Policy Report',
    relevance: 'High',
  },
  {
    id: '3',
    title: 'Family-based behavioural interventions for childhood obesity: meta-analysis of RCTs',
    authors: ['Johansson, M.', 'Torres, A.', 'Brennan, C.', 'Ali, F.'],
    year: 2023,
    source: 'Academic',
    type: 'Meta-Analysis',
    relevance: 'High',
  },
  {
    id: '4',
    title: 'Food environment mapping in deprived urban areas: implications for childhood health',
    authors: ['Nakamura, Y.', 'Singh, P.'],
    year: 2020,
    source: 'Academic',
    type: 'Observational Study',
    relevance: 'Medium',
  },
  {
    id: '5',
    title: 'Childhood Obesity Strategy 2021–2026: Review of evidence and policy options',
    authors: ['DHSC'],
    year: 2021,
    source: 'Policy',
    type: 'Strategy Document',
    relevance: 'Medium',
  },
  {
    id: '6',
    title: 'Sugar-sweetened beverage taxes and child health outcomes: a natural experiment',
    authors: ['Reyes, G.', 'Hoffman, T.'],
    year: 2023,
    source: 'Academic',
    type: 'Quasi-Experimental',
    relevance: 'Low',
  },
]

const DUMMY_INTERVENTIONS = [
  {
    id: '1',
    theme: 'School-based physical activity',
    docCount: 3,
    strength: 'Strong' as const,
    description:
      'Structured PE and active travel programmes embedded in school curricula targeting 5–11 year olds. Consistent moderate effects on BMI (effect size 0.3–0.5 SD) observed across multiple high-quality trials.',
    examples: ['Daily Mile programme', 'Change4Life school sports clubs', 'Active travel to school schemes'],
  },
  {
    id: '2',
    theme: 'Subsidised nutrition access',
    docCount: 2,
    strength: 'Moderate' as const,
    description:
      'Voucher and subsidy schemes improving access to fruit, vegetables, and balanced meals for low-income families. Produces meaningful dietary improvements; longer follow-up needed for obesity outcomes.',
    examples: ['Healthy Start vouchers', 'Universal Free School Meals extension', 'Community food co-ops'],
  },
  {
    id: '3',
    theme: 'Family behavioural support',
    docCount: 2,
    strength: 'Moderate' as const,
    description:
      'Structured family-facing programmes combining dietary education with behaviour change support. Strongest individual-level outcomes but face scalability challenges in resource-constrained settings.',
    examples: ['MEND programme', 'HENRY programme', 'Tier 2 weight management services'],
  },
  {
    id: '4',
    theme: 'Food environment regulation',
    docCount: 1,
    strength: 'Emerging' as const,
    description:
      'Area-level policies restricting unhealthy food access or marketing near schools and residential areas. Early-stage evidence; longer evaluation horizons required.',
    examples: ['Takeaway planning restrictions', 'SSB levy', 'Junk food advertising restrictions'],
  },
]

// ---- Shared Primitives ----

const USE_CASE_LABELS: Record<string, string> = {
  horizon_scan: 'Horizon Scan',
  rapid_brief: 'Rapid Brief',
  policy_note: 'Policy Note',
  policy_blueprint: 'Policy Blueprint',
  rapid_evidence_review: 'Rapid Evidence Review',
  not_sure: 'General Search',
}

// ---- Section Card ----

function SectionCard({
  icon,
  title,
  status,
  children,
}: {
  icon: React.ReactNode
  title: string
  status: SectionStatus
  children: React.ReactNode
}) {
  const isLocked = status === 'locked'
  return (
    <div
      className={`rounded-2xl border bg-white shadow-sm transition-all duration-300 ${
        isLocked ? 'border-slate-100 opacity-50' : 'border-slate-200'
      }`}
    >
      <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
        <div
          className={`flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0 ${
            isLocked ? 'bg-slate-100 text-slate-400' : 'bg-blue-50 text-blue-600'
          }`}
        >
          {isLocked ? <Lock className="w-4 h-4" /> : icon}
        </div>
        <h2
          className={`text-lg font-semibold ${isLocked ? 'text-slate-400' : 'text-slate-900'}`}
        >
          {title}
        </h2>
        {status === 'loading' && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-blue-600 flex-shrink-0">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading…
          </span>
        )}
        {status === 'ready' && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-green-600 flex-shrink-0">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            Ready
          </span>
        )}
      </div>

      <div>{children}</div>
    </div>
  )
}

// ---- Empty / Loading States ----

function EmptyState({ what, whenAvailable }: { what: string; whenAvailable: string }) {
  return (
    <div className="px-6 py-10 text-center space-y-2">
      <Lock className="w-5 h-5 text-slate-300 mx-auto" />
      <p className="text-sm text-slate-500 max-w-sm mx-auto mt-2">{what}</p>
      <p className="text-xs text-slate-400">Available once: {whenAvailable}</p>
    </div>
  )
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="px-6 py-10 text-center">
      <Loader2 className="w-6 h-6 text-blue-500 animate-spin mx-auto" />
      <p className="text-sm text-slate-500 mt-3">{label}</p>
    </div>
  )
}

// ---- Search Summary Card (collapsed wizard) ----

function SearchSummaryCard({
  data,
  wizardOpen,
  onToggle,
}: {
  data: SearchSummaryData
  wizardOpen: boolean
  onToggle: () => void
}) {
  return (
    <div className="px-6 py-5 border-b border-slate-100">
      <div className="flex items-start gap-4">
        <div className="flex-1 space-y-2 min-w-0">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Research question
          </p>
          <p className="text-base text-slate-900 leading-snug">{data.question || '—'}</p>
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {data.useCase && (
              <span className="text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200 px-2.5 py-0.5 rounded-full">
                {USE_CASE_LABELS[data.useCase] ?? data.useCase}
              </span>
            )}
            {data.sources.includes('openalex') && (
              <span className="text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 px-2.5 py-0.5 rounded-full">
                Academic literature
              </span>
            )}
            {data.sources.includes('overton') && (
              <span className="text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-0.5 rounded-full">
                Policy documents
              </span>
            )}
            {data.geography.length > 0 && (
              <span className="text-xs font-medium bg-slate-100 text-slate-600 px-2.5 py-0.5 rounded-full">
                {data.geography.length === 1
                  ? data.geography[0]
                  : `${data.geography.length} regions`}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={onToggle}
          className="flex-shrink-0 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium mt-0.5 transition-colors"
        >
          {wizardOpen ? (
            <>
              <ChevronUp className="w-4 h-4" />
              Collapse
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4" />
              Edit search
            </>
          )}
        </button>
      </div>
    </div>
  )
}

// ---- Documents Content ----

function DocumentsContent() {
  return (
    <div className="px-6 py-4">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-slate-600">
          <span className="font-semibold text-slate-900">{DUMMY_DOCS.length}</span> documents found
          {' · '}
          <span className="font-semibold text-green-700">4 relevant</span>
        </p>
        <button className="text-xs font-medium text-blue-600 hover:underline">Download CSV</button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 text-xs">Title</th>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 text-xs whitespace-nowrap">
                Year
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 text-xs">Source</th>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 text-xs whitespace-nowrap">
                Type
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-slate-600 text-xs">
                Relevance
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {DUMMY_DOCS.map((doc) => (
              <tr key={doc.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3 max-w-xs">
                  <div className="font-medium text-slate-900 leading-snug">{doc.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{doc.authors.join(', ')}</div>
                </td>
                <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{doc.year}</td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      doc.source === 'Academic'
                        ? 'bg-blue-50 text-blue-700'
                        : 'bg-amber-50 text-amber-700'
                    }`}
                  >
                    {doc.source}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{doc.type}</td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      doc.relevance === 'High'
                        ? 'bg-green-50 text-green-700'
                        : doc.relevance === 'Medium'
                          ? 'bg-yellow-50 text-yellow-700'
                          : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {doc.relevance}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---- Policy Background Content ----

function BackgroundContent() {
  return (
    <div className="px-6 py-5 space-y-5 text-sm text-slate-700 leading-relaxed max-w-3xl">
      <div>
        <h3 className="font-semibold text-slate-900 text-base mb-2">Policy Background</h3>
        <p>
          Childhood obesity is a significant and growing public health challenge, particularly acute
          in low-income urban communities. Rates in England&apos;s most deprived quintile are
          approximately{' '}
          <strong className="text-slate-900">twice those in the least deprived areas</strong>,
          creating both a health equity concern and a long-term burden on health and social care
          systems.
        </p>
      </div>
      <div>
        <h4 className="font-semibold text-slate-900 mb-2">Key drivers in low-income settings</h4>
        <ul className="space-y-2 list-none pl-0">
          {[
            [
              'Food environment',
              'Higher density of fast-food outlets relative to supermarkets in deprived urban areas reduces access to affordable nutritious options.',
            ],
            [
              'Physical activity',
              'Low-income urban children face reduced access to safe outdoor space, sports facilities, and structured after-school activity.',
            ],
            [
              'Socioeconomic stress',
              'Parental time poverty and financial constraints limit the feasibility of dietary and lifestyle changes.',
            ],
            [
              'School food',
              'Despite nutritional standards, compliance and uptake of school meals varies significantly across income groups.',
            ],
          ].map(([term, def]) => (
            <li key={term} className="flex gap-2">
              <span className="font-semibold text-slate-800 whitespace-nowrap flex-shrink-0">
                {term}:
              </span>
              <span>{def}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-slate-900 mb-2">Policy context</h4>
        <p>
          The UK Government&apos;s <em>Childhood Obesity Plan</em> (2016, updated 2022) sets a
          target of halving childhood obesity rates by 2030. Local authorities have primary
          responsibility for public health interventions but face significant capacity constraints.
          NICE guidance (PH47, PH53) provides evidence-based recommendations but implementation at
          scale remains limited.
        </p>
        <p className="mt-2">
          International comparators — notably the{' '}
          <strong className="text-slate-900">
            Netherlands Amsterdam Healthy Weight Programme
          </strong>{' '}
          and <strong className="text-slate-900">Chile&apos;s front-of-pack labelling scheme</strong>{' '}
          — provide evidence of population-level impact under specific conditions.
        </p>
      </div>
    </div>
  )
}

// ---- Executive Summary Content ----

function ExecutiveSummaryContent() {
  return (
    <div className="px-6 py-5 space-y-5 text-sm text-slate-700 leading-relaxed max-w-3xl">
      <p className="text-slate-600">
        This rapid evidence review draws on{' '}
        <strong className="text-slate-900">6 documents</strong> spanning systematic reviews, policy
        reports, and primary studies published since 2020.
      </p>
      <div>
        <h4 className="font-semibold text-slate-900 mb-3">Key findings</h4>
        <ul className="space-y-2.5 list-none pl-0">
          {[
            [
              'School-based physical activity programmes',
              'Show consistent moderate effects on BMI outcomes (effect size 0.3–0.5 SD), with greatest impact when embedded in the curriculum rather than offered as add-ons.',
            ],
            [
              'Subsidised food access schemes',
              'Produce meaningful dietary improvements among low-income families, though obesity outcomes require longer follow-up to measure.',
            ],
            [
              'Family-based behavioural interventions',
              'Produce the strongest individual-level outcomes but face significant scalability challenges in resource-constrained settings.',
            ],
            [
              'Food environment regulation',
              'Shows promising but early-stage evidence; area-level restrictions require longer evaluation horizons.',
            ],
          ].map(([finding, detail]) => (
            <li key={finding} className="flex gap-2.5">
              <span className="mt-1.5 flex-shrink-0 w-1.5 h-1.5 rounded-full bg-blue-500" />
              <span>
                <strong className="text-slate-800">{finding}</strong> — {detail}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-slate-900 mb-2">Recommendations</h4>
        <ol className="space-y-1.5 list-none pl-0 counter-reset-none">
          {[
            'Prioritise school-based universal programmes as the most scalable and equitable route.',
            'Combine dietary access subsidies with physical activity components for additive effects.',
            'Pilot area-level food environment interventions with built-in evaluation frameworks.',
          ].map((rec, i) => (
            <li key={i} className="flex gap-2.5">
              <span className="flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-blue-600 text-white text-xs font-semibold mt-0.5">
                {i + 1}
              </span>
              <span>{rec}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
        <p className="text-xs font-semibold text-amber-800 mb-0.5">Evidence caveat</p>
        <p className="text-xs text-amber-700">
          Most high-quality RCTs are conducted in high-income settings with dedicated research
          infrastructure; transferability to routine local authority delivery requires caution.
        </p>
      </div>
    </div>
  )
}

// ---- Policy Interventions Content ----

const STRENGTH_CONFIG = {
  Strong: {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
    dot: 'bg-green-500',
  },
  Moderate: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    dot: 'bg-blue-500',
  },
  Emerging: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    dot: 'bg-amber-500',
  },
} as const

function InterventionsContent() {
  const [openId, setOpenId] = useState<string | null>(null)

  return (
    <div className="px-6 py-4 space-y-3">
      {DUMMY_INTERVENTIONS.map((intervention) => {
        const cfg = STRENGTH_CONFIG[intervention.strength]
        const isOpen = openId === intervention.id
        return (
          <div key={intervention.id} className="rounded-xl border border-slate-200 overflow-hidden">
            <button
              onClick={() => setOpenId(isOpen ? null : intervention.id)}
              className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50 transition-colors text-left"
            >
              <span
                className={`flex-shrink-0 flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full border ${cfg.bg} ${cfg.text} ${cfg.border}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                {intervention.strength}
              </span>
              <span className="flex-1 font-medium text-slate-900 text-sm">
                {intervention.theme}
              </span>
              <span className="text-xs text-slate-500 flex-shrink-0">
                {intervention.docCount} doc{intervention.docCount !== 1 ? 's' : ''}
              </span>
              {isOpen ? (
                <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" />
              ) : (
                <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
              )}
            </button>
            {isOpen && (
              <div className="px-4 pb-4 pt-3 border-t border-slate-100 bg-slate-50/60 space-y-3">
                <p className="text-sm text-slate-600 leading-relaxed">{intervention.description}</p>
                <div className="flex flex-wrap gap-1.5">
                  {intervention.examples.map((ex) => (
                    <span
                      key={ex}
                      className="text-xs bg-white border border-slate-200 text-slate-700 px-2.5 py-0.5 rounded-full"
                    >
                      {ex}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---- Main Page ----

export default function WorkspacePage() {
  const [searchData, setSearchData] = useState<SearchSummaryData | null>(null)
  const [wizardExpandedPostSearch, setWizardExpandedPostSearch] = useState(false)
  const [docsStatus, setDocsStatus] = useState<SectionStatus>('locked')
  const [analysisStatus, setAnalysisStatus] = useState<SectionStatus>('locked')

  // Reset wizard on mount
  useEffect(() => {
    useWizard.getState().reset()
  }, [])

  const handleRunAnalysis = useCallback((context: SearchContext) => {
    setSearchData({
      question: context.researchQuestion,
      useCase: context.useCase,
      sources: context.parameters.sources,
      geography: context.parameters.geography,
    })
    setWizardExpandedPostSearch(false)

    // Simulate: docs appear after ~2.5s, analysis sections after ~4.5s
    setDocsStatus('loading')
    setAnalysisStatus('locked')

    setTimeout(() => {
      setDocsStatus('ready')
      setAnalysisStatus('loading')
    }, 2500)

    setTimeout(() => {
      setAnalysisStatus('ready')
    }, 4500)
  }, [])

  const isSearchRunning = docsStatus === 'loading'
  const hasSearched = searchData !== null

  return (
    <div className="bg-slate-50 min-h-full">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">New Project</h1>
          <p className="text-sm text-slate-500 mt-1">
            Complete the steps below to build your policy evidence review.
          </p>
        </div>

        {/* ── Section 1: Get Started ── */}
        <SectionCard
          icon={<Search className="w-4 h-4" />}
          title="Get Started"
          status={hasSearched ? 'ready' : 'active'}
        >
          {/* After search: show collapsed summary + optional re-expanded wizard */}
          {hasSearched && searchData && (
            <SearchSummaryCard
              data={searchData}
              wizardOpen={wizardExpandedPostSearch}
              onToggle={() => setWizardExpandedPostSearch((v) => !v)}
            />
          )}

          {/* Show wizard when: first visit, or user hit "Edit search" */}
          {(!hasSearched || wizardExpandedPostSearch) && (
            <SearchWizard onRunAnalysis={handleRunAnalysis} isRunning={isSearchRunning} />
          )}

          {/* Show inline running indicator when collapsed and loading */}
          {hasSearched && !wizardExpandedPostSearch && isSearchRunning && (
            <div className="px-6 py-4 flex items-center gap-2 text-sm text-blue-600">
              <Loader2 className="w-4 h-4 animate-spin" />
              Running analysis…
            </div>
          )}
        </SectionCard>

        {/* ── Section 2: Documents ── */}
        <SectionCard
          icon={<FileText className="w-4 h-4" />}
          title="Documents"
          status={docsStatus}
        >
          {docsStatus === 'locked' && (
            <EmptyState
              what="Documents retrieved by your search will appear here. Review, filter, and select which sources to include in your analysis."
              whenAvailable="you run a search using Get Started above"
            />
          )}
          {docsStatus === 'loading' && (
            <LoadingState label="Retrieving and screening documents…" />
          )}
          {docsStatus === 'ready' && <DocumentsContent />}
        </SectionCard>

        {/* ── Section 3: Policy Background & Context ── */}
        <SectionCard
          icon={<BookOpen className="w-4 h-4" />}
          title="Policy Background & Context"
          status={analysisStatus}
        >
          {analysisStatus === 'locked' && (
            <EmptyState
              what="An AI-generated briefing covering the policy context, key drivers, and existing frameworks relevant to your research question."
              whenAvailable="your documents have loaded"
            />
          )}
          {analysisStatus === 'loading' && (
            <LoadingState label="Generating policy background…" />
          )}
          {analysisStatus === 'ready' && <BackgroundContent />}
        </SectionCard>

        {/* ── Section 4: Executive Summary ── */}
        <SectionCard
          icon={<Target className="w-4 h-4" />}
          title="Executive Summary"
          status={analysisStatus}
        >
          {analysisStatus === 'locked' && (
            <EmptyState
              what="A concise summary of the most important findings from your evidence review, with key recommendations and caveats for policy action."
              whenAvailable="your documents have loaded"
            />
          )}
          {analysisStatus === 'loading' && (
            <LoadingState label="Synthesising evidence…" />
          )}
          {analysisStatus === 'ready' && <ExecutiveSummaryContent />}
        </SectionCard>

        {/* ── Section 5: Policy Interventions ── */}
        <SectionCard
          icon={<Lightbulb className="w-4 h-4" />}
          title="Policy Interventions"
          status={analysisStatus}
        >
          {analysisStatus === 'locked' && (
            <EmptyState
              what="A structured breakdown of interventions identified in the evidence, grouped by theme. Includes evidence strength, examples, and implementation notes."
              whenAvailable="your documents have loaded"
            />
          )}
          {analysisStatus === 'loading' && (
            <LoadingState label="Extracting policy interventions…" />
          )}
          {analysisStatus === 'ready' && <InterventionsContent />}
        </SectionCard>
      </div>
    </div>
  )
}
