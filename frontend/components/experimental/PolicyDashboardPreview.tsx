'use client';

import React, { useMemo, useState } from 'react';
import {
  ChevronRight,
  Download,
  ArrowLeft,
  BookOpen,
  SlidersHorizontal,
} from 'lucide-react';

// ----------
// Small, testable helpers (kept pure)
// ----------

export function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

// Scale: 1 (very low) -> 5 (very high)
export function scoreToFiveTier(score: number) {
  const s = clamp(Number(score ?? 0), 1, 5);
  if (s < 1.5) return 'Very low';
  if (s < 2.5) return 'Low';
  if (s < 3.5) return 'Moderate';
  if (s < 4.5) return 'High';
  return 'Very high';
}

export function evidenceLabel(score: number) {
  return scoreToFiveTier(score);
}

export function impactLabel(score: number) {
  return scoreToFiveTier(score);
}

export function tierIndexFromScore(score: number) {
  const t = scoreToFiveTier(score);
  if (t === 'Very low') return 1;
  if (t === 'Low') return 2;
  if (t === 'Moderate') return 3;
  if (t === 'High') return 4;
  return 5;
}

export function deriveStrengthMeta(label: string) {
  const s = String(label ?? '').toLowerCase();
  const tier = s.includes('very high')
    ? 'Very high'
    : s.includes('high')
    ? 'High'
    : s.includes('moderate')
    ? 'Moderate'
    : s.includes('low')
    ? 'Low'
    : 'Very low';

  const bar = s.includes('very high')
    ? 'w-full'
    : s.includes('high')
    ? 'w-4/5'
    : s.includes('moderate')
    ? 'w-3/5'
    : s.includes('low')
    ? 'w-2/5'
    : 'w-1/5';

  return { tier, bar };
}

export function deriveImpactMeta(label: string) {
  const s = String(label ?? '').toLowerCase();
  const strength = s.includes('very high')
    ? 'Very high'
    : s.includes('high')
    ? 'High'
    : s.includes('moderate')
    ? 'Moderate'
    : s.includes('low')
    ? 'Low'
    : 'Very low';

  const bar = s.includes('very high')
    ? 'w-full'
    : s.includes('high')
    ? 'w-4/5'
    : s.includes('moderate')
    ? 'w-3/5'
    : s.includes('low')
    ? 'w-2/5'
    : 'w-1/5';

  return { strength, bar };
}

// ----------
// UI components
// ----------

function tierBadgeClasses(tier: string) {
  switch (tier) {
    case 'Very high':
      return 'bg-green-500 text-white';
    case 'High':
      return 'bg-lime-400 text-gray-900';
    case 'Moderate':
      return 'bg-amber-300 text-gray-900';
    case 'Low':
      return 'bg-orange-300 text-gray-900';
    case 'Very low':
    default:
      return 'bg-rose-400 text-white';
  }
}

function TierBadge({ tier, label }: { tier: string; label?: string }) {
  const t = tier ?? 'Moderate';
  return (
    <span className="inline-flex items-center gap-1.5">
      {label && <span className="text-xs text-gray-500">{label}:</span>}
      <span
        className={`inline-flex items-center justify-center rounded-full px-3 py-1 text-xs font-semibold ${tierBadgeClasses(
          t
        )}`}
      >
        {t}
      </span>
    </span>
  );
}

function RangeFilter({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  const tiers = ['Very low', 'Low', 'Moderate', 'High', 'Very high'];
  const shown = tiers[clamp(value, 1, 5) - 1];

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium text-gray-900">{label}</div>
        <div className="text-xs text-gray-500">{shown}+</div>
      </div>

      <input
        type="range"
        min={1}
        max={5}
        step={1}
        value={value}
        onChange={(e) => onChange(Number((e.target as HTMLInputElement).value))}
        className="w-full"
      />

      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>Very low</span>
        <span>Very high</span>
      </div>
    </div>
  );
}

type Theme = {
  id: string;
  title: string;
  impactScore: number;
  evidenceScore: number;
  frequency: number;
  group: string;
  summary: string;
};

type OutcomeDirection = 'increase' | 'decrease' | 'no change' | 'mixed' | 'unclear';

type Outcome = {
  id: string;
  name: string;
  direction: OutcomeDirection;
  shortSummary?: string;
  effectSize?: string;
  pValue?: string;
  uncertainty?: string;
  population?: string;
  timeframe?: string;
  notes?: string;
};

type Intervention = {
  id: string;
  canonicalKey: string;
  title: string;
  category: string;
  impactScore: number;
  evidenceScore: number;
  summary: string;
  studyCitation: string;
  studyTitle?: string;
  studyLinkLabel?: string;
  studyUrl?: string;
  studySummary?: string;
  outcomes?: Outcome[];
  focus?: string;
  source?: string;
  sourceNote?: string;
  briefVerdict?: string;
  mechanism?: string;
  riskBody?: string;
};

const ThemeRow = ({ theme, onOpen }: { theme: Theme; onOpen: () => void }) => {
  return (
    <div
      className="bg-white border border-gray-100 rounded-xl px-6 py-5 hover:bg-gray-50 transition-colors cursor-pointer"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onOpen();
      }}
    >
      <div className="flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{theme.title}</h3>
        </div>

        <div className="shrink-0 w-24">
          <TierBadge tier={impactLabel(theme.impactScore)} />
        </div>

        <div className="shrink-0 w-24">
          <TierBadge tier={evidenceLabel(theme.evidenceScore)} />
        </div>

        <div className="shrink-0 w-16 text-center">
          <span className="text-sm font-semibold text-gray-900">{theme.frequency}</span>
        </div>

        <div className="shrink-0">
          <ChevronRight size={18} className="text-gray-300" />
        </div>
      </div>
    </div>
  );
};

const InsightCard = ({
  title,
  category,
  impactScore,
  evidenceScore,
  summary,
  studyCitation,
  onOpen,
  showReadLink = true,
}: {
  title: string;
  category: string;
  impactScore: number;
  evidenceScore: number;
  summary: string;
  studyCitation: string;
  onOpen: () => void;
  showReadLink?: boolean;
}) => {
  const impact = impactLabel(impactScore);
  const evidence = evidenceLabel(evidenceScore);

  return (
    <div
      className="group border-b border-gray-100 py-6 hover:bg-gray-50 transition-colors cursor-pointer"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onOpen();
      }}
    >
      <div className="flex justify-between items-baseline mb-2">
        <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
          {title}
        </h3>
        <span className="text-xs font-medium uppercase tracking-wide text-gray-500 bg-gray-100 px-2 py-1 rounded">
          {category}
        </span>
      </div>

      <div className="flex items-center flex-wrap gap-x-4 gap-y-2 mb-3 text-sm">
        <div className="flex items-center gap-4">
          <TierBadge tier={impact} label="Impact" />
          <TierBadge tier={evidence} label="Evidence" />
          <span className="text-gray-400 font-normal">Study: {studyCitation}</span>
        </div>
      </div>

      <p className="text-gray-600 leading-relaxed max-w-3xl mb-3">{summary}</p>

      {showReadLink ? (
        <div className="flex items-center text-blue-600 text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
          View study outcomes <ChevronRight size={16} />
        </div>
      ) : null}
    </div>
  );
};

const ThemeDetail = ({
  theme,
  interventions,
  onBack,
  onOpenIntervention,
}: {
  theme: Theme;
  interventions: Intervention[];
  onBack: () => void;
  onOpenIntervention: (it: Intervention) => void;
}) => {
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => {
    const m = new Map<string, { key: string; title: string; category: string; items: Intervention[] }>();

    for (const it of interventions) {
      const k = it.canonicalKey || it.id;
      const existing = m.get(k);
      if (existing) existing.items.push(it);
      else m.set(k, { key: k, title: it.title, category: it.category, items: [it] });
    }

    return Array.from(m.values()).map((g) => {
      const items = [...g.items].sort((a, b) => {
        const ai = tierIndexFromScore(a.impactScore);
        const bi = tierIndexFromScore(b.impactScore);
        if (ai !== bi) return bi - ai;
        return String(a.studyCitation).localeCompare(String(b.studyCitation));
      });
      return { ...g, items };
    });
  }, [interventions]);

  return (
    <div className="max-w-5xl mx-auto bg-white min-h-screen font-sans text-gray-800 p-8">
      <button
        className="mb-6 flex items-center text-gray-500 hover:text-black cursor-pointer transition-colors"
        onClick={onBack}
        type="button"
      >
        <ArrowLeft size={16} className="mr-2" /> Back to Themes
      </button>

      <div className="mb-8 pb-6 border-b border-gray-100">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">{theme.title}</h1>
        <div className="flex items-center justify-between gap-6">
          <p className="text-gray-600 max-w-3xl">{theme.summary}</p>
          <div className="shrink-0 flex items-center gap-4">
            <TierBadge tier={impactLabel(theme.impactScore)} label="Impact" />
            <TierBadge tier={evidenceLabel(theme.evidenceScore)} label="Evidence" />
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {groups.map((g) => {
          const isMulti = g.items.length > 1;
          const open = !!openGroups[g.key];

          if (!isMulti) {
            const item = g.items[0];
            return (
              <div key={item.id} className="border border-gray-100 rounded-xl bg-white px-6">
                <InsightCard
                  title={item.title}
                  category={item.category}
                  impactScore={item.impactScore}
                  evidenceScore={item.evidenceScore}
                  summary={item.summary}
                  studyCitation={item.studyCitation}
                  onOpen={() => onOpenIntervention(item)}
                />
              </div>
            );
          }

          const aggImpact = g.items.reduce((s, it) => s + it.impactScore, 0) / g.items.length;
          const aggEvidence = g.items.reduce((s, it) => s + it.evidenceScore, 0) / g.items.length;

          return (
            <div key={g.key} className="border border-gray-100 rounded-xl bg-white">
              <div
                className="px-6 py-5 hover:bg-gray-50 transition-colors cursor-pointer"
                onClick={() => setOpenGroups((p) => ({ ...p, [g.key]: !open }))}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    setOpenGroups((p) => ({ ...p, [g.key]: !open }));
                  }
                }}
              >
                <div className="flex justify-between items-baseline mb-2">
                  <h3 className="text-lg font-semibold text-gray-900">{g.title}</h3>
                  <span className="text-xs font-medium uppercase tracking-wide text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    {g.category}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-sm">
                  <TierBadge tier={impactLabel(aggImpact)} label="Impact" />
                  <TierBadge tier={evidenceLabel(aggEvidence)} label="Evidence" />
                  <span className="text-gray-400">{g.items.length} studies</span>
                </div>

                <div className="mt-3 flex items-center text-blue-600 text-sm font-medium">
                  {open ? 'Hide studies' : 'View studies'} <ChevronRight size={16} />
                </div>
              </div>

              {open ? (
                <div className="px-6 pb-4">
                  <div className="border-t border-gray-100 pt-4 space-y-2">
                    {g.items.map((item) => (
                      <div key={item.id} className="rounded-lg border border-gray-100">
                        <InsightCard
                          title={item.title}
                          category={item.category}
                          impactScore={item.impactScore}
                          evidenceScore={item.evidenceScore}
                          summary={item.summary}
                          studyCitation={item.studyCitation}
                          onOpen={() => onOpenIntervention(item)}
                          showReadLink={true}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

function directionBadgeClasses(dir: OutcomeDirection) {
  switch (dir) {
    case 'increase':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'decrease':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    case 'no change':
      return 'bg-gray-50 text-gray-700 border-gray-200';
    case 'mixed':
      return 'bg-amber-50 text-amber-800 border-amber-200';
    case 'unclear':
    default:
      return 'bg-blue-50 text-blue-700 border-blue-200';
  }
}

function directionLabel(dir: OutcomeDirection) {
  if (dir === 'increase') return 'Increase';
  if (dir === 'decrease') return 'Decrease';
  if (dir === 'no change') return 'No change';
  if (dir === 'mixed') return 'Mixed';
  return 'Unclear';
}

const OutcomeCard = ({ outcome }: { outcome: Outcome }) => {
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-gray-900">{outcome.name}</h3>
          {outcome.shortSummary ? (
            <p className="text-gray-600 mt-1 leading-relaxed">{outcome.shortSummary}</p>
          ) : null}
        </div>

        <span
          className={`shrink-0 inline-flex items-center justify-center rounded-full border px-3 py-1 text-xs font-semibold ${directionBadgeClasses(
            outcome.direction
          )}`}
        >
          {directionLabel(outcome.direction)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <div className="space-y-2">
          <div className="flex gap-2">
            <span className="text-gray-500 w-28">Effect size</span>
            <span className="text-gray-900">{outcome.effectSize ?? 'n/a'}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-28">P-value</span>
            <span className="text-gray-900">{outcome.pValue ?? 'n/a'}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-28">Uncertainty</span>
            <span className="text-gray-900">{outcome.uncertainty ?? 'n/a'}</span>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex gap-2">
            <span className="text-gray-500 w-28">Population</span>
            <span className="text-gray-900">{outcome.population ?? 'n/a'}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-28">Timeframe</span>
            <span className="text-gray-900">{outcome.timeframe ?? 'n/a'}</span>
          </div>
          {outcome.notes ? (
            <div className="flex gap-2">
              <span className="text-gray-500 w-28">Notes</span>
              <span className="text-gray-900">{outcome.notes}</span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

const StudyOutcomes = ({ item, onBack }: { item: Intervention; onBack: () => void }) => {
  const impactLbl = impactLabel(item?.impactScore ?? 3);
  const evidenceLbl = evidenceLabel(item?.evidenceScore ?? 3);

  const title = item?.studyTitle ?? item?.studyCitation ?? 'Study';
  const outcomes = item?.outcomes ?? [];

  return (
    <div className="max-w-4xl mx-auto bg-white min-h-screen font-sans text-gray-800 p-8">
      <button
        className="mb-8 flex items-center text-gray-500 hover:text-black cursor-pointer transition-colors"
        onClick={onBack}
        type="button"
      >
        <ArrowLeft size={16} className="mr-2" /> Back
      </button>

      <div className="mb-8 pb-6 border-b border-gray-100">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-3">
              <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase">
                Study outcomes
              </span>
              <span className="text-gray-400 text-sm">{item?.focus ?? ''}</span>
            </div>

            <h1 className="text-3xl font-bold text-gray-900 mb-2">{item?.title}</h1>
            <p className="text-gray-600 leading-relaxed">
              Study outcomes from: <span className="font-medium text-gray-900">{title}</span>
            </p>

            {item?.studySummary ? (
              <p className="text-gray-600 leading-relaxed mt-3 max-w-3xl">{item.studySummary}</p>
            ) : null}

            <div className="mt-4 flex items-center gap-4">
              <TierBadge tier={impactLbl} label="Impact" />
              <TierBadge tier={evidenceLbl} label="Evidence" />
            </div>
          </div>

          <div className="shrink-0 flex flex-col items-end gap-2">
            {item?.studyUrl ? (
              <a
                className="inline-flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700"
                href={item.studyUrl}
                target="_blank"
                rel="noreferrer"
              >
                <BookOpen size={16} />
                {item.studyLinkLabel ?? 'Open paper'}
              </a>
            ) : null}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {outcomes.length === 0 ? (
          <div className="bg-gray-50 border border-gray-100 rounded-xl p-6 text-gray-600">
            No outcome data in this demo.
          </div>
        ) : (
          outcomes.map((o) => <OutcomeCard key={o.id} outcome={o} />)
        )}
      </div>
    </div>
  );
};

// Demo data
const DEMO_THEMES: Theme[] = [
  {
    id: 'finance',
    title: 'Public finance, subsidies and institutional lending',
    impactScore: 4.4,
    evidenceScore: 4.6,
    frequency: 25,
    group: 'Supply & finance drivers',
    summary:
      'Fiscal and lending instruments to expand or stabilise supply, including investment banks, long-term subsidies, interest subsidies or caps, and tax incentives.',
  },
  {
    id: 'rent',
    title: 'Rent price and indexation controls',
    impactScore: 2.6,
    evidenceScore: 2.2,
    frequency: 20,
    group: 'Regulation & tenancy',
    summary:
      'Rent caps, indexation rules, and related price control measures. Evidence suggests mixed outcomes and context sensitivity.',
  },
  {
    id: 'tenant',
    title: 'Tenant security and rental-law reform',
    impactScore: 3.8,
    evidenceScore: 2.1,
    frequency: 17,
    group: 'Regulation & tenancy',
    summary:
      'Eviction protections, contract rules, and reforms to strengthen security while managing potential market distortions.',
  },
  {
    id: 'public-housing',
    title: 'Public, non-profit and municipal housing expansion',
    impactScore: 4.2,
    evidenceScore: 3.9,
    frequency: 12,
    group: 'Supply & finance drivers',
    summary:
      'Direct delivery and expansion programmes led by public or non-profit actors, including municipal development and acquisition.',
  },
  {
    id: 'demand',
    title: 'Demand-side affordability and social safety nets',
    impactScore: 3.1,
    evidenceScore: 3.4,
    frequency: 11,
    group: 'Demand & safety nets',
    summary:
      'Household supports that affect affordability and stability, including allowances and targeted safety net measures.',
  },
  {
    id: 'anti-spec',
    title: 'Mobilising existing stock and anti-speculation tools',
    impactScore: 2.2,
    evidenceScore: 1.8,
    frequency: 9,
    group: 'Supply & allocation',
    summary:
      'Measures to reduce vacancy, mobilise underused stock, and discourage speculation or hoarding behaviours.',
  },
  {
    id: 'construction',
    title: 'Construction cost reduction, renovation and maintenance measures',
    impactScore: 4.7,
    evidenceScore: 3.6,
    frequency: 6,
    group: 'Supply & finance drivers',
    summary:
      'Cost reduction levers, renovation throughput, maintenance strategies, and technical interventions to expand effective supply.',
  },
  {
    id: 'orientation',
    title: 'Strategic supply orientation: market vs non-market approaches',
    impactScore: 3.0,
    evidenceScore: 2.8,
    frequency: 4,
    group: 'Strategy',
    summary:
      'System-level choices about the role of market delivery versus non-market models in supply expansion and allocation.',
  },
  {
    id: 'oversight',
    title: 'Oversight, governance and regulatory instruments',
    impactScore: 2.0,
    evidenceScore: 1.6,
    frequency: 3,
    group: 'Governance',
    summary:
      'Governance structures and regulatory instruments to ensure compliance, fairness, and transparency in housing systems.',
  },
  {
    id: 'landuse',
    title: 'Land-use, spatial planning and supply reservation',
    impactScore: 1.7,
    evidenceScore: 1.4,
    frequency: 3,
    group: 'Land & planning',
    summary:
      'Planning tools, zoning, land reservation, and spatial policies that constrain or enable supply expansion.',
  },
];

const DEMO_INTERVENTIONS_BY_THEME: Record<string, Intervention[]> = {
  finance: [
    {
      id: 'wbib-2019',
      canonicalKey: 'wbib',
      title: 'Re-establishment of Housing Investment Bank (WBIB)',
      category: 'Policy proposal',
      impactScore: 4.0,
      evidenceScore: 3.0,
      summary:
        'Dedicated housing banks can cushion rising construction costs, improving project viability during market volatility.',
      studyCitation: 'Müller et al. (2019)',
      focus: 'Austria focus',
      source: 'Müller et al. (2019)',
      sourceNote: 'Single-study intervention record (demo).',
      studyTitle: 'WBIB programme evaluation (Müller et al., 2019)',
      studySummary:
        'Single-study evaluation of a dedicated housing investment bank mechanism, focusing on social housing viability under cost and rate volatility.',
      studyUrl: 'https://example.com/paper/wbib-2019',
      studyLinkLabel: 'Open paper',
      outcomes: [
        {
          id: 'starts',
          name: 'Housing starts (social/non-profit)',
          direction: 'increase',
          shortSummary: 'Observed increase in starts for eligible projects during tightening cycles.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Social housing sector',
          timeframe: '12 months',
        },
        {
          id: 'costs',
          name: 'Financing cost volatility',
          direction: 'decrease',
          shortSummary: 'Reduced exposure to rate shocks via counter-cyclical lending conditions.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Non-profit developers',
          timeframe: '24 months',
        },
        {
          id: 'delivery',
          name: 'Project completion rate',
          direction: 'unclear',
          shortSummary: 'Evidence on completion rates is mixed and sensitive to eligibility rules.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Eligible projects',
          timeframe: '18 months',
          notes: 'Design and governance appear to mediate effects.',
        },
      ],
      mechanism:
        'A dedicated institution provides long-term, counter-cyclical lending that smooths financing conditions for social and affordable housing delivery.',
      riskBody:
        'Fiscal exposure depends on mandate design and balance sheet risk. Governance and underwriting standards become central to limiting contingent liabilities.',
    },
    {
      id: 'rate-subsidy-2018',
      canonicalKey: 'interest-rate-subsidy',
      title: 'Interest rate subsidy programme',
      category: 'Financial support',
      impactScore: 4.0,
      evidenceScore: 4.0,
      summary:
        'A subsidised lending rate reduced financing costs for eligible developments during tightening cycles.',
      studyCitation: 'Schmidt and Bauer (2018)',
      focus: 'Austria focus',
      source: 'Schmidt and Bauer (2018)',
      sourceNote: 'Single-study intervention record (demo).',
      studyTitle: 'Rate subsidy instrument (Schmidt and Bauer, 2018)',
      studySummary:
        'Study reports outcomes of a subsidised lending rate for eligible developments during a high-rate period.',
      studyUrl: 'https://example.com/paper/rate-subsidy-2018',
      studyLinkLabel: 'Open paper',
      outcomes: [
        {
          id: 'starts',
          name: 'Housing starts (eligible projects)',
          direction: 'increase',
          shortSummary: 'Starts increased relative to comparator regions during the subsidy period.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Eligible developments',
          timeframe: '12 months',
        },
        {
          id: 'cost',
          name: 'Effective borrowing cost',
          direction: 'decrease',
          shortSummary: 'Lower effective rate compared to market benchmarks for participants.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Non-profit builders',
          timeframe: 'During loan term',
        },
        {
          id: 'fiscal',
          name: 'Fiscal exposure',
          direction: 'increase',
          shortSummary: 'Public cost rises with sustained high market rates.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Public budget',
          timeframe: 'Multi-year',
          notes: 'Budget commitment accumulates over time.',
        },
      ],
      briefVerdict:
        'Study-level finding: reduced cost of capital for non-profit builders during high-rate periods.',
      mechanism:
        'Subsidies reduce the effective cost of capital by covering the delta between market rates and a target rate.',
      riskBody:
        'Rate subsidies create long-term budget commitments if high rates persist, increasing fiscal exposure.',
    },
    {
      id: 'rate-subsidy-2020',
      canonicalKey: 'interest-rate-subsidy',
      title: 'Interest rate subsidy programme',
      category: 'Financial support',
      impactScore: 4.0,
      evidenceScore: 3.0,
      summary: 'A time-limited subsidy maintained project viability by lowering effective borrowing costs.',
      studyCitation: 'Klein (2020)',
      focus: 'Austria focus',
      source: 'Klein (2020)',
      sourceNote: 'Single-study intervention record (demo).',
      studyTitle: 'Time-limited rate subsidy (Klein, 2020)',
      studySummary:
        'Time-limited subsidy designed to preserve project viability by lowering effective borrowing costs.',
      studyUrl: 'https://example.com/paper/rate-subsidy-2020',
      studyLinkLabel: 'Open paper',
      outcomes: [
        {
          id: 'viability',
          name: 'Project viability (financial)',
          direction: 'increase',
          shortSummary: 'Improved viability for marginal projects during the subsidy window.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Eligible projects',
          timeframe: 'Subsidy window',
        },
        {
          id: 'prices',
          name: 'Land price pass-through',
          direction: 'mixed',
          shortSummary: 'Some evidence of partial capitalisation into land prices in constrained areas.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Constrained metros',
          timeframe: '24 months',
        },
      ],
      mechanism: 'Targeted subsidies improve project cashflow and reduce hurdle rates during volatile periods.',
      riskBody: 'May be captured via higher land prices if supply constraints are binding.',
    },
    {
      id: 'rate-subsidy-2022',
      canonicalKey: 'interest-rate-subsidy',
      title: 'Interest rate subsidy programme',
      category: 'Financial support',
      impactScore: 3.0,
      evidenceScore: 4.0,
      summary: 'A capped-rate instrument supported starts for eligible projects when market rates rose sharply.',
      studyCitation: 'Wagner et al. (2022)',
      focus: 'Austria focus',
      source: 'Wagner et al. (2022)',
      sourceNote: 'Single-study intervention record (demo).',
      studyTitle: 'Capped-rate instrument (Wagner et al., 2022)',
      studySummary:
        'Capped-rate instrument supporting starts by reducing downside financing risk when market rates rise sharply.',
      studyUrl: 'https://example.com/paper/rate-subsidy-2022',
      studyLinkLabel: 'Open paper',
      outcomes: [
        {
          id: 'starts',
          name: 'Starts for marginal developments',
          direction: 'increase',
          shortSummary: 'Improved starts for projects near viability thresholds.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Marginal projects',
          timeframe: '12 months',
        },
        {
          id: 'targeting',
          name: 'Targeting efficiency',
          direction: 'unclear',
          shortSummary: 'Unclear whether benefits concentrated on additional supply versus windfalls.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Programme participants',
          timeframe: '12 months',
        },
      ],
      mechanism: 'A cap reduces downside financing risk, preserving viability of marginal developments.',
      riskBody: 'Design needs clear eligibility rules to avoid windfall gains and excessive fiscal liability.',
    },
    {
      id: 'fees-2017',
      canonicalKey: 'land-registration-fee',
      title: 'Elimination of land registration fees',
      category: 'Policy change',
      impactScore: 3.0,
      evidenceScore: 2.0,
      summary:
        'Lowers friction costs for buyers and self-builders, but evidence suggests limited effects on total stock in tight metros.',
      studyCitation: 'Huber (2017)',
      focus: 'Austria focus',
      source: 'Huber (2017)',
      sourceNote: 'Single-study intervention record (demo).',
      studyTitle: 'Land fee removal assessment (Huber, 2017)',
      studySummary:
        'Assessment of eliminating registration fees to reduce up-front transaction costs for buyers and builders.',
      studyUrl: 'https://example.com/paper/fees-2017',
      studyLinkLabel: 'Open paper',
      outcomes: [
        {
          id: 'takeup',
          name: 'Home purchase timing',
          direction: 'mixed',
          shortSummary: 'Some evidence of earlier purchases among marginal households; effects vary by market.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Marginal households',
          timeframe: '12 months',
        },
        {
          id: 'prices',
          name: 'House prices',
          direction: 'increase',
          shortSummary: 'Potential partial capitalisation into prices where supply is inelastic.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Tight metros',
          timeframe: '24 months',
        },
        {
          id: 'stock',
          name: 'Total housing stock',
          direction: 'no change',
          shortSummary: 'No meaningful change in total stock detected over the evaluation period.',
          effectSize: 'n/a',
          pValue: 'n/a',
          uncertainty: 'n/a',
          population: 'Metropolitan stock',
          timeframe: '24 months',
        },
      ],
      mechanism: 'Reduces up-front transaction costs, potentially advancing purchase timing for marginal households.',
      riskBody:
        'Can capitalise into prices where supply is inelastic, reducing affordability gains and creating regressive distributional effects.',
    },
  ],
};

export default function PolicyDashboardPreview() {
  const [route, setRoute] = useState<'themes' | 'theme' | 'study'>('themes');
  const [selectedTheme, setSelectedTheme] = useState<Theme | null>(null);
  const [selectedIntervention, setSelectedIntervention] = useState<Intervention | null>(null);

  // Filters
  const [minImpact, setMinImpact] = useState(1);
  const [minEvidence, setMinEvidence] = useState(1);
  const [themeFilter, setThemeFilter] = useState('All');

  // Sort
  const [sortBy, setSortBy] = useState<'frequency' | 'impact' | 'evidence'>('frequency');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const themes = DEMO_THEMES;
  const interventionsByTheme = DEMO_INTERVENTIONS_BY_THEME;

  const themeOptions = useMemo(() => {
    const groups = Array.from(new Set(themes.map((t) => t.group)));
    return ['All', ...groups];
  }, [themes]);

  const filteredThemes = useMemo(() => {
    const base = themes
      .filter((t) => tierIndexFromScore(t.impactScore) >= minImpact)
      .filter((t) => tierIndexFromScore(t.evidenceScore) >= minEvidence)
      .filter((t) => (themeFilter === 'All' ? true : t.group === themeFilter));

    const sorted = [...base].sort((a, b) => {
      let av: number;
      let bv: number;

      if (sortBy === 'impact') {
        av = tierIndexFromScore(a.impactScore);
        bv = tierIndexFromScore(b.impactScore);
      } else if (sortBy === 'evidence') {
        av = tierIndexFromScore(a.evidenceScore);
        bv = tierIndexFromScore(b.evidenceScore);
      } else {
        av = a.frequency;
        bv = b.frequency;
      }

      return sortDir === 'asc' ? av - bv : bv - av;
    });

    return sorted;
  }, [themes, minImpact, minEvidence, themeFilter, sortBy, sortDir]);

  // Routing
  if (route === 'theme' && selectedTheme) {
    const interventions = interventionsByTheme[selectedTheme.id] ?? [];
    return (
      <ThemeDetail
        theme={selectedTheme}
        interventions={interventions}
        onBack={() => {
          setRoute('themes');
          setSelectedTheme(null);
        }}
        onOpenIntervention={(it) => {
          setSelectedIntervention(it);
          setRoute('study');
        }}
      />
    );
  }

  if (route === 'study' && selectedIntervention) {
    return (
      <StudyOutcomes
        item={selectedIntervention}
        onBack={() => {
          setRoute('theme');
          setSelectedIntervention(null);
        }}
      />
    );
  }

  // Themes page
  return (
    <div className="min-h-screen bg-gray-50 font-sans text-gray-900 p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-8 pb-6 border-b border-gray-200">
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Interventions</h1>
              <p className="text-gray-600 max-w-3xl">
                Explore themes, then drill into representative intervention deep dives. Use filters to surface
                higher-impact and stronger-evidence areas.
              </p>
            </div>
            <button className="flex items-center text-sm font-medium text-gray-700 hover:text-black border border-gray-300 rounded-md px-3 py-1.5 transition-colors">
              <Download size={14} className="mr-2" /> Download
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white border border-gray-100 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-2 text-gray-500 mb-4">
            <SlidersHorizontal size={16} />
            <span className="text-sm font-medium">Filters</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <RangeFilter label="Min Impact" value={minImpact} onChange={setMinImpact} />
            <RangeFilter label="Min Evidence" value={minEvidence} onChange={setMinEvidence} />

            <div className="w-full">
              <div className="text-sm font-medium text-gray-900 mb-2">Theme group</div>
              <select
                value={themeFilter}
                onChange={(e) => setThemeFilter(e.target.value)}
                className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm"
              >
                {themeOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-2">
            <span className="text-sm text-gray-500 mr-2">Sort by:</span>
            {(['frequency', 'impact', 'evidence'] as const).map((s) => (
              <button
                key={s}
                onClick={() => {
                  if (sortBy === s) {
                    setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
                  } else {
                    setSortBy(s);
                    setSortDir('desc');
                  }
                }}
                className={`text-sm px-3 py-1.5 rounded-md font-medium transition-colors ${
                  sortBy === s
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100 border border-gray-200'
                }`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}{sortBy === s ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
              </button>
            ))}
          </div>
        </div>

        {/* Header row */}
        <div className="hidden md:flex items-center gap-4 px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <div className="flex-1">Theme</div>
          <div className="shrink-0 w-24">Impact</div>
          <div className="shrink-0 w-24">Evidence</div>
          <div className="shrink-0 w-16 text-center">Studies</div>
          <div className="shrink-0 w-[18px]"></div>
        </div>

        {/* Theme list */}
        <div className="space-y-2">
          {filteredThemes.length === 0 ? (
            <div className="bg-white border border-gray-100 rounded-xl px-6 py-8 text-center text-gray-500">
              No themes match your filters. Try adjusting the minimum impact or evidence levels.
            </div>
          ) : (
            filteredThemes.map((theme) => (
              <ThemeRow
                key={theme.id}
                theme={theme}
                onOpen={() => {
                  setSelectedTheme(theme);
                  setRoute('theme');
                }}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
