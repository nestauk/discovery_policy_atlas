'use client'

import { useMemo, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { ExternalLink, BookOpen, FileText, Quote, CheckCircle, Lightbulb, AlertTriangle, ChevronRight } from "lucide-react";
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

function InterventionsTable({ interventions, lookupCitation, onCitationClick }: { 
  interventions: InterventionTableRow[];
  lookupCitation: CitationLookupFn;
  onCitationClick?: (docId: string) => void;
}) {
  if (!interventions.length) return null;

  const effectBadgeColor = (direction: string) => {
    switch (direction) {
      case 'positive': return 'bg-green-100 text-green-800';
      case 'negative': return 'bg-red-100 text-red-800';
      case 'mixed': return 'bg-amber-100 text-amber-800';
      case 'null': return 'bg-slate-100 text-slate-600';
      default: return 'bg-slate-50 text-slate-500';
    }
  };

  const formatEffectCounts = (pos: number, neg: number, nul: number) => {
    const parts = [];
    if (pos > 0) parts.push(`${pos}↑`);
    if (neg > 0) parts.push(`${neg}↓`);
    if (nul > 0) parts.push(`${nul}—`);
    return parts.join(' ') || '—';
  };

  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold text-slate-800 mb-3">Key Interventions</h3>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-1/5">Intervention</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-1/5">Context</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-2/5">Effects by Outcome</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-1/5">Sources</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-200">
            {interventions.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-50 align-top">
                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                  {row.intervention_name}
                </td>
                <td className="px-4 py-3 text-sm text-slate-600">
                  {row.context || 'Various settings'}
                </td>
                <td className="px-4 py-3">
                  {row.outcome_effects && row.outcome_effects.length > 0 ? (
                    <div className="space-y-1.5">
                      {row.outcome_effects.map((effect, effIdx) => (
                        <div key={effIdx} className="flex items-center gap-2 text-sm">
                          <Badge className={`${effectBadgeColor(effect.direction)} text-xs px-1.5 py-0.5`}>
                            {effect.direction}
                          </Badge>
                          <span className="text-slate-700 font-medium truncate max-w-[200px]" title={effect.outcome_theme}>
                            {effect.outcome_theme}
                          </span>
                          <span className="text-xs text-slate-400">
                            {formatEffectCounts(effect.positive_count, effect.negative_count, effect.null_count)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm text-slate-400 italic">No outcome data</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm">
                  <div className="flex flex-wrap gap-1">
                    {row.citation_numbers.slice(0, 4).map((num) => (
                      <CitationLink
                        key={`int-${idx}-${num}`}
                        citationKey={`[${num}]`}
                        citationNumber={num}
                        citationInfo={lookupCitation(num)}
                        onCitationClick={onCitationClick}
                      />
                    ))}
                    {row.citation_numbers.length > 4 && (
                      <span className="text-xs text-slate-500">+{row.citation_numbers.length - 4}</span>
                    )}
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
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-slate-500" />
          Executive Briefing
        </CardTitle>
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
