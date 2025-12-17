"""
Evidence retrieval tools for agentic briefing.

Provides tools to query pre-computed RCS scored contexts and
retrieve targeted evidence for specific themes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.services.synthesis.schemas import ScoredContext, ThemeEvidence
from app.services.synthesis.tools.base import (
    BaseTool,
    ToolResult,
    register_tool,
)

logger = logging.getLogger(__name__)


class ThemeEvidenceItem(BaseModel):
    """A single evidence item returned by get_theme_evidence.

    Attributes:
        summary: Contextualised summary of the evidence.
        citation_number: [N] citation for referencing.
        document_title: Source document title.
        relevance_score: RCS relevance score (0-10).
        document_quality: Evidence strength score (1-5), None if unavailable.
        chunk_text: Original chunk text (truncated).
    """

    summary: str
    citation_number: int
    document_title: str
    relevance_score: int
    document_quality: Optional[int] = None
    chunk_text: str = ""


class GetThemeEvidenceTool(BaseTool):
    """Tool to retrieve RCS-scored evidence for a specific theme.

    Queries pre-computed scored_theme_evidence and scored_issue_evidence
    from the synthesis state. Filters by relevance score and deduplicates
    by document.
    """

    name = "get_theme_evidence"
    description = (
        "Retrieve pre-scored evidence for a specific theme or intervention. "
        "Use when writing about a specific intervention or issue and need "
        "supporting evidence with citations. Returns evidence items sorted "
        "by relevance score, deduplicated by document."
    )
    max_results = 5

    async def execute(
        self,
        state: Dict[str, Any],
        theme_name: str,
        min_relevance: int = 5,
        max_results: Optional[int] = None,
    ) -> ToolResult:
        """Execute the get_theme_evidence tool.

        Args:
            state: Current synthesis state.
            theme_name: Name of intervention or issue theme.
            min_relevance: Minimum RCS relevance score (0-10), default 5.
            max_results: Maximum evidence items to return.

        Returns:
            ToolResult with list of ThemeEvidenceItem.
        """
        max_results = max_results or self.max_results

        # Get pre-computed evidence from state
        scored_theme_evidence: List[ThemeEvidence] = (
            state.get("scored_theme_evidence") or []
        )
        scored_issue_evidence: List[ThemeEvidence] = (
            state.get("scored_issue_evidence") or []
        )
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}
        doc_scores: Dict[str, Dict[str, Any]] = state.get("doc_scores") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}

        # Search both theme and issue evidence
        all_evidence = scored_theme_evidence + scored_issue_evidence

        # Find matching theme
        matching_contexts: List[ScoredContext] = []
        theme_name_lower = theme_name.lower().strip()

        for te in all_evidence:
            # Match by theme_id or theme_name (case-insensitive partial match)
            if (te.theme_id and te.theme_id.lower() == theme_name_lower) or (
                te.theme_name and theme_name_lower in te.theme_name.lower()
            ):
                matching_contexts.extend(te.scored_contexts)

        if not matching_contexts:
            # Try fuzzy matching on all themes
            for te in all_evidence:
                if te.theme_name:
                    # Check if any word from theme_name appears in the search
                    theme_words = set(te.theme_name.lower().split())
                    search_words = set(theme_name_lower.split())
                    if theme_words & search_words:  # Intersection
                        matching_contexts.extend(te.scored_contexts)

        if not matching_contexts:
            # Fallback: use all_scored_contexts from state
            all_contexts: List[ScoredContext] = state.get("all_scored_contexts") or []
            if all_contexts:
                logger.info(
                    f"No theme match for '{theme_name}', "
                    f"falling back to all {len(all_contexts)} contexts"
                )
                matching_contexts = all_contexts
                fallback_used = True
            else:
                return ToolResult.ok([], fallback_used=True)
        else:
            fallback_used = False

        # Filter by relevance score
        filtered = [
            ctx for ctx in matching_contexts if ctx.relevance_score >= min_relevance
        ]

        # Sort by relevance (descending)
        sorted_contexts = sorted(
            filtered, key=lambda c: (-c.relevance_score, c.document_id)
        )

        # Deduplicate by document_id (keep highest scoring)
        seen_docs: set = set()
        deduped: List[ScoredContext] = []
        for ctx in sorted_contexts:
            if ctx.document_id not in seen_docs:
                deduped.append(ctx)
                seen_docs.add(ctx.document_id)

        # Limit results
        final_contexts = deduped[:max_results]

        # Convert to output format
        evidence_items: List[ThemeEvidenceItem] = []
        for ctx in final_contexts:
            # Get citation number
            cit_num = doc_citation_map.get(ctx.document_id, 0)
            if cit_num == 0:
                # Skip contexts without valid citations
                continue

            # Get document quality
            doc_score_info = doc_scores.get(ctx.document_id, {})
            evidence_strength = doc_score_info.get("evidence_score")

            # Get document title
            doc_meta = doc_metadata.get(ctx.document_id, {})
            doc_title = doc_meta.get("title") or ctx.document_title or "Unknown"

            evidence_items.append(
                ThemeEvidenceItem(
                    summary=ctx.summary,
                    citation_number=cit_num,
                    document_title=doc_title,
                    relevance_score=ctx.relevance_score,
                    document_quality=evidence_strength,
                    chunk_text=ctx.chunk_text[:500] if ctx.chunk_text else "",
                )
            )

        logger.info(
            f"get_theme_evidence('{theme_name}'): "
            f"found {len(evidence_items)} items "
            f"(filtered from {len(matching_contexts)}, fallback={fallback_used})"
        )

        return ToolResult.ok(
            [item.model_dump() for item in evidence_items],
            fallback_used=fallback_used,
        )

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "theme_name": {
                    "type": "string",
                    "description": (
                        "Name of intervention or issue theme to retrieve evidence for. "
                        "Examples: 'Physical activity interventions', "
                        "'School-based programmes', 'Dietary interventions'"
                    ),
                },
                "min_relevance": {
                    "type": "integer",
                    "description": (
                        "Minimum RCS relevance score (0-10). "
                        "Default is 5. Use higher values (6-8) for more precise evidence."
                    ),
                    "default": 5,
                    "minimum": 0,
                    "maximum": 10,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of evidence items to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["theme_name"],
        }


# Functional interface for direct use
async def get_theme_evidence(
    state: Dict[str, Any],
    theme_name: str,
    min_relevance: int = 5,
    max_results: int = 5,
) -> ToolResult:
    """Retrieve RCS-scored evidence for a specific theme.

    Convenience function wrapping GetThemeEvidenceTool.

    Args:
        state: Current synthesis state.
        theme_name: Name of intervention or issue theme.
        min_relevance: Minimum RCS relevance score (0-10).
        max_results: Maximum evidence items to return.

    Returns:
        ToolResult with list of evidence items.
    """
    tool = GetThemeEvidenceTool()
    return await tool.execute(
        state,
        theme_name=theme_name,
        min_relevance=min_relevance,
        max_results=max_results,
    )


# Register tool with global registry
_tool_instance = GetThemeEvidenceTool()
register_tool(_tool_instance)
