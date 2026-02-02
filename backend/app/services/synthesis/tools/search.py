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

    def _rcs_search(
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

        for ctx, score in scored_matches[: max_results * 2]:
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
                    content=ctx.chunk_text[:500] if ctx.chunk_text else "",
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
                    content=str(chunk.get("content", ""))[:500],
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

        # First, try to find relevant pre-computed RCS contexts
        rcs_results = []
        if all_scored_contexts:
            rcs_results = self._rcs_search(
                query, all_scored_contexts, doc_citation_map, max_results
            )
            if rcs_results:
                logger.info(
                    f"search_extractions('{query[:50]}...'): "
                    f"found {len(rcs_results)} from RCS contexts"
                )
                return ToolResult.ok(
                    [r.model_dump() for r in rcs_results], fallback_used=False
                )

        # Fallback: perform live vector search
        try:
            results = await self._live_search(
                query=query,
                project_id=project_id,
                doc_citation_map=doc_citation_map,
                doc_metadata=doc_metadata,
                max_results=max_results,
            )
            logger.info(
                f"search_extractions('{query[:50]}...'): "
                f"found {len(results)} from live search"
            )

            return ToolResult.ok(
                [r.model_dump() for r in results],
                fallback_used=True,
            )

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


# Register tool
register_tool(SearchExtractionsTool())
