"""
Contextual Summarisation (RCS) Node for the synthesis workflow.

Implements paper-qa's Ranking and Contextual Summarisation technique:
1. Takes retrieved chunks + question/theme
2. Summarises each chunk in context of the question
3. Assigns relevance score (0-10)
4. Returns ScoredContext objects for quality-based filtering

This is the core enhancement that grounds the executive briefing in
relevance-scored evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from app.utils.llm.llm_utils import get_llm, build_langfuse_metadata
from app.services.synthesis.schemas import (
    RetrievedChunk,
    ScoredContext,
    ThemeEvidence,
    RCSConfig,
)
from app.services.synthesis.state import SynthesisState
from app.services.synthesis.utils import escape_braces

logger = logging.getLogger(__name__)

# Model for RCS - using mini model for cost efficiency at high volume
RCS_MODEL = "gpt-4.1-mini"


# =============================================================================
# PROMPTS
# =============================================================================

RCS_SYSTEM_PROMPT = """You are an expert policy analyst evaluating evidence relevance.

For the given excerpt from a policy document, determine if it contains information 
relevant to answering the question. If relevant, provide a concise summary of the 
key points that help answer the question.

Respond with JSON only:
{
  "summary": "Concise summary of relevant information (max 100 words). Empty string if not relevant.",
  "relevance_score": <integer 0-10>
}

Scoring guide:
- 0: Not relevant at all
- 1-3: Tangentially related, minimal direct relevance  
- 4-6: Moderately relevant, provides useful context
- 7-8: Highly relevant, directly addresses the question
- 9-10: Critical evidence, directly answers key aspects

Be specific. Include numbers, findings, and direct quotes where valuable.
If the excerpt is not relevant, return empty summary with score 0."""

RCS_USER_PROMPT = """Question: {question}

Document: {document_title}
Year: {year}

Excerpt:
---
{chunk_text}
---

Evaluate this excerpt's relevance and provide a contextual summary in JSON format."""


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def generate_citation_key(document_id: str, chunk_id: str) -> str:
    """Generate a short citation key for inline references.

    Format: pqa-<8-char-hash> (similar to paper-qa style)
    """
    combined = f"{document_id}:{chunk_id}"
    hash_val = hashlib.md5(combined.encode()).hexdigest()[:8]
    return f"pqa-{hash_val}"


def parse_rcs_response(response_text: str) -> Dict[str, Any]:
    """Parse the JSON response from RCS LLM call.

    Handles common parsing edge cases:
    - Markdown code blocks
    - Trailing text
    - Invalid JSON
    """
    text = response_text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    # Find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        result = json.loads(text)
        # Validate required fields
        if "summary" not in result:
            result["summary"] = ""
        if "relevance_score" not in result:
            result["relevance_score"] = 0

        # Ensure score is int in valid range
        score = result["relevance_score"]
        if isinstance(score, str):
            score = int(score) if score.isdigit() else 0
        result["relevance_score"] = max(0, min(10, int(score)))

        return result
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse RCS response: {e}")
        return {"summary": "", "relevance_score": 0}


def build_full_citation(chunk: RetrievedChunk) -> str:
    """Build a full citation string from chunk metadata."""
    parts = []
    if chunk.author_short:
        parts.append(chunk.author_short)
    if chunk.year:
        parts.append(f"({chunk.year})")
    if chunk.doc_title:
        parts.append(f'"{chunk.doc_title}"')
    return " ".join(parts) if parts else "Unknown source"


# =============================================================================
# CORE RCS FUNCTIONS
# =============================================================================


async def contextual_summarise_chunk(
    chunk: RetrievedChunk,
    question: str,
    theme_id: Optional[str] = None,
    theme_name: Optional[str] = None,
    state: Optional[SynthesisState] = None,
) -> ScoredContext:
    """Summarise a single chunk in context of the question and score relevance.

    Args:
        chunk: The retrieved chunk to summarise
        question: The question/theme to evaluate relevance against
        theme_id: Optional theme identifier for grouping
        theme_name: Optional theme name for display
        state: Optional workflow state for Langfuse tracing

    Returns:
        ScoredContext with summary and relevance score
    """
    llm = get_llm(RCS_MODEL, temperature=0)

    # Truncate chunk text for token limits
    chunk_text = chunk.content[:2500] if chunk.content else ""

    prompt = RCS_USER_PROMPT.format(
        question=question,
        document_title=chunk.doc_title or "Unknown",
        year=chunk.year or "Unknown",
        chunk_text=escape_braces(chunk_text),
    )

    try:
        messages = [
            SystemMessage(content=RCS_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        # Build Langfuse config from state if available
        config: Dict[str, Any] = {}
        if state:
            handler = state.get("langfuse_handler")
            if handler:
                tags = [
                    "component:synthesis",
                    "component:synthesis.rcs",
                    f"model:{RCS_MODEL}",
                ]
                config = {
                    "callbacks": [handler],
                    "tags": tags,
                    "metadata": build_langfuse_metadata(
                        tags=tags,
                        session_id=state.get("langfuse_session_id"),
                        user_id=state.get("policy_user_id"),
                        project_id=state.get("project_id"),
                    ),
                    "run_name": f"rcs:{chunk.chunk_id[:8]}",
                }

        response = await llm.ainvoke(messages, config=config)
        result = parse_rcs_response(response.content)

    except Exception as e:
        logger.warning(f"RCS failed for chunk {chunk.chunk_id}: {e}")
        result = {"summary": "", "relevance_score": 0}

    # Generate citation key
    citation_key = generate_citation_key(chunk.document_id, chunk.chunk_id)

    return ScoredContext(
        context_id=str(uuid4()),
        summary=result["summary"],
        relevance_score=result["relevance_score"],
        question=question,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_title=chunk.doc_title or "",
        chunk_text=chunk_text[:500],  # Store truncated for reference
        citation_key=citation_key,
        full_citation=build_full_citation(chunk),
        theme_id=theme_id,
        theme_name=theme_name,
    )


async def contextual_summarise_batch(
    chunks: List[RetrievedChunk],
    question: str,
    theme_id: Optional[str] = None,
    theme_name: Optional[str] = None,
    concurrency: int = 10,
    state: Optional[SynthesisState] = None,
) -> List[ScoredContext]:
    """Process multiple chunks concurrently with RCS.

    Args:
        chunks: List of retrieved chunks to process
        question: The question/theme for relevance evaluation
        theme_id: Optional theme identifier
        theme_name: Optional theme name
        concurrency: Maximum parallel RCS calls
        state: Optional workflow state for Langfuse tracing

    Returns:
        List of ScoredContext objects (may be fewer than input if errors occur)
    """
    if not chunks:
        return []

    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_semaphore(chunk: RetrievedChunk) -> Optional[ScoredContext]:
        async with semaphore:
            try:
                return await contextual_summarise_chunk(
                    chunk=chunk,
                    question=question,
                    theme_id=theme_id,
                    theme_name=theme_name,
                    state=state,
                )
            except Exception as e:
                logger.warning(f"RCS batch item failed: {e}")
                return None

    results = await asyncio.gather(
        *[process_with_semaphore(c) for c in chunks],
        return_exceptions=True,
    )

    # Filter out None results and exceptions
    scored = []
    for r in results:
        if isinstance(r, ScoredContext):
            scored.append(r)
        elif isinstance(r, Exception):
            logger.warning(f"RCS exception: {r}")

    return scored


def generate_theme_question(
    theme_name: str,
    theme_description: str,
    research_question: str,
) -> str:
    """Generate a targeted question for RCS based on a theme.

    Combines the theme context with the research question for
    more targeted relevance evaluation.
    """
    return (
        f"What evidence addresses '{theme_name}' in the context of: {research_question}? "
        f"Theme focus: {theme_description}"
    )


# =============================================================================
# NODE FUNCTIONS
# =============================================================================


async def _apply_rcs_to_evidence(
    *,
    state: SynthesisState,
    evidence_key: str,
    aggregate_items: List[Any],
    name_attr: str,
    description_attr: str,
    result_key: str,
    collect_all_contexts: bool = False,
    existing_contexts: Optional[List[ScoredContext]] = None,
    existing_gaps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Shared RCS application for theme/issue/outcome evidence."""
    evidence = state.get(evidence_key) or {}
    research_question = state.get("research_question", "")
    rcs_config = state.get("rcs_config") or RCSConfig()

    item_lookup = {
        getattr(item, name_attr): item
        for item in aggregate_items
        if getattr(item, name_attr, None)
    }

    results: List[ThemeEvidence] = []
    all_scored_contexts: List[ScoredContext] = list(existing_contexts or [])
    themes_with_gaps: List[str] = list(existing_gaps or [])

    for theme_id, chunks in evidence.items():
        if not chunks:
            themes_with_gaps.append(theme_id)
            continue

        item = item_lookup.get(theme_id)
        theme_description = getattr(item, description_attr, "") if item else ""

        theme_question = generate_theme_question(
            theme_name=theme_id,
            theme_description=theme_description,
            research_question=research_question,
        )

        scored_contexts = await contextual_summarise_batch(
            chunks=chunks,
            question=theme_question,
            theme_id=theme_id,
            theme_name=theme_id,
            concurrency=rcs_config.rcs_concurrency,
            state=state,
        )

        filtered_contexts = [
            c
            for c in scored_contexts
            if c.relevance_score >= rcs_config.score_threshold
        ]
        filtered_contexts.sort(key=lambda c: c.relevance_score, reverse=True)
        filtered_contexts = filtered_contexts[: rcs_config.max_contexts_per_theme]

        high_quality = [
            c
            for c in filtered_contexts
            if c.relevance_score >= rcs_config.high_quality_threshold
        ]
        evidence_sufficient = len(high_quality) >= rcs_config.min_high_quality_per_theme
        if not evidence_sufficient:
            themes_with_gaps.append(theme_id)

        results.append(
            ThemeEvidence(
                theme_id=theme_id,
                theme_name=theme_id,
                theme_description=theme_description,
                theme_question=theme_question,
                scored_contexts=filtered_contexts,
                total_chunks_retrieved=len(chunks),
                total_chunks_scored=len(scored_contexts),
                high_quality_count=len(high_quality),
                evidence_sufficient=evidence_sufficient,
            )
        )
        if collect_all_contexts:
            all_scored_contexts.extend(filtered_contexts)

    response: Dict[str, Any] = {result_key: results}
    if collect_all_contexts:
        response["all_scored_contexts"] = all_scored_contexts
        response["themes_with_gaps"] = themes_with_gaps
    return response


async def apply_rcs_to_theme_evidence(
    state: SynthesisState,
) -> Dict[str, Any]:
    """Apply RCS to existing theme_evidence to create scored contexts.

    This node takes the current theme_evidence (Dict[str, List[RetrievedChunk]])
    and applies contextual summarisation to create scored, grounded evidence.

    Args:
        state: Current workflow state with theme_evidence populated

    Returns:
        State update with scored_theme_evidence
    """
    print("--- Applying Contextual Summarisation (RCS) to Theme Evidence ---")

    response = await _apply_rcs_to_evidence(
        state=state,
        evidence_key="theme_evidence",
        aggregate_items=state.get("aggregated_interventions") or [],
        name_attr="intervention_name",
        description_attr="brief_description",
        result_key="scored_theme_evidence",
        collect_all_contexts=True,
    )

    scored_theme_evidence = response.get("scored_theme_evidence", [])
    total_high_quality = sum(te.high_quality_count for te in scored_theme_evidence)
    themes_with_gaps = response.get("themes_with_gaps", [])
    all_scored_contexts = response.get("all_scored_contexts", [])

    print(
        f"RCS complete: {len(all_scored_contexts)} scored contexts, "
        f"{total_high_quality} high-quality, {len(themes_with_gaps)} themes with gaps"
    )

    return {
        **response,
        "rcs_iterations_run": 1,
    }


async def apply_rcs_to_issue_evidence(
    state: SynthesisState,
) -> Dict[str, Any]:
    """Apply RCS to existing issue_evidence to create scored contexts.

    Similar to apply_rcs_to_theme_evidence but for issue themes.

    Args:
        state: Current workflow state with issue_evidence populated

    Returns:
        State update with scored_issue_evidence
    """
    print("--- Applying Contextual Summarisation (RCS) to Issue Evidence ---")

    response = await _apply_rcs_to_evidence(
        state=state,
        evidence_key="issue_evidence",
        aggregate_items=state.get("aggregated_issues") or [],
        name_attr="issue_theme",
        description_attr="summary_description",
        result_key="scored_issue_evidence",
    )

    scored_issue_evidence = response.get("scored_issue_evidence", [])
    print(
        f"RCS for issues complete: {len(scored_issue_evidence)} issue themes processed"
    )

    return response


async def apply_rcs_to_outcome_evidence(
    state: SynthesisState,
) -> Dict[str, Any]:
    """Apply RCS to existing outcome_evidence to create scored contexts.

    This mirrors apply_rcs_to_theme_evidence/apply_rcs_to_issue_evidence, but uses
    outcome themes so outcome-related sections can draw from pre-scored evidence.

    Args:
        state: Current workflow state with outcome_evidence populated.

    Returns:
        State update with scored_outcome_evidence (and updated all_scored_contexts).
    """
    print("--- Applying Contextual Summarisation (RCS) to Outcome Evidence ---")

    response = await _apply_rcs_to_evidence(
        state=state,
        evidence_key="outcome_evidence",
        aggregate_items=state.get("aggregated_outcomes") or [],
        name_attr="outcome_name",
        description_attr="outcome_description",
        result_key="scored_outcome_evidence",
        collect_all_contexts=True,
        existing_contexts=state.get("all_scored_contexts") or [],
        existing_gaps=state.get("themes_with_gaps") or [],
    )

    scored_outcome_evidence = response.get("scored_outcome_evidence", [])
    print(
        f"RCS for outcomes complete: {len(scored_outcome_evidence)} outcome themes processed"
    )

    return response
