"""
Search tools for agentic briefing.

Provides tools to perform semantic search across extractions and chunks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.vectorization import vectorization_service
from app.services.synthesis.schemas import ScoredContext
from app.services.synthesis.utils import fetch_chunk_texts
from app.services.synthesis.tools.base import (
    BaseTool,
    ToolResult,
    register_tool,
)

logger = logging.getLogger(__name__)


class SearchResultItem(BaseModel):
    """A single search result from semantic search.

    Attributes:
        summary: Content summary or full text.
        citation_number: [N] citation if available.
        document_title: Source document title.
        document_id: UUID of the source document.
        similarity_score: Vector similarity (0-1).
        content: Chunk content text.
        chunk_id: Unique chunk identifier.
    """

    summary: str = ""
    citation_number: Optional[int] = None
    document_title: str = ""
    document_id: str = ""
    similarity_score: float = 0.0
    content: str = ""
    chunk_id: str = ""


class SearchExtractionsInput(BaseModel):
    """Input parameters for search_extractions tool."""

    query: str = Field(..., description="Semantic search query")
    max_results: int = Field(5, description="Maximum results to return", ge=1, le=10)


class DynamicRetrieveInput(BaseModel):
    """Input parameters for retrieve_evidence tool."""

    query: str = Field(..., description="Evidence search query")
    max_results: int = Field(5, description="Maximum results to return", ge=1, le=10)
    match_threshold: float = Field(
        0.45,
        description="Vector similarity threshold",
        ge=0.0,
        le=1.0,
    )


class SearchExtractionsTool(BaseTool):
    """Tool to perform semantic search across document chunks.

    Unlike get_theme_evidence (which queries pre-computed RCS),
    this tool performs a live semantic search across all document
    chunks for a given query. Use when you need evidence that
    doesn't match a specific theme.
    """

    name = "search_extractions"
    description = (
        "Perform semantic search across all document chunks. "
        "Use when you need evidence for a specific claim or topic "
        "that doesn't fit into a known theme. Returns chunks ranked "
        "by similarity, with citation numbers if available."
    )
    max_results = 5

    async def _rcs_search(
        self,
        query: str,
        contexts: List[ScoredContext],
        doc_citation_map: Dict[str, int],
        max_results: int,
    ) -> List[SearchResultItem]:
        query_words = set(query.lower().split())
        scored_matches: List[tuple] = []

        for ctx in contexts:
            summary_words = set(ctx.summary.lower().split())
            overlap = len(query_words & summary_words)
            if overlap:
                score = overlap * 0.3 + ctx.relevance_score * 0.7
                scored_matches.append((ctx, score))

        if not scored_matches:
            return []

        scored_matches.sort(key=lambda x: x[1], reverse=True)
        results: List[SearchResultItem] = []
        seen_docs: set = set()
        top_matches = scored_matches[: max_results * 2]
        chunk_text_map = await fetch_chunk_texts(
            [ctx.chunk_id for ctx, _ in top_matches if getattr(ctx, "chunk_id", "")]
        )

        for ctx, score in top_matches:
            if ctx.document_id in seen_docs:
                continue
            seen_docs.add(ctx.document_id)
            cit_num = doc_citation_map.get(ctx.document_id)
            if not cit_num:
                continue
            results.append(
                SearchResultItem(
                    summary=ctx.summary,
                    citation_number=cit_num,
                    document_title=ctx.document_title,
                    document_id=ctx.document_id,
                    similarity_score=score / 10,
                    content=chunk_text_map.get(ctx.chunk_id, ""),
                    chunk_id=ctx.chunk_id,
                )
            )
            if len(results) >= max_results:
                break

        return results

    async def _live_search(
        self,
        query: str,
        project_id: str,
        doc_citation_map: Dict[str, int],
        doc_metadata: Dict[str, Dict[str, Any]],
        max_results: int,
    ) -> List[SearchResultItem]:
        raw_chunks = await vectorization_service.search_similar_content(
            query=query,
            project_id=project_id,
            match_threshold=0.5,
            match_count=max_results * 3,
        )

        if not raw_chunks:
            return []

        results: List[SearchResultItem] = []
        seen_docs: set = set()

        for chunk in raw_chunks:
            doc_uuid = str(chunk.get("document_id", ""))
            if doc_uuid in seen_docs:
                continue
            seen_docs.add(doc_uuid)

            cit_num = doc_citation_map.get(doc_uuid)
            meta = doc_metadata.get(doc_uuid, {})
            title = meta.get("title") or chunk.get("title", "Unknown")

            results.append(
                SearchResultItem(
                    summary="",
                    citation_number=cit_num,
                    document_title=title,
                    document_id=doc_uuid,
                    similarity_score=float(chunk.get("similarity", 0)),
                    content=str(chunk.get("content", "")),
                    chunk_id=str(chunk.get("id", "")),
                )
            )

            if len(results) >= max_results:
                break

        return results

    async def execute(
        self,
        state: Dict[str, Any],
        query: str,
        max_results: Optional[int] = None,
    ) -> ToolResult:
        """Execute semantic search across document chunks.

        Args:
            state: Current synthesis state.
            query: Semantic search query.
            max_results: Maximum results to return.

        Returns:
            ToolResult with list of SearchResultItem.
        """
        max_results = max_results or self.max_results
        project_id = state.get("project_id", "")

        if not project_id:
            return ToolResult.fail("No project_id in state")

        if not query.strip():
            return ToolResult.fail("Empty search query")

        # Get mappings from state
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}
        all_scored_contexts: List[ScoredContext] = (
            state.get("all_scored_contexts") or []
        )
        try:
            results = await self._live_search(
                query=query,
                project_id=project_id,
                doc_citation_map=doc_citation_map,
                doc_metadata=doc_metadata,
                max_results=max_results,
            )
            if results:
                # Enrich semantic hits with RCS summary when chunk ids overlap.
                summary_by_chunk = {
                    str(ctx.chunk_id): (ctx.summary or "")
                    for ctx in all_scored_contexts
                    if getattr(ctx, "chunk_id", "")
                }
                for item in results:
                    if not item.summary:
                        item.summary = summary_by_chunk.get(item.chunk_id, "")

                logger.info(
                    f"search_extractions('{query[:50]}...'): "
                    f"found {len(results)} from semantic vector search"
                )
                return ToolResult.ok(
                    [r.model_dump() for r in results],
                    fallback_used=False,
                )

            # Fallback to lexical-overlap search over pre-scored summaries.
            if all_scored_contexts:
                rcs_results = await self._rcs_search(
                    query,
                    all_scored_contexts,
                    doc_citation_map,
                    max_results,
                )
                logger.info(
                    f"search_extractions('{query[:50]}...'): "
                    f"found {len(rcs_results)} from RCS fallback"
                )
                return ToolResult.ok(
                    [r.model_dump() for r in rcs_results],
                    fallback_used=True,
                )

            logger.info(f"search_extractions('{query[:50]}...'): " "found 0 results")
            return ToolResult.ok([], fallback_used=True)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return ToolResult.fail(f"Search failed: {e}")

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Semantic search query. Be specific about what evidence "
                        "you're looking for. Examples: 'effect size of exercise on BMI', "
                        "'barriers to policy implementation'"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }


class DynamicRetrieveTool(BaseTool):
    """Tool to retrieve fresh evidence with live vector search.

    This bypasses pre-computed theme matching and is intended for
    targeted gap-filling during retries.
    """

    name = "retrieve_evidence"
    description = (
        "Retrieve fresh evidence for a specific claim via live vector search "
        "across project chunks. Use for targeted evidence gap-filling."
    )
    max_results = 5

    async def execute(
        self,
        state: Dict[str, Any],
        query: str,
        max_results: Optional[int] = None,
        match_threshold: float = 0.45,
    ) -> ToolResult:
        """Retrieve evidence with live semantic search."""
        project_id = state.get("project_id", "")
        if not project_id:
            return ToolResult.fail("No project_id in state")
        if not query.strip():
            return ToolResult.fail("Empty query")

        max_results = max_results or self.max_results
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}

        raw_chunks = await vectorization_service.search_similar_content(
            query=query,
            project_id=project_id,
            match_threshold=match_threshold,
            match_count=max_results * 4,
        )
        if not raw_chunks:
            return ToolResult.ok([], fallback_used=True)

        chunk_ids = [str(c.get("id", "")) for c in raw_chunks if c.get("id")]
        chunk_text_map = await fetch_chunk_texts(chunk_ids)

        results: List[SearchResultItem] = []
        seen_docs: set = set()
        for chunk in raw_chunks:
            doc_uuid = str(chunk.get("document_id", ""))
            if not doc_uuid or doc_uuid in seen_docs:
                continue
            seen_docs.add(doc_uuid)
            meta = doc_metadata.get(doc_uuid, {})
            title = meta.get("title") or chunk.get("title", "Unknown")
            chunk_id = str(chunk.get("id", ""))
            results.append(
                SearchResultItem(
                    summary="",
                    citation_number=doc_citation_map.get(doc_uuid),
                    document_title=title,
                    document_id=doc_uuid,
                    similarity_score=float(chunk.get("similarity", 0.0)),
                    content=chunk_text_map.get(chunk_id)
                    or str(chunk.get("content", "")),
                    chunk_id=chunk_id,
                )
            )
            if len(results) >= max_results:
                break

        logger.info(
            "retrieve_evidence('%s...'): found %d results",
            query[:50],
            len(results),
        )
        return ToolResult.ok([r.model_dump() for r in results], fallback_used=False)

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Claim or evidence need to search for.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
                "match_threshold": {
                    "type": "number",
                    "description": "Vector similarity threshold.",
                    "default": 0.45,
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["query"],
        }


# Functional interface
async def search_extractions(
    state: Dict[str, Any],
    query: str,
    max_results: int = 5,
) -> ToolResult:
    """Perform semantic search across document chunks.

    Convenience function wrapping SearchExtractionsTool.

    Args:
        state: Current synthesis state.
        query: Semantic search query.
        max_results: Maximum results to return.

    Returns:
        ToolResult with list of search results.
    """
    tool = SearchExtractionsTool()
    return await tool.execute(state, query=query, max_results=max_results)


async def retrieve_evidence(
    state: Dict[str, Any],
    query: str,
    max_results: int = 5,
    match_threshold: float = 0.45,
) -> ToolResult:
    """Retrieve fresh evidence via live vector search."""
    tool = DynamicRetrieveTool()
    return await tool.execute(
        state,
        query=query,
        max_results=max_results,
        match_threshold=match_threshold,
    )


# Register tool
register_tool(SearchExtractionsTool())
register_tool(DynamicRetrieveTool())
