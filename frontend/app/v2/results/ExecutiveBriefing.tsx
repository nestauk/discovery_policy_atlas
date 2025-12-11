'use client'

import { useMemo, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { ExternalLink, BookOpen, FileText, Quote, CheckCircle, Lightbulb, AlertTriangle, ChevronRight, Download } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { 
  CitationInfo, 
  EvidenceCoverageSnapshot, 
  StructuredBriefing,
  InterventionTableRow,
  RecommendationItem,
  TopCitationItem,
  BackgroundSection,
} from "@/types/search";

interface ExecutiveBriefingProps {
  briefing: string;
  structuredBriefing?: StructuredBriefing;
  citationMap?: Record<string, CitationInfo>;
  evidenceCoverage?: EvidenceCoverageSnapshot;
  documents?: Array<{
    id: string;
    doc_id?: string;
    title?: string;
    supporting_quote?: string;
    landing_page_url?: string;
    pdf_url?: string;
    year?: number;
    authors?: string[];
  }>;
  onCitationClick?: (docId: string) => void;
}

// Study type normalisation
const STUDY_TYPE_LABELS: Record<string, string> = {
  'a': 'Systematic Review', 'b': 'Meta-Analysis', 'c': 'RCT',
  'd': 'Quasi-Experimental', 'e': 'Cohort Study', 'f': 'Case-Control',
  'g': 'Cross-Sectional', 'h': 'Case Study', 'i': 'Qualitative', 'j': 'Expert Opinion',
  'systematic review': 'Systematic Review', 'meta-analysis': 'Meta-Analysis',
  'rct': 'RCT', 'randomised controlled trial': 'RCT', 'randomized controlled trial': 'RCT',
  'quasi-experimental': 'Quasi-Experimental', 'cohort': 'Cohort Study',
  'case-control': 'Case-Control', 'cross-sectional': 'Cross-Sectional',
  'case study': 'Case Study', 'qualitative': 'Qualitative',
};

function normalizeStudyType(type: string): string {
  return STUDY_TYPE_LABELS[type.toLowerCase().trim()] || type;
}

// Citation lookup function type
type CitationLookupFn = (key: string | number) => CitationInfo | undefined;

function buildCitationLookup(citationMap?: Record<string, CitationInfo>): CitationLookupFn {
  if (!citationMap) return () => undefined;
  
  const byNumber: Record<number, CitationInfo> = {};
  Object.values(citationMap).forEach(info => {
    if (info.citation_number) byNumber[info.citation_number] = info;
  });
  
  return (key: string | number): CitationInfo | undefined => {
    if (typeof key === 'number') return byNumber[key];
    
    const numMatch = key.match(/^\[(\d+)\]$/);
    if (numMatch) return byNumber[parseInt(numMatch[1], 10)];
    
    return citationMap[key] || citationMap[key.replace(/^\[|\]$/g, '')] || citationMap[`[${key}]`];
  };
}

// Shared citation rendering utility
function useRenderCitations(lookupCitation: CitationLookupFn, onCitationClick?: (docId: string) => void) {
  return useCallback((text: string, keyPrefix: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    const pattern = /\[(\d+)\]/g;
    let lastIndex = 0;
    let match;
    let keyIdx = 0;

    while ((match = pattern.exec(text)) !== null) {
      if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
      
      const citNum = parseInt(match[1], 10);
      const citInfo = lookupCitation(citNum);
      
      parts.push(
        <CitationLink
          key={`${keyPrefix}-${keyIdx++}`}
          citationKey={`[${citNum}]`}
          citationNumber={citNum}
          citationInfo={citInfo}
          onCitationClick={onCitationClick}
        />
      );
      
      lastIndex = match.index + match[0].length;
    }
    
    if (lastIndex < text.length) parts.push(text.slice(lastIndex));
    return parts;
  }, [lookupCitation, onCitationClick]);
}

// ============================================================================
// Citation Link
// ============================================================================

interface CitationLinkProps {
  citationKey: string;
  citationNumber?: number;
  citationInfo?: CitationInfo;
  onCitationClick?: (docId: string) => void;
}

function CitationLink({ citationKey, citationNumber, citationInfo, onCitationClick }: CitationLinkProps) {
  const url = citationInfo?.url;
  const title = citationInfo?.title || "Unknown source";
  const quote = citationInfo?.supporting_quote;
  const docId = citationInfo?.analysis_document_id;
  const displayText = citationNumber ? `[${citationNumber}]` : citationKey;

  const handleClick = useCallback((e: React.MouseEvent) => {
    if (url) return;
    if (onCitationClick && docId) {
      e.preventDefault();
      onCitationClick(docId);
    }
  }, [onCitationClick, docId, url]);

  const tooltipContent = (
    <div className="space-y-2 max-w-sm">
      <div className="font-medium text-sm leading-tight">{title}</div>
      {citationInfo?.author_short && citationInfo?.year && (
        <div className="text-xs opacity-80">{citationInfo.author_short}, {citationInfo.year}</div>
      )}
      {quote && (
        <div className="mt-2 pt-2 border-t border-white/20">
          <div className="flex items-start gap-1.5">
            <Quote className="h-3 w-3 mt-0.5 opacity-60 flex-shrink-0" />
            <div className="text-xs italic opacity-90 leading-relaxed">
              {quote.length > 200 ? quote.substring(0, 200) + "…" : quote}
            </div>
          </div>
        </div>
      )}
      {url && (
        <div className="text-xs text-blue-300 flex items-center gap-1 pt-1">
          <ExternalLink className="h-3 w-3" />
          Click to view source
        </div>
      )}
    </div>
  );

  const linkElement = url ? (
    <a href={url} target="_blank" rel="noopener noreferrer" onClick={handleClick}
       className="text-blue-600 hover:text-blue-800 hover:underline cursor-pointer font-medium transition-colors">
      {displayText}
    </a>
  ) : (
    <span onClick={handleClick}
          className={`text-blue-600 font-medium ${onCitationClick && docId ? 'cursor-pointer hover:underline' : ''}`}>
      {displayText}
    </span>
  );

  return <Tooltip content={tooltipContent}>{linkElement}</Tooltip>;
}

// ============================================================================
// Evidence Coverage Badge
// ============================================================================

function EvidenceCoverageBadge({ coverage }: { coverage: EvidenceCoverageSnapshot }) {
  const strengthColors: Record<string, string> = {
    'High': 'bg-green-100 text-green-800 border-green-200',
    'Moderate': 'bg-amber-100 text-amber-800 border-amber-200',
    'Low': 'bg-red-100 text-red-800 border-red-200',
    'Unknown': 'bg-slate-100 text-slate-800 border-slate-200',
  };

  const normalizedStudyTypes = useMemo(() => {
    const normalized: Record<string, number> = {};
    Object.entries(coverage.study_types || {}).forEach(([type, count]) => {
      const label = normalizeStudyType(type);
      normalized[label] = (normalized[label] || 0) + count;
    });
    return normalized;
  }, [coverage.study_types]);

  const studyTypeSummary = Object.entries(normalizedStudyTypes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([type, count]) => `${count} ${type}`)
    .join(', ') || 'Various';

  const countriesEntries = Object.entries(coverage.countries || {}).sort((a, b) => b[1] - a[1]);
  const topCountries = countriesEntries.slice(0, 3).map(([c]) => c);
  const remainingCount = countriesEntries.length - 3;
  
  const countrySummary = countriesEntries.length === 0 ? 'Unknown'
    : remainingCount > 0 ? `${topCountries.join(', ')} +${remainingCount} more`
    : topCountries.join(', ');

  const sourceTypeSummary = Object.entries(coverage.source_types || {})
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => `${count} ${type}`)
    .join(', ') || 'Various';

  const hasRCTs = Object.keys(normalizedStudyTypes).some(t => 
    t.toLowerCase().includes('rct') || t.toLowerCase().includes('randomised'));
  const hasMetas = Object.keys(normalizedStudyTypes).some(t => 
    t.toLowerCase().includes('meta'));

  const filteredGaps = (coverage.gaps || []).filter(gap => {
    if (gap.toLowerCase().includes('no rcts') && hasRCTs) return false;
    if (gap.toLowerCase().includes('no meta') && hasMetas) return false;
    return true;
  });

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-6">
      <div className="flex items-center gap-2 mb-3">
        <BookOpen className="h-4 w-4 text-slate-500" />
        <span className="font-medium text-sm text-slate-700">Evidence Base</span>
        <Badge className={`ml-auto ${strengthColors[coverage.overall_strength] || strengthColors['Unknown']}`}>
          {coverage.overall_strength} Confidence
        </Badge>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Sources</div>
          <div className="font-semibold text-slate-800">{coverage.total_sources} documents</div>
        </div>
        <div>
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Source Types</div>
          <div className="text-slate-700">{sourceTypeSummary}</div>
        </div>
        <div>
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Study Types</div>
          <div className="text-slate-700">{studyTypeSummary}</div>
        </div>
        <div>
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Geographic Coverage</div>
          <div className="text-slate-700">{countrySummary}</div>
        </div>
      </div>
      {filteredGaps.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-200">
          <div className="text-xs text-amber-700 flex items-start gap-1">
            <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
            <span className="font-medium">Evidence gaps:</span>
            <span>{filteredGaps.slice(0, 2).join('; ')}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Structured Briefing Components
// ============================================================================

function CoreAnswerSection({ coreAnswer }: { coreAnswer: StructuredBriefing['core_answer'] }) {
  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-5 mb-6">
      <div className="flex items-start gap-3">
        <Lightbulb className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
        <div>
          <div className="text-sm text-blue-600 font-medium mb-2">Core Finding</div>
          <p className="text-slate-800 font-medium leading-relaxed">{coreAnswer.answer}</p>
          {coreAnswer.directive && (
            <div className="mt-3 pt-3 border-t border-blue-200">
              <div className="flex items-start gap-2">
                <ChevronRight className="h-4 w-4 text-blue-600 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-slate-700">{coreAnswer.directive}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function BackgroundSectionComponent({ background, renderCitations }: { 
  background: BackgroundSection; 
  renderCitations: (text: string, prefix: string) => React.ReactNode[];
}) {
  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold text-slate-800 mb-3">{background.title}</h3>
      <div className="space-y-3">
        {background.paragraphs.map((para, idx) => (
          <p key={idx} className="text-slate-700 leading-relaxed">
            {renderCitations(para, `bg-${idx}`)}
          </p>
        ))}
      </div>
    </div>
  );
}

function InterventionsTable({ interventions, lookupCitation, onCitationClick, renderCitations }: { 
  interventions: InterventionTableRow[];
  lookupCitation: CitationLookupFn;
  onCitationClick?: (docId: string) => void;
  renderCitations: (text: string, prefix: string) => React.ReactNode[];
}) {
  if (!interventions.length) return null;

  const effectBadgeColor = (direction: string) => {
    switch (direction) {
      case 'increase': return 'bg-emerald-700 text-white';
      case 'decrease': return 'bg-purple-700 text-white';
      case 'mixed': return 'bg-amber-600 text-white';
      case 'no change': return 'bg-slate-500 text-white';
      default: return 'bg-slate-400 text-white';
    }
  };

  const formatEffectCounts = (pos: number, neg: number, nul: number) => {
    const parts = [];
    if (pos > 0) parts.push(`${pos}↑`);
    if (neg > 0) parts.push(`${neg}↓`);
    if (nul > 0) parts.push(`${nul}—`);
    return parts.join(' ') || '—';
  };

  // Render markdown-style bold in context/impact text
  const renderFormattedText = (text: string, prefix: string) => {
    // First render citations, then handle bold
    const parts = renderCitations(text, prefix);
    return parts.map((part, i) => {
      if (typeof part !== 'string') return part;
      // Handle **bold** markdown
      const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
      return boldParts.map((bp, j) => {
        if (bp.startsWith('**') && bp.endsWith('**')) {
          return <strong key={`${i}-${j}`} className="font-semibold text-slate-800">{bp.slice(2, -2)}</strong>;
        }
        return bp;
      });
    });
  };

  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold text-slate-800 mb-3">Key Interventions</h3>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider" style={{width: '18%'}}>Intervention</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider" style={{width: '22%'}}>Context</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider" style={{width: '45%'}}>Impact & Outcomes</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider" style={{width: '15%'}}>Sources</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-200">
            {interventions.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-50 align-top">
                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                  {row.intervention_name}
                </td>
                <td className="px-4 py-3 text-sm text-slate-600">
                  <div className="space-y-1">
                    {renderFormattedText(row.context || 'Various settings', `ctx-${idx}`)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {/* Impact narrative */}
                  {row.impact_narrative && (
                    <div className="text-sm text-slate-700 mb-2">
                      {renderFormattedText(row.impact_narrative, `imp-${idx}`)}
                    </div>
                  )}
                  {/* Outcome effects */}
                  {row.outcome_effects && row.outcome_effects.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-1">
                      {[...row.outcome_effects]
                        .sort((a, b) => (b.positive_count + b.negative_count + b.null_count) - (a.positive_count + a.negative_count + a.null_count))
                        .slice(0, 3)
                        .map((effect, effIdx) => (
                        <div key={effIdx} className="inline-flex items-start gap-1 text-xs whitespace-normal break-words max-w-full">
                          <Badge variant="outline" className={`${effectBadgeColor(effect.direction)} text-xs px-1.5 py-0.5 border-transparent`}>
                            {effect.direction}
                          </Badge>
                          <span className="text-slate-600 whitespace-normal break-words" title={effect.outcome_theme}>
                            {effect.outcome_theme}
                          </span>
                          <span className="text-slate-400">
                            {formatEffectCounts(effect.positive_count, effect.negative_count, effect.null_count)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {!row.impact_narrative && (!row.outcome_effects || row.outcome_effects.length === 0) && (
                    <span className="text-sm text-slate-400 italic">No impact data</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm">
                  <div className="flex flex-wrap gap-1">
                    {row.citation_numbers.map((num) => (
                      <CitationLink
                        key={`int-${idx}-${num}`}
                        citationKey={`[${num}]`}
                        citationNumber={num}
                        citationInfo={lookupCitation(num)}
                        onCitationClick={onCitationClick}
                      />
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RecommendationsList({ recommendations, renderCitations }: { 
  recommendations: RecommendationItem[];
  renderCitations: (text: string, prefix: string) => React.ReactNode[];
}) {
  if (!recommendations.length) return null;

  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <CheckCircle className="h-5 w-5 text-green-600" />
        Recommendations
      </h3>
      <div className="space-y-3">
        {recommendations.map((rec) => (
          <div key={rec.number} className="flex gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-semibold flex items-center justify-center">
              {rec.number}
            </div>
            <div className="flex-1">
              <div className="font-semibold text-slate-800">{rec.title}</div>
              <p className="text-sm text-slate-700 mt-1">{renderCitations(rec.description, `rec-${rec.number}`)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopCitationsList({ citations, lookupCitation, onCitationClick }: { 
  citations: TopCitationItem[];
  lookupCitation: CitationLookupFn;
  onCitationClick?: (docId: string) => void;
}) {
  if (!citations.length) return null;

  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <BookOpen className="h-5 w-5 text-blue-600" />
        Key Sources for Review
      </h3>
      <div className="space-y-2">
        {citations.map((cit) => (
          <div key={cit.citation_number} className="flex items-start gap-3 p-3 bg-white rounded-lg border border-slate-200 hover:border-blue-300 transition-colors">
            <CitationLink
              citationKey={`[${cit.citation_number}]`}
              citationNumber={cit.citation_number}
              citationInfo={lookupCitation(cit.citation_number)}
              onCitationClick={onCitationClick}
            />
            <div className="flex-1 min-w-0">
              <div className="font-medium text-slate-800 truncate">{cit.title}</div>
              <div className="text-xs text-slate-500">{cit.author_year}</div>
              {cit.reason && <div className="text-xs text-slate-600 mt-1">{cit.reason}</div>}
            </div>
            {cit.url && (
              <a href={cit.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800">
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function ExecutiveBriefing({ 
  briefing, 
  structuredBriefing,
  citationMap, 
  evidenceCoverage,
  onCitationClick 
}: ExecutiveBriefingProps) {
  const lookupCitation = useMemo(() => buildCitationLookup(citationMap), [citationMap]);
  const renderCitations = useRenderCitations(lookupCitation, onCitationClick);

  const handleDownloadPdf = useCallback(() => {
    const sanitize = (text?: string) =>
      (text || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    // Allow basic bold markdown and convert [N] to clickable citations
    const linkCitations = (text: string) =>
      text.replace(/\[(\d+)\]/g, (_m, g1) => {
        const num = parseInt(g1, 10);
        const citInfo = lookupCitation(num);
        const href = citInfo?.url ? sanitize(citInfo.url) : `#cite-${num}`;
        return `<a class="pill-inline" href="${href}" target="_blank" rel="noopener">[${num}]</a>`;
      });

    const rich = (text?: string) => {
      const safe = sanitize(text);
      const withBold = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      return linkCitations(withBold);
    };

    const badgeForDirection = (direction: string) => {
      const colors: Record<string, string> = {
        increase: "#047857", // deep green
        decrease: "#6b21a8", // deep purple
        mixed: "#d97706", // amber
        "no change": "#6b7280", // grey
        default: "#6b7280",
      };
      return `<span style="display:inline-block;padding:2px 6px;border-radius:6px;font-size:11px;font-weight:600;color:#fff;background:${colors[direction] || colors.default};">${direction}</span>`;
    };

    const renderInterventions = () => {
      if (!structuredBriefing?.interventions_table?.length) return "";

      const cards = structuredBriefing.interventions_table
        .map((row) => {
          const citations = (row.citation_numbers || [])
            .map((c) => {
              const citInfo = lookupCitation(c);
              const href = citInfo?.url ? sanitize(citInfo.url) : `#cite-${c}`;
              const title = citInfo?.title ? sanitize(citInfo.title) : "";
              return `<a class="pill" href="${href}" target="_blank" rel="noopener" title="${title}">[${c}]</a>`;
            })
            .join("");
          const outcomes = (row.outcome_effects || [])
            .sort(
              (a, b) =>
                b.positive_count +
                b.negative_count +
                b.null_count -
                (a.positive_count + a.negative_count + a.null_count)
            )
            .slice(0, 3)
            .map(
              (o) =>
                `<div class="outcome-chip">
                   ${badgeForDirection(o.direction)}
                   <div class="outcome-text">
                     <div class="outcome-name">${sanitize(o.outcome_theme)}</div>
                     <div class="outcome-counts">${o.positive_count}↑ ${o.negative_count}↓ ${o.null_count}—</div>
                   </div>
                 </div>`
            )
            .join("");

          return `
            <div class="card card-tight">
              <div class="card-heading">${sanitize(row.intervention_name)}</div>
              <div class="card-row">
                <div class="card-label">Context</div>
              <div class="card-value">${rich(row.context)}</div>
              </div>
              ${
                row.impact_narrative
                  ? `<div class="card-row">
                      <div class="card-label">Impact</div>
                      <div class="card-value">${rich(row.impact_narrative)}</div>
                    </div>`
                  : ""
              }
              ${
                outcomes
                  ? `<div class="card-row">
                      <div class="card-label">Outcomes</div>
                      <div class="card-value outcome-wrap">${outcomes}</div>
                    </div>`
                  : ""
              }
              ${
                citations
                  ? `<div class="card-row">
                      <div class="card-label">Sources</div>
                      <div class="card-value citations">${citations}</div>
                    </div>`
                  : ""
              }
            </div>
          `;
        })
        .join("");

      return `
        <div class="card">
          <div class="card-title">Key Interventions</div>
          <div class="card-grid">
            ${cards}
          </div>
        </div>
      `;
    };

    const renderRecommendations = () => {
      if (!structuredBriefing?.recommendations?.length) return "";
      const items = structuredBriefing.recommendations
            .map(
              (r) =>
                `<div class="chip-row">
              <div class="chip-num">${r.number}</div>
              <div>
                <div class="chip-title">${rich(r.title)}</div>
                <div class="chip-body">${rich(r.description)}</div>
              </div>
            </div>`
            )
        .join("");
      return `
        <div class="card">
          <div class="card-title">Recommendations</div>
          ${items}
        </div>
      `;
    };

    const renderEvidenceSnapshot = () => {
      if (!evidenceCoverage) return "";
      const strengths: Record<string, string> = {
        High: "#bbf7d0",
        Moderate: "#fef3c7",
        Low: "#fecdd3",
        Unknown: "#e5e7eb",
      };
      const strengthColor = strengths[evidenceCoverage.overall_strength] || strengths.Unknown;
      const studyTypes = Object.entries(evidenceCoverage.study_types || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([k, v]) => `${v} ${sanitize(k)}`)
        .join(", ") || "Various";
      const countryEntries = Object.entries(evidenceCoverage.countries || {}).sort((a, b) => b[1] - a[1]);
      const topCountries = countryEntries.slice(0, 3).map(([c]) => sanitize(c)).join(", ") || "Unknown";
      return `
        <div class="card">
          <div class="card-title">Evidence Base</div>
          <div class="badge" style="background:${strengthColor};color:#0f172a;">${evidenceCoverage.overall_strength} confidence</div>
          <div class="snapshot-grid">
            <div>
              <div class="label">Sources</div>
              <div class="value">${evidenceCoverage.total_sources} documents</div>
            </div>
            <div>
              <div class="label">Study Types</div>
              <div class="value">${studyTypes}</div>
            </div>
            <div>
              <div class="label">Geographic Coverage</div>
              <div class="value">${topCountries}</div>
            </div>
          </div>
        </div>
      `;
    };

    const renderBackground = () => {
      if (!structuredBriefing?.background_section) return "";
      const paras =
        structuredBriefing.background_section.paragraphs
          .map((p) => `<p>${rich(p)}</p>`)
          .join("") || "";
      return `
        <div class="card">
          <div class="card-title">${sanitize(structuredBriefing.background_section.title)}</div>
          ${paras}
        </div>
      `;
    };

    const renderQuestion = () => {
      const q = structuredBriefing?.core_answer?.query || "";
      if (!q) return "";
      return `
        <div class="card">
          <div class="card-title">Research Question</div>
          <p class="question-text">${rich(q)}</p>
        </div>
      `;
    };

    const structuredHtml = structuredBriefing
      ? `
        ${renderQuestion()}
        <div class="hero">
          <div class="hero-icon">✦</div>
          <div>
            <div class="hero-label">Core Answer</div>
            <div class="hero-answer">${rich(structuredBriefing?.core_answer?.answer)}</div>
            ${
              structuredBriefing?.core_answer?.directive
                ? `<div class="hero-directive">${rich(structuredBriefing.core_answer.directive)}</div>`
                : ""
            }
          </div>
        </div>
        ${renderEvidenceSnapshot()}
        ${renderBackground()}
        ${renderInterventions()}
        ${renderRecommendations()}
      `
      : `<div style="white-space: pre-wrap;">${sanitize(briefing)}</div>`;

    const html = `
      <html>
        <head>
          <meta charset="utf-8" />
          <title>Executive Summary</title>
          <style>
            body { font-family: "Inter", Arial, sans-serif; line-height: 1.65; padding: 28px; color: #0f172a; background: #f8fafc; }
            h1 { font-size: 24px; margin-bottom: 16px; }
            .card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 16px 18px; margin-bottom: 18px; box-shadow: 0 2px 4px rgba(15,23,42,0.06); }
            .card-tight { padding: 14px 16px; }
            .card-title { font-size: 16px; font-weight: 700; margin-bottom: 10px; display:flex; align-items:center; gap:8px; color:#0f172a; }
            .card-heading { font-size: 15px; font-weight: 700; margin-bottom: 10px; color:#0f172a; }
            .card-row { display:flex; gap:10px; margin-bottom:8px; }
            .card-label { width: 90px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.02em; color:#6b7280; flex-shrink:0; }
            .card-value { font-size: 13px; color:#111827; }
            .outcome-wrap { display:flex; flex-wrap:wrap; gap:8px; }
            .outcome-chip { display:flex; align-items:center; gap:6px; padding:6px 8px; border:1px solid #e2e8f0; border-radius:10px; background:#f8fafc; }
            .outcome-text { display:flex; flex-direction:column; gap:2px; }
            .outcome-name { font-weight:600; color:#0f172a; }
            .outcome-counts { font-size:11px; color:#6b7280; }
            .pill { display:inline-block; padding:4px 8px; margin:2px; background:#e0e7ff; color:#1d4ed8; border-radius:9999px; font-weight:600; font-size:11px; }
            .citations { display:flex; flex-wrap:wrap; gap:4px; }
            .card-grid { display:flex; flex-direction:column; gap:12px; }
            p { margin: 8px 0; color: #1f2937; font-size: 14px; }
            .hero { display:flex; gap:14px; padding:14px 16px; background: linear-gradient(135deg, #e0f2fe, #eef2ff); border:1px solid #bfdbfe; border-radius:14px; margin-bottom:16px; box-shadow:0 1px 3px rgba(59,130,246,0.2); }
            .hero-icon { width:32px; height:32px; border-radius:10px; background:#2563eb; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; }
            .hero-label { font-size:12px; text-transform:uppercase; letter-spacing:0.04em; color:#2563eb; font-weight:700; }
            .hero-answer { font-size:15px; font-weight:700; color:#0f172a; margin-top:4px; }
            .hero-directive { margin-top:6px; font-size:13px; color:#1f2937; border-top:1px solid #bfdbfe; padding-top:6px; }
            .snapshot-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; margin-top:10px; }
            .label { font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:#6b7280; margin-bottom:2px; }
            .value { font-size:13px; color:#0f172a; font-weight:600; }
            .badge { display:inline-block; padding:6px 10px; border-radius:9999px; font-size:12px; font-weight:700; margin-bottom:8px; border:1px solid #d1d5db; }
            .chip-row { display:flex; gap:10px; padding:10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; margin-bottom:8px; }
            .chip-num { width:24px; height:24px; border-radius:9999px; background:#2563eb; color:#fff; font-weight:700; display:flex; align-items:center; justify-content:center; font-size:12px; }
            .chip-title { font-weight:700; color:#0f172a; }
            .chip-body { color:#1f2937; font-size:14px; margin-top:4px; }
            .pill { text-decoration:none; background:#e0f2fe; color:#1d4ed8; }
            .pill-inline { text-decoration:none; color:#1d4ed8; font-weight:600; }
            .question-text { font-size:14px; color:#0f172a; font-weight:600; }
          </style>
        </head>
        <body>
          <h1>Executive Summary</h1>
          ${structuredHtml}
        </body>
      </html>
    `;

    const w = window.open("", "_blank", "width=960,height=720");
    if (!w) return;
    w.document.write(html);
    w.document.close();
    w.focus();
    setTimeout(() => {
      w.print();
    }, 300);
  }, [structuredBriefing, briefing]);

  // Legacy markdown components (simplified)
  const processText = useCallback((text: string, prefix: string): React.ReactNode => {
    const parts = renderCitations(text, prefix);
    return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : <>{parts}</>;
  }, [renderCitations]);

  const markdownComponents = useMemo(() => ({
    p: ({ children }: { children?: React.ReactNode }) => (
      <p className="my-3 leading-relaxed">
        {typeof children === 'string' ? processText(children, 'p') : children}
      </p>
    ),
    li: ({ children }: { children?: React.ReactNode }) => (
      <li className="my-1">
        {typeof children === 'string' ? processText(children, 'li') : children}
      </li>
    ),
    ul: (props: React.ComponentProps<'ul'>) => <ul className="list-disc pl-6 my-2 space-y-1" {...props} />,
    ol: (props: React.ComponentProps<'ol'>) => <ol className="list-decimal pl-6 my-2 space-y-1" {...props} />,
    h2: (props: React.ComponentProps<'h2'>) => <h2 className="text-lg font-semibold text-slate-800 mt-6 mb-3" {...props} />,
    h3: (props: React.ComponentProps<'h3'>) => <h3 className="text-base font-semibold text-slate-700 mt-4 mb-2" {...props} />,
    strong: (props: React.ComponentProps<'strong'>) => <strong className="font-semibold text-slate-900" {...props} />,
    table: (props: React.ComponentProps<'table'>) => (
      <div className="overflow-x-auto my-4 rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200" {...props} />
      </div>
    ),
    thead: (props: React.ComponentProps<'thead'>) => <thead className="bg-slate-50" {...props} />,
    tbody: (props: React.ComponentProps<'tbody'>) => <tbody className="bg-white divide-y divide-slate-200" {...props} />,
    th: (props: React.ComponentProps<'th'>) => <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider bg-slate-100" {...props} />,
    td: ({ children, ...props }: React.ComponentProps<'td'>) => (
      <td className="px-4 py-3 text-sm text-slate-700" {...props}>
        {typeof children === 'string' ? processText(children, 'td') : children}
      </td>
    ),
  }), [processText]);

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-slate-500" />
          Executive Briefing
        </CardTitle>
        <Button
          variant="outline"
          size="sm"
          onClick={handleDownloadPdf}
          disabled={!structuredBriefing && !briefing}
          className="gap-2"
        >
          <Download className="h-4 w-4" />
          Download PDF
        </Button>
      </CardHeader>
      <CardContent>
        {evidenceCoverage && <EvidenceCoverageBadge coverage={evidenceCoverage} />}
        
        {structuredBriefing ? (
          <div className="space-y-2">
            <CoreAnswerSection coreAnswer={structuredBriefing.core_answer} />
            
            {structuredBriefing.background_section && (
              <BackgroundSectionComponent 
                background={structuredBriefing.background_section}
                renderCitations={renderCitations}
              />
            )}
            
            <InterventionsTable 
              interventions={structuredBriefing.interventions_table}
              lookupCitation={lookupCitation}
              onCitationClick={onCitationClick}
              renderCitations={renderCitations}
            />
            
            <RecommendationsList 
              recommendations={structuredBriefing.recommendations}
              renderCitations={renderCitations}
            />
            
            <TopCitationsList 
              citations={structuredBriefing.top_citations}
              lookupCitation={lookupCitation}
              onCitationClick={onCitationClick}
            />
            
            {structuredBriefing.follow_up_suggestions.length > 0 && (
              <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                <div className="text-sm font-medium text-slate-700 mb-2">Suggested follow-up searches:</div>
                <ul className="text-sm text-slate-600 space-y-1">
                  {structuredBriefing.follow_up_suggestions.map((s, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <ChevronRight className="h-4 w-4 text-slate-400 mt-0.5 flex-shrink-0" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : briefing ? (
          <div className="prose prose-slate max-w-none">
            <ReactMarkdown skipHtml components={markdownComponents}>{briefing}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-center py-8 text-slate-500">
            <FileText className="h-12 w-12 mx-auto mb-3 text-slate-300" />
            <p>We are preparing the executive briefing. Please come back a bit later.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
