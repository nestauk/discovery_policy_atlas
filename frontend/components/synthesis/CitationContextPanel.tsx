"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ExternalLink, X } from "lucide-react";
import * as fuzz from "fuzzball";
import { fetchWithAuthExternal } from "@/lib/api";
import { Tooltip } from "@/components/ui/tooltip";
import { getEvidenceCategoryColors, getEvidenceCategoryShortName } from "@/lib/evidenceCategories";
import type { CitationInfo } from "@/types/search";

interface ChunkContextResponse {
  chunk_id: string;
  chunk_content: string;
  chunk_index: number;
  previous_chunk_content?: string | null;
  next_chunk_content?: string | null;
  document: {
    analysis_document_id: string;
    title: string;
    author_display?: string | null;
    author_short?: string | null;
    year?: number | null;
    country?: string | null;
    url?: string | null;
    source_type?: string | null;
    document_type?: string | null;
    evidence_category?: string | null;
    evidence_score?: number | null;
    impact_score?: number | null;
  };
}

interface CitationContextPanelProps {
  isOpen: boolean;
  projectId: string;
  citationInfo: CitationInfo | null;
  chunkId?: string;
  supportingQuote?: string;
  onClose: () => void;
  onViewEvidence?: (docId: string) => void;
}

function ratio(str1: string, str2: string): number {
  const fuzzModule = fuzz as unknown as {
    ratio?: (a: string, b: string) => number;
    partial_ratio?: (a: string, b: string) => number;
    default?: { ratio?: (a: string, b: string) => number };
  };
  const scorer = fuzzModule.ratio || fuzzModule.default?.ratio;
  if (!scorer) return 0;
  return scorer(str1, str2);
}

function partialRatio(str1: string, str2: string): number {
  const fuzzModule = fuzz as unknown as {
    partial_ratio?: (a: string, b: string) => number;
    default?: { partial_ratio?: (a: string, b: string) => number };
  };
  const scorer = fuzzModule.partial_ratio || fuzzModule.default?.partial_ratio;
  if (!scorer) return 0;
  return scorer(str1, str2);
}

function canonicaliseText(text: string): string {
  return text
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2013\u2014]/g, "-");
}

type NormalisedText = { text: string; indexMap: number[] };

function normaliseForMatching(text: string): NormalisedText {
  const canonical = canonicaliseText(text);
  const strippedChars: string[] = [];
  const strippedMap: number[] = [];

  for (let idx = 0; idx < canonical.length; ) {
    if (canonical[idx] === "(") {
      const match = canonical.slice(idx).match(/^\(\s*\d{1,4}\s*\)/);
      if (match) {
        idx += match[0].length;
        continue;
      }
    }
    strippedChars.push(canonical[idx]);
    strippedMap.push(idx);
    idx += 1;
  }

  const compactChars: string[] = [];
  const compactMap: number[] = [];
  for (let i = 0; i < strippedChars.length; i += 1) {
    const ch = strippedChars[i];
    if (/\s/.test(ch)) {
      if (compactChars.length === 0 || compactChars[compactChars.length - 1] === " ") continue;
      compactChars.push(" ");
      compactMap.push(strippedMap[i]);
      continue;
    }
    if (/[.,;:!?]/.test(ch) && compactChars.length > 0 && compactChars[compactChars.length - 1] === " ") {
      compactChars.pop();
      compactMap.pop();
    }
    compactChars.push(ch);
    compactMap.push(strippedMap[i]);
  }

  while (compactChars.length > 0 && compactChars[compactChars.length - 1] === " ") {
    compactChars.pop();
    compactMap.pop();
  }

  return { text: compactChars.join(""), indexMap: compactMap };
}

function findExactLikeRange(content: string, quote: string): { start: number; end: number } | null {
  if (!content || !quote) return null;
  const rawIndex = content.indexOf(quote);
  if (rawIndex >= 0) return { start: rawIndex, end: rawIndex + quote.length };

  const contentLower = content.toLowerCase();
  const quoteLower = quote.toLowerCase();
  const caseIndex = contentLower.indexOf(quoteLower);
  if (caseIndex >= 0) return { start: caseIndex, end: caseIndex + quote.length };

  const normalisedContent = normaliseForMatching(content);
  const normalisedQuote = normaliseForMatching(quote);
  if (!normalisedContent.text || !normalisedQuote.text) return null;
  const normalisedIndex = normalisedContent.text
    .toLowerCase()
    .indexOf(normalisedQuote.text.toLowerCase());
  if (normalisedIndex >= 0) {
    const start = normalisedContent.indexMap[normalisedIndex];
    const endIdx = normalisedIndex + normalisedQuote.text.length - 1;
    const end =
      endIdx >= 0 && endIdx < normalisedContent.indexMap.length
        ? normalisedContent.indexMap[endIdx] + 1
        : start + normalisedQuote.text.length;
    return { start, end };
  }

  return null;
}

type TokenSpan = { token: string; start: number; end: number };

function extractTokenSpans(text: string): TokenSpan[] {
  const spans: TokenSpan[] = [];
  const regex = /[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    spans.push({
      token: match[0],
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  return spans;
}

function findQuoteRange(content: string, quote: string): { start: number; end: number } | null {
  const trimmedContent = content.trim();
  const trimmedQuote = quote.trim();
  if (!trimmedContent || !trimmedQuote) return null;

  const exactLikeMatch = findExactLikeRange(trimmedContent, trimmedQuote);
  if (exactLikeMatch) return exactLikeMatch;

  const contentTokens = extractTokenSpans(trimmedContent);
  const quoteTokens = extractTokenSpans(trimmedQuote);
  if (contentTokens.length === 0 || quoteTokens.length === 0) return null;

  const minWindowTokens = Math.max(3, Math.floor(quoteTokens.length * 0.9));
  const maxWindowTokens = Math.max(minWindowTokens, Math.ceil(quoteTokens.length * 1.1));
  let bestScore = 0;
  let bestPartial = 0;
  let bestLengthSimilarity = 0;
  let bestStart = -1;
  let bestEnd = -1;
  const quoteNormalised = normaliseForMatching(trimmedQuote).text.toLowerCase();
  if (!quoteNormalised) return null;

  for (let startToken = 0; startToken < contentTokens.length; startToken += 1) {
    for (
      let tokenCount = minWindowTokens;
      tokenCount <= maxWindowTokens && startToken + tokenCount <= contentTokens.length;
      tokenCount += 1
    ) {
      const endToken = startToken + tokenCount - 1;
      const windowStart = contentTokens[startToken].start;
      const windowEnd = contentTokens[endToken].end;
      const windowText = trimmedContent.slice(windowStart, windowEnd);
      const windowNormalised = normaliseForMatching(windowText).text.toLowerCase();
      if (!windowNormalised) continue;

      const lengthSimilarity =
        Math.min(quoteNormalised.length, windowNormalised.length) /
        Math.max(quoteNormalised.length, windowNormalised.length);
      if (lengthSimilarity < 0.88) continue;

      const score = ratio(quoteNormalised, windowNormalised);
      const pScore = partialRatio(quoteNormalised, windowNormalised);
      if (
        score > bestScore ||
        (score === bestScore && pScore > bestPartial) ||
        (score === bestScore && pScore === bestPartial && lengthSimilarity > bestLengthSimilarity)
      ) {
        bestScore = score;
        bestPartial = pScore;
        bestLengthSimilarity = lengthSimilarity;
        bestStart = windowStart;
        bestEnd = windowEnd;
      }
    }
  }

  // Require strong ordered similarity and comparable span length.
  if (bestScore < 90 || bestPartial < 92 || bestLengthSimilarity < 0.9 || bestStart < 0) return null;
  return { start: bestStart, end: bestEnd };
}

function formatOutOfFive(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "N/A";
  const formatted = Number.isInteger(value) ? value.toString() : value.toFixed(1);
  return `${formatted}/5`;
}

export function CitationContextPanel({
  isOpen,
  projectId,
  citationInfo,
  chunkId,
  supportingQuote,
  onClose,
  onViewEvidence,
}: CitationContextPanelProps) {
  const [contextData, setContextData] = useState<ChunkContextResponse | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const highlightRef = useRef<HTMLSpanElement | null>(null);

  const dataIsStale = isOpen && !!chunkId && contextData?.chunk_id !== chunkId;
  const isLoading = isFetching || dataIsStale;

  useEffect(() => {
    let cancelled = false;

    async function loadContext() {
      if (!isOpen || !citationInfo || !chunkId) {
        setContextData(null);
        setError(null);
        setIsFetching(false);
        return;
      }

      setIsFetching(true);
      setError(null);

      try {
        const res = (await fetchWithAuthExternal(
          `api/analysis-projects/${projectId}/chunks/${chunkId}/context`
        )) as ChunkContextResponse | null;

        if (!cancelled) {
          if (res) {
            setContextData(res);
          } else {
            setContextData(null);
            setError("Full context unavailable in preview.");
          }
        }
      } catch {
        if (!cancelled) {
          setContextData(null);
          setError("Full context unavailable in preview.");
        }
      } finally {
        if (!cancelled) setIsFetching(false);
      }
    }

    void loadContext();

    return () => {
      cancelled = true;
    };
  }, [isOpen, projectId, chunkId, citationInfo]);

  const freshData = dataIsStale ? null : contextData;

  const effectiveTitle = freshData?.document.title || citationInfo?.title || "Unknown source";
  const effectiveAuthor =
    freshData?.document.author_display || freshData?.document.author_short || citationInfo?.author_short;
  const effectiveYear = freshData?.document.year || citationInfo?.year;
  const effectiveCountry = freshData?.document.country;
  const effectiveUrl = freshData?.document.url || citationInfo?.url;
  const effectiveSourceType =
    freshData?.document.source_type || freshData?.document.document_type || citationInfo?.document_type;
  const effectiveEvidenceCategory = freshData?.document.evidence_category;
  const evidenceScore = freshData?.document.evidence_score ?? citationInfo?.evidence_score;
  const impactScore = freshData?.document.impact_score ?? citationInfo?.impact_score;
  const quote = supportingQuote || citationInfo?.supporting_quote || "";

  const quoteRange = useMemo(() => {
    if (!freshData?.chunk_content || !quote) return null;
    return findQuoteRange(freshData.chunk_content, quote);
  }, [freshData?.chunk_content, quote]);

  useEffect(() => {
    if (!isOpen || isLoading || !quoteRange) return;
    const container = scrollContainerRef.current;
    const highlight = highlightRef.current;
    if (!container || !highlight) return;

    const containerRect = container.getBoundingClientRect();
    const highlightRect = highlight.getBoundingClientRect();
    const currentScrollTop = container.scrollTop;
    const highlightTopInContainer = highlightRect.top - containerRect.top + currentScrollTop;
    const targetScrollTop =
      highlightTopInContainer - container.clientHeight / 2 + highlightRect.height / 2;

    container.scrollTo({
      top: Math.max(0, targetScrollTop),
      behavior: "auto",
    });
  }, [isOpen, isLoading, quoteRange, freshData?.chunk_id]);

  const sourceDocId = citationInfo?.analysis_document_id || "";

  return (
    <aside
      className={`fixed inset-y-0 right-0 z-40 w-[30vw] min-w-[360px] max-w-[500px] border-l border-slate-200 bg-white shadow-xl transition-transform duration-300 ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
      aria-hidden={!isOpen}
    >
      <div className="flex h-full flex-col">
        <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-5 py-4">
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close citation context"
          >
            <X className="h-4 w-4" />
          </button>
          <h3 className="pr-8 text-sm font-semibold text-slate-900">{effectiveTitle}</h3>
          <div className="mt-1 text-xs text-slate-600">
            {[effectiveAuthor, effectiveYear].filter(Boolean).join(", ") || "Unknown metadata"}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            {effectiveSourceType && (
              <span className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-700">
                {effectiveSourceType}
              </span>
            )}
            {effectiveEvidenceCategory && (
              <Tooltip content={effectiveEvidenceCategory}>
                <span
                  className="inline-block cursor-help whitespace-normal rounded px-2 py-1 text-xs font-medium leading-tight"
                  style={{
                    backgroundColor: getEvidenceCategoryColors(effectiveEvidenceCategory).bg,
                    color: getEvidenceCategoryColors(effectiveEvidenceCategory).text,
                  }}
                >
                  {getEvidenceCategoryShortName(effectiveEvidenceCategory)}
                </span>
              </Tooltip>
            )}
            <div className="text-slate-500">
              Evidence: <span className="font-medium text-slate-700">{formatOutOfFive(evidenceScore)}</span>
            </div>
            <div className="text-slate-500">
              Impact:{" "}
              <span className="font-medium text-slate-700">
                {formatOutOfFive(impactScore)}
              </span>
            </div>
            {effectiveCountry && (
              <div className="text-slate-500">
                Country: <span className="font-medium text-slate-700">{effectiveCountry}</span>
              </div>
            )}
          </div>
        </div>

        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && (
            <div className="space-y-3">
              <div className="h-3 w-2/3 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-5/6 animate-pulse rounded bg-slate-200" />
            </div>
          )}

          {!isLoading && error && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4" />
                <span>{error}</span>
              </div>
            </div>
          )}

          {!isLoading && quote && !freshData && (
            <blockquote className="mt-3 rounded-md border-l-4 border-amber-400 bg-amber-50 p-3 text-sm italic text-slate-700">
              {quote}
            </blockquote>
          )}

          {!isLoading && freshData && (
            <div className="space-y-3 text-sm leading-relaxed">
              {freshData.previous_chunk_content && (
                <p className="text-slate-400">{freshData.previous_chunk_content}</p>
              )}

              {quoteRange ? (
                <p className="text-slate-700">
                  <span className="text-slate-400">
                    {freshData.chunk_content.slice(0, quoteRange.start)}
                  </span>
                  <span
                    ref={highlightRef}
                    className="rounded bg-amber-100 px-0.5 font-semibold text-slate-900"
                  >
                    {freshData.chunk_content.slice(quoteRange.start, quoteRange.end)}
                  </span>
                  <span className="text-slate-400">
                    {freshData.chunk_content.slice(quoteRange.end)}
                  </span>
                </p>
              ) : (
                <>
                  {quote && (
                    <blockquote className="rounded-md border-l-4 border-amber-400 bg-amber-50 p-3 text-sm italic text-slate-700">
                      {quote}
                    </blockquote>
                  )}
                  <p className="text-slate-700">{freshData.chunk_content}</p>
                </>
              )}

              {freshData.next_chunk_content && (
                <p className="text-slate-400">{freshData.next_chunk_content}</p>
              )}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 px-5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {effectiveUrl && (
              <a
                href={effectiveUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open original document
              </a>
            )}
            {onViewEvidence && sourceDocId && (
              <button
                type="button"
                onClick={() => onViewEvidence(sourceDocId)}
                className="inline-flex items-center rounded-md border border-blue-300 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50"
              >
                View all evidence
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
