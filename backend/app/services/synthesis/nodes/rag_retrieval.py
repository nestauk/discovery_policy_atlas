"""
RAG retrieval nodes for the synthesis workflow.

Phase 4: Retrieve document chunks for themes and issues using vector search,
building grounded citations.

Implements constrained retrieval: only retrieves chunks from documents that
contributed to a theme via extractions, weighted by evidence strength and
predicted impact scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from app.services.vectorization import vectorization_service
from app.services.synthesis.state import SynthesisState
from app.services.synthesis.utils import extract_doc_info_from_chunk
from app.services.synthesis.schemas import CitationInfo, RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class RetrievalContext:
    """Shared context for RAG retrieval operations."""

    project_id: str
    doc_metadata: Dict[str, Dict[str, Any]]
    doc_scores: Dict[str, Dict[str, Any]]
    extraction_quotes: Dict[str, List[str]]
    theme_to_doc_uuids: Dict[str, List[str]]
    grounded_citations: List[CitationInfo]
    chunk_to_citation: Dict[str, int]
    doc_citation_map: Dict[str, int]
    seen_chunks: Set[str]


def _compute_quality_score(
    doc_scores: Dict[str, Dict[str, Any]], doc_uuid: str
) -> float:
    """Compute a combined quality score for a document.

    Combines evidence strength and predicted impact (both 1-5 scale)
    into a single 0-1 score. Documents without scores get 0, which
    penalises unscored documents in favour of those with quality assessments.

    Args:
        doc_scores: Mapping of doc_uuid -> {evidence_score, impact_score}.
        doc_uuid: The document UUID to score.

    Returns:
        Quality score between 0 and 1.
    """
    scores = doc_scores.get(doc_uuid, {})
    evidence = scores.get("evidence_score")  # 1-5 or None
    impact = scores.get("impact_score")  # 1-5 or None

    if evidence is None and impact is None:
        return 0.0

    ev_norm = ((evidence - 1) / 4) if evidence else 0.0
    im_norm = ((impact - 1) / 4) if impact else 0.0

    return 0.6 * ev_norm + 0.4 * im_norm


def _rerank_chunks_by_quality(
    chunks: List[Dict[str, Any]],
    doc_scores: Dict[str, Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], float]]:
    """Re-rank chunks by combining similarity and document quality.

    Final score = 0.7 * similarity + 0.3 * quality_score

    Args:
        chunks: Raw chunks from vector search with similarity scores.
        doc_scores: Document quality scores mapping.

    Returns:
        List of (chunk, final_score) tuples sorted by final_score descending.
    """
    scored = []
    for chunk in chunks:
        doc_uuid = str(chunk.get("document_id", ""))
        similarity = float(chunk.get("similarity", 0))
        quality = _compute_quality_score(doc_scores, doc_uuid)
        final_score = 0.7 * similarity + 0.3 * quality
        scored.append((chunk, final_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def _retrieve_for_theme(
    theme_id: str,
    query: str,
    ctx: RetrievalContext,
    match_count: int,
    max_results: int,
) -> Tuple[List[RetrievedChunk], int]:
    """Retrieve and process chunks for a single theme.

    Args:
        theme_id: Theme identifier for constraint lookup.
        query: Search query string.
        ctx: Shared retrieval context.
        match_count: Number of candidates to fetch from vector search.
        max_results: Maximum chunks to return after filtering.

    Returns:
        Tuple of (retrieved_chunks, constrained_count).
    """
    if not query.strip():
        return [], 0

    allowed_doc_uuids = set(ctx.theme_to_doc_uuids.get(theme_id, []))
    constrained_count = 0

    try:
        raw_chunks = await vectorization_service.search_similar_content(
            query=query,
            project_id=ctx.project_id,
            match_threshold=0.45,
            match_count=match_count,
        )

        if allowed_doc_uuids:
            constrained_chunks = [
                c
                for c in (raw_chunks or [])
                if str(c.get("document_id", "")) in allowed_doc_uuids
            ]
            constrained_count = len(constrained_chunks)
        else:
            constrained_chunks = raw_chunks or []

        ranked = _rerank_chunks_by_quality(constrained_chunks, ctx.doc_scores)

        retrieved: List[RetrievedChunk] = []
        for chunk, final_score in ranked:
            chunk_id = str(chunk.get("id", ""))
            if chunk_id in ctx.seen_chunks:
                continue
            ctx.seen_chunks.add(chunk_id)

            info = extract_doc_info_from_chunk(chunk, ctx.doc_metadata)
            content = str(chunk.get("content", ""))[:500]
            doc_uuid = info["doc_uuid"]

            doc_quotes = ctx.extraction_quotes.get(doc_uuid, [])
            supporting_quote = doc_quotes[0][:300] if doc_quotes else content[:300]

            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=doc_uuid,
                    content=content,
                    chunk_type=str(chunk.get("chunk_type", "content")),
                    similarity=final_score,
                    doc_title=info["title"],
                    author_short=info["author_short"],
                    year=info["year"],
                    url=info["url"],
                )
            )

            if chunk_id not in ctx.chunk_to_citation:
                if doc_uuid in ctx.doc_citation_map:
                    ctx.chunk_to_citation[chunk_id] = ctx.doc_citation_map[doc_uuid]
                else:
                    cit_num = len(ctx.grounded_citations) + 1
                    ctx.chunk_to_citation[chunk_id] = cit_num
                    ctx.doc_citation_map[doc_uuid] = cit_num
                    ctx.grounded_citations.append(
                        CitationInfo(
                            citation_key=f"[{cit_num}]",
                            citation_number=cit_num,
                            doc_id=info["doc_id"],
                            analysis_document_id=doc_uuid,
                            author_short=info["author_short"],
                            year=info["year"],
                            title=info["title"],
                            url=info["url"],
                            supporting_quote=supporting_quote,
                            chunk_id=chunk_id,
                        )
                    )

        return retrieved[:max_results], constrained_count

    except Exception as e:
        logger.warning(f"RAG retrieval failed for '{theme_id}': {e}")
        return [], 0


async def retrieve_evidence_for_themes(state: SynthesisState) -> SynthesisState:
    """Retrieve document chunks for intervention themes using constrained RAG.

    Args:
        state: Current workflow state with aggregated_interventions.

    Returns:
        State update with theme_evidence, grounded_citations, chunk_to_citation.
    """
    print("--- RAG: Retrieving Evidence for Interventions (Constrained) ---")

    ctx = RetrievalContext(
        project_id=state.get("project_id", ""),
        doc_metadata=state.get("doc_metadata") or {},
        doc_scores=state.get("doc_scores") or {},
        extraction_quotes=state.get("extraction_quotes") or {},
        theme_to_doc_uuids=state.get("theme_to_doc_uuids") or {},
        grounded_citations=[],
        chunk_to_citation={},
        doc_citation_map=dict(state.get("doc_citation_map") or {}),
        seen_chunks=set(),
    )

    interventions = state.get("aggregated_interventions") or []
    theme_evidence: Dict[str, List[RetrievedChunk]] = {}
    total_constrained = 0

    for intervention in interventions:
        theme_id = intervention.intervention_name
        query = f"{theme_id} {intervention.brief_description or ''}"[:500]

        chunks, constrained = await _retrieve_for_theme(
            theme_id, query, ctx, match_count=30, max_results=8
        )
        theme_evidence[theme_id] = chunks
        total_constrained += constrained

    print(
        f"Retrieved evidence for {len(theme_evidence)} themes, "
        f"{len(ctx.grounded_citations)} citations"
    )
    print(
        f"Constrained to theme-contributing docs: {total_constrained} chunks passed filter"
    )

    return {
        "theme_evidence": theme_evidence,
        "grounded_citations": ctx.grounded_citations,
        "chunk_to_citation": ctx.chunk_to_citation,
        "doc_citation_map": ctx.doc_citation_map,
    }


async def retrieve_evidence_for_issues(state: SynthesisState) -> SynthesisState:
    """Retrieve document chunks for issue themes using constrained RAG.

    Args:
        state: Current workflow state with aggregated_issues.

    Returns:
        State update with issue_evidence and updated citations.
    """
    print("--- RAG: Retrieving Evidence for Issues (Constrained) ---")

    ctx = RetrievalContext(
        project_id=state.get("project_id", ""),
        doc_metadata=state.get("doc_metadata") or {},
        doc_scores=state.get("doc_scores") or {},
        extraction_quotes=state.get("extraction_quotes") or {},
        theme_to_doc_uuids=state.get("theme_to_doc_uuids") or {},
        grounded_citations=list(state.get("grounded_citations") or []),
        chunk_to_citation=dict(state.get("chunk_to_citation") or {}),
        doc_citation_map=dict(state.get("doc_citation_map") or {}),
        seen_chunks=set(state.get("chunk_to_citation", {}).keys()),
    )

    issues = state.get("aggregated_issues") or []
    issue_evidence: Dict[str, List[RetrievedChunk]] = {}
    total_constrained = 0

    for issue in issues:
        theme_id = issue.issue_theme
        query = f"{theme_id} {issue.summary_description or ''}"[:400]

        chunks, constrained = await _retrieve_for_theme(
            theme_id, query, ctx, match_count=20, max_results=6
        )
        issue_evidence[theme_id] = chunks
        total_constrained += constrained

    print(f"Constrained issue retrieval: {total_constrained} chunks passed filter")

    return {
        "issue_evidence": issue_evidence,
        "grounded_citations": ctx.grounded_citations,
        "chunk_to_citation": ctx.chunk_to_citation,
        "doc_citation_map": ctx.doc_citation_map,
    }
