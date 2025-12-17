"""
Verification tools for agentic briefing.

Provides tools to verify claims against evidence, ensuring
all statements in the briefing are properly grounded.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.services.synthesis.schemas import ScoredContext
from app.services.synthesis.tools.base import (
    BaseTool,
    ToolResult,
    register_tool,
)
from app.services.synthesis.tools.models import (
    VERIFICATION_MODEL,
    VERIFICATION_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class ClaimVerificationResult(BaseModel):
    """Result of verifying a claim against evidence.

    Attributes:
        claim: The original claim text.
        is_supported: Whether the claim is supported by evidence.
        confidence: Confidence level (high, medium, low).
        supporting_citations: List of [N] citations that support the claim.
        issues: List of issues with the claim if not fully supported.
        suggested_revision: Suggested revision if claim needs rewording.
    """

    claim: str
    is_supported: bool
    confidence: str  # high, medium, low
    supporting_citations: List[int] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    suggested_revision: Optional[str] = None


class VerifyClaimSupportTool(BaseTool):
    """Tool to verify whether a claim is supported by evidence.

    Uses an LLM to assess whether a claim can be properly attributed
    to the available evidence. Essential for mandatory verification.
    """

    name = "verify_claim_support"
    description = (
        "Verify whether a claim is supported by available evidence. "
        "Use to check that statements can be properly cited. "
        "Returns whether the claim is supported, confidence level, "
        "and suggested revisions if needed."
    )
    max_results = 1

    async def execute(
        self,
        state: Dict[str, Any],
        claim: str,
        cited_numbers: Optional[List[int]] = None,
    ) -> ToolResult:
        """Verify a claim against evidence.

        Args:
            state: Current synthesis state.
            claim: The claim text to verify.
            cited_numbers: List of [N] citations claimed to support it.

        Returns:
            ToolResult with ClaimVerificationResult.
        """
        if not claim.strip():
            return ToolResult.fail("Empty claim")

        cited_numbers = cited_numbers or []

        # Get evidence from state
        grounded_citations = state.get("grounded_citations") or []
        all_scored_contexts: List[ScoredContext] = (
            state.get("all_scored_contexts") or []
        )
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}

        # Build evidence context for the cited sources
        evidence_context = self._build_evidence_context(
            cited_numbers,
            grounded_citations,
            all_scored_contexts,
            doc_citation_map,
        )

        if not evidence_context:
            # No evidence to verify against
            return ToolResult.ok(
                ClaimVerificationResult(
                    claim=claim,
                    is_supported=False,
                    confidence="low",
                    supporting_citations=[],
                    issues=["No evidence available for the cited sources"],
                    suggested_revision=None,
                ).model_dump()
            )

        # Use LLM to verify the claim
        try:
            result = await self._verify_with_llm(
                claim, cited_numbers, evidence_context, state
            )
            return ToolResult.ok(result.model_dump())
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return ToolResult.fail(f"Verification failed: {e}")

    def _build_evidence_context(
        self,
        cited_numbers: List[int],
        grounded_citations: List,
        all_scored_contexts: List[ScoredContext],
        doc_citation_map: Dict[str, int],
    ) -> str:
        """Build evidence context string for the LLM.

        Args:
            cited_numbers: Citation numbers to include.
            grounded_citations: All grounded citations.
            all_scored_contexts: Pre-computed RCS contexts.
            doc_citation_map: Document UUID to citation number mapping.

        Returns:
            Formatted evidence context string.
        """
        context_parts: List[str] = []

        # Get document IDs for the cited numbers
        cit_to_doc: Dict[int, str] = {v: k for k, v in doc_citation_map.items()}

        for cit_num in cited_numbers:
            doc_uuid = cit_to_doc.get(cit_num)
            if not doc_uuid:
                continue

            # Find the grounded citation
            cit_info = None
            for gc in grounded_citations:
                if gc.citation_number == cit_num:
                    cit_info = gc
                    break

            # Find RCS summaries for this document
            doc_summaries: List[str] = []
            for ctx in all_scored_contexts:
                if ctx.document_id == doc_uuid:
                    doc_summaries.append(
                        f"- {ctx.summary} (relevance: {ctx.relevance_score}/10)"
                    )

            if cit_info or doc_summaries:
                part = f"[{cit_num}] "
                if cit_info:
                    part += (
                        f"{cit_info.author_short} ({cit_info.year}): {cit_info.title}\n"
                    )
                    if cit_info.supporting_quote:
                        part += f'Quote: "{cit_info.supporting_quote[:300]}..."\n'
                if doc_summaries:
                    part += "Summaries:\n" + "\n".join(doc_summaries[:3])
                context_parts.append(part)

        return "\n\n".join(context_parts)

    async def _verify_with_llm(
        self,
        claim: str,
        cited_numbers: List[int],
        evidence_context: str,
        state: Dict[str, Any],
    ) -> ClaimVerificationResult:
        """Use LLM to verify the claim against evidence.

        Args:
            claim: The claim to verify.
            cited_numbers: Citations claimed to support it.
            evidence_context: Formatted evidence for the LLM.
            state: Synthesis state (for Langfuse config).

        Returns:
            ClaimVerificationResult.
        """
        llm = ChatOpenAI(
            model=VERIFICATION_MODEL,
            temperature=VERIFICATION_TEMPERATURE,
        )

        prompt = f"""You are a verification assistant. Your task is to check whether a claim is properly supported by the provided evidence.

## Claim to Verify
"{claim}"

## Cited Sources
{cited_numbers if cited_numbers else "No citations provided"}

## Available Evidence
{evidence_context}

## Instructions
1. Assess whether the claim is directly supported by the evidence
2. Check if the cited sources actually contain information that supports the claim
3. Identify any issues (overclaiming, misattribution, unsupported statements)
4. Suggest revisions if the claim needs to be more accurately worded

Respond in JSON format:
{{
    "is_supported": true/false,
    "confidence": "high"/"medium"/"low",
    "supporting_citations": [list of citation numbers that actually support the claim],
    "issues": [list of issues found, empty if none],
    "suggested_revision": "revised claim text if needed, null if claim is fine"
}}

Only output the JSON, no other text."""

        # Build Langfuse config
        config = {}
        handler = state.get("langfuse_handler")
        if handler:
            config = {
                "callbacks": [handler],
                "tags": [
                    "component:synthesis",
                    "component:synthesis.verification",
                    f"model:{VERIFICATION_MODEL}",
                ],
                "run_name": "verify_claim",
            }

        response = await llm.ainvoke(prompt, config=config)

        try:
            # Parse JSON response
            content = response.content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            data = json.loads(content)

            return ClaimVerificationResult(
                claim=claim,
                is_supported=data.get("is_supported", False),
                confidence=data.get("confidence", "low"),
                supporting_citations=data.get("supporting_citations", []),
                issues=data.get("issues", []),
                suggested_revision=data.get("suggested_revision"),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse verification response: {e}")
            # Conservative fallback
            return ClaimVerificationResult(
                claim=claim,
                is_supported=False,
                confidence="low",
                supporting_citations=[],
                issues=["Could not parse verification result"],
                suggested_revision=None,
            )

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": (
                        "The claim or statement to verify. "
                        "Include the full statement with any citation markers."
                    ),
                },
                "cited_numbers": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "description": (
                        "List of [N] citation numbers that the claim references. "
                        "Example: if claim says '[3], [5]' then provide [3, 5]."
                    ),
                },
            },
            "required": ["claim"],
        }


class VerifyMultipleClaimsTool(BaseTool):
    """Tool to verify multiple claims in batch.

    More efficient than calling verify_claim_support multiple times.
    Essential for mandatory verification of all major claims.
    """

    name = "verify_multiple_claims"
    description = (
        "Verify multiple claims against evidence in batch. "
        "More efficient than verifying one at a time. "
        "Use after generating a section to verify all major claims."
    )
    max_results = 10

    async def execute(
        self,
        state: Dict[str, Any],
        claims: List[Dict[str, Any]],
    ) -> ToolResult:
        """Verify multiple claims.

        Args:
            state: Current synthesis state.
            claims: List of {"claim": str, "cited_numbers": [int]} dicts.

        Returns:
            ToolResult with list of ClaimVerificationResult.
        """
        single_tool = VerifyClaimSupportTool()
        results: List[Dict[str, Any]] = []

        for claim_data in claims[: self.max_results]:
            claim = claim_data.get("claim", "")
            cited = claim_data.get("cited_numbers", [])

            result = await single_tool.execute(
                state,
                claim=claim,
                cited_numbers=cited,
            )

            if result.success:
                results.append(result.data)
            else:
                results.append(
                    ClaimVerificationResult(
                        claim=claim,
                        is_supported=False,
                        confidence="low",
                        supporting_citations=[],
                        issues=[result.error or "Verification failed"],
                        suggested_revision=None,
                    ).model_dump()
                )

        # Summary stats
        supported = sum(1 for r in results if r.get("is_supported", False))
        logger.info(
            f"verify_multiple_claims: {supported}/{len(results)} claims supported"
        )

        return ToolResult.ok(
            {
                "results": results,
                "summary": {
                    "total": len(results),
                    "supported": supported,
                    "unsupported": len(results) - supported,
                },
            }
        )

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "string"},
                            "cited_numbers": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                        "required": ["claim"],
                    },
                    "description": (
                        "List of claims to verify. Each claim should have "
                        "'claim' text and optional 'cited_numbers' array."
                    ),
                    "maxItems": 10,
                },
            },
            "required": ["claims"],
        }


# Functional interfaces
async def verify_claim_support(
    state: Dict[str, Any],
    claim: str,
    cited_numbers: Optional[List[int]] = None,
) -> ToolResult:
    """Verify whether a claim is supported by evidence.

    Convenience function wrapping VerifyClaimSupportTool.

    Args:
        state: Current synthesis state.
        claim: The claim text to verify.
        cited_numbers: List of [N] citations claimed to support it.

    Returns:
        ToolResult with ClaimVerificationResult.
    """
    tool = VerifyClaimSupportTool()
    return await tool.execute(state, claim=claim, cited_numbers=cited_numbers)


async def verify_multiple_claims(
    state: Dict[str, Any],
    claims: List[Dict[str, Any]],
) -> ToolResult:
    """Verify multiple claims in batch.

    Convenience function wrapping VerifyMultipleClaimsTool.

    Args:
        state: Current synthesis state.
        claims: List of {"claim": str, "cited_numbers": [int]} dicts.

    Returns:
        ToolResult with verification results and summary.
    """
    tool = VerifyMultipleClaimsTool()
    return await tool.execute(state, claims=claims)


# Register tools
register_tool(VerifyClaimSupportTool())
register_tool(VerifyMultipleClaimsTool())
