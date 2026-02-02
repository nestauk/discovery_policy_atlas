"""
Document quality tools for agentic briefing.

Provides tools to query document quality scores for prioritising citations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.services.synthesis.schemas import CitationInfo
from app.services.synthesis.tools.base import (
    BaseTool,
    ToolResult,
    register_tool,
)

logger = logging.getLogger(__name__)


class DocumentQualityInfo(BaseModel):
    """Quality assessment for a document.

    Attributes:
        citation_number: The [N] citation number.
        title: Document title.
        evidence_strength: 1-5 star rating for evidence quality.
        evidence_justification: Why this rating was given.
        impact_score: 1-5 star rating for document impact.
        impact_justification: Why this rating was given.
        study_type: Type of study (e.g., "RCT", "Systematic Review").
        year: Publication year.
        source: Source database (e.g., "openalex", "pubmed").
    """

    citation_number: int
    title: str
    evidence_strength: Optional[int] = None
    evidence_justification: str = ""
    impact_score: Optional[float] = None
    impact_justification: str = ""
    study_type: Optional[str] = None
    year: Optional[int] = None
    source: Optional[str] = None


class GetDocumentQualityTool(BaseTool):
    """Tool to get quality assessment for a document by citation number.

    Queries pre-computed doc_scores and doc_metadata from the synthesis state.
    """

    name = "get_document_quality"
    description = (
        "Get quality assessment for a document by citation number. "
        "Use to verify a source is high-quality before citing. "
        "Returns evidence strength (1-5 stars), impact score (1-5), "
        "study type, and justifications."
    )
    max_results = 1

    async def execute(
        self,
        state: Dict[str, Any],
        citation_number: int,
    ) -> ToolResult:
        """Execute the get_document_quality tool.

        Args:
            state: Current synthesis state.
            citation_number: The [N] citation number to look up.

        Returns:
            ToolResult with DocumentQualityInfo or error.
        """
        # Get mappings from state
        grounded_citations: List[CitationInfo] = state.get("grounded_citations") or []
        doc_scores: Dict[str, Dict[str, Any]] = state.get("doc_scores") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}

        # Find citation by number
        target_citation: Optional[CitationInfo] = None
        for cit in grounded_citations:
            if cit.citation_number == citation_number:
                target_citation = cit
                break

        if not target_citation:
            return ToolResult.fail(
                f"Citation [{citation_number}] not found in grounded citations"
            )

        doc_uuid = target_citation.analysis_document_id

        # Get quality scores
        scores = doc_scores.get(doc_uuid, {})
        metadata = doc_metadata.get(doc_uuid, {})

        quality_info = DocumentQualityInfo(
            citation_number=citation_number,
            title=metadata.get("title") or target_citation.document_title or "Unknown",
            evidence_strength=scores.get("evidence_score"),
            evidence_justification=scores.get("evidence_justification", ""),
            impact_score=scores.get("impact_score"),
            impact_justification=scores.get("impact_justification", ""),
            study_type=metadata.get("document_type"),
            year=metadata.get("year"),
            source=metadata.get("source"),
        )

        logger.info(
            f"get_document_quality([{citation_number}]): "
            f"evidence={quality_info.evidence_strength}/5, "
            f"impact={quality_info.impact_score}/5"
        )

        return ToolResult.ok(quality_info.model_dump())

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "citation_number": {
                    "type": "integer",
                    "description": (
                        "The [N] citation number to look up. "
                        "This is the number used in the briefing text, e.g., [3]."
                    ),
                    "minimum": 1,
                },
            },
            "required": ["citation_number"],
        }


class GetMultipleDocumentQualityTool(BaseTool):
    """Tool to get quality assessments for multiple documents at once.

    More efficient than calling get_document_quality multiple times.
    """

    name = "get_multiple_document_quality"
    description = (
        "Get quality assessments for multiple documents by citation numbers. "
        "More efficient than calling get_document_quality multiple times. "
        "Use when you need to compare quality across several sources."
    )
    max_results = 10

    async def execute(
        self,
        state: Dict[str, Any],
        citation_numbers: List[int],
    ) -> ToolResult:
        """Execute the get_multiple_document_quality tool.

        Args:
            state: Current synthesis state.
            citation_numbers: List of [N] citation numbers to look up.

        Returns:
            ToolResult with list of DocumentQualityInfo.
        """
        single_tool = GetDocumentQualityTool()
        results: List[Dict[str, Any]] = []
        errors: List[str] = []

        for cit_num in citation_numbers[: self.max_results]:
            result = await single_tool.execute(state, citation_number=cit_num)
            if result.success:
                results.append(result.data)
            else:
                errors.append(f"[{cit_num}]: {result.error}")

        if not results and errors:
            return ToolResult.fail("; ".join(errors))

        # Sort by evidence strength (highest first)
        results.sort(key=lambda x: (x.get("evidence_strength") or 0), reverse=True)

        logger.info(
            f"get_multiple_document_quality({citation_numbers}): "
            f"found {len(results)}, errors={len(errors)}"
        )

        return ToolResult.ok(results)

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "citation_numbers": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "description": (
                        "List of [N] citation numbers to look up. "
                        "Maximum 10 citations per call."
                    ),
                    "maxItems": 10,
                },
            },
            "required": ["citation_numbers"],
        }


# Functional interface for direct use
async def get_document_quality(
    state: Dict[str, Any],
    citation_number: int,
) -> ToolResult:
    """Get quality assessment for a document by citation number.

    Convenience function wrapping GetDocumentQualityTool.

    Args:
        state: Current synthesis state.
        citation_number: The [N] citation number to look up.

    Returns:
        ToolResult with DocumentQualityInfo or error.
    """
    tool = GetDocumentQualityTool()
    return await tool.execute(state, citation_number=citation_number)


async def get_multiple_document_quality(
    state: Dict[str, Any],
    citation_numbers: List[int],
) -> ToolResult:
    """Get quality assessments for multiple documents.

    Convenience function wrapping GetMultipleDocumentQualityTool.

    Args:
        state: Current synthesis state.
        citation_numbers: List of [N] citation numbers to look up.

    Returns:
        ToolResult with list of DocumentQualityInfo.
    """
    tool = GetMultipleDocumentQualityTool()
    return await tool.execute(state, citation_numbers=citation_numbers)


# Register tools with global registry
register_tool(GetDocumentQualityTool())
register_tool(GetMultipleDocumentQualityTool())
