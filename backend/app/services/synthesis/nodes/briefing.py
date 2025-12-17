"""
Briefing generation node for the synthesis workflow.

Uses the tool-augmented approach with gpt-5.2 orchestration and
mandatory verification to generate grounded executive briefings.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.services.synthesis.state import SynthesisState, ScoredContext
from app.services.synthesis.schemas import (
    StructuredBriefing,
    BackgroundSection,
    CoreAnswer,
    InterventionTableRow,
    RecommendationItem,
    CitationInfo,
    EvidenceSnapshotRow,
    TopCitationItem,
)
from app.services.synthesis.tools.orchestrator import (
    BriefingOrchestrator,
    SectionOutput,
)
from app.services.synthesis.tools.models import GENERATION_MODEL

logger = logging.getLogger(__name__)


@dataclass
class BriefingConfig:
    """Configuration for briefing generation.

    Attributes:
        max_tool_calls_per_section: Maximum tool calls allowed per section.
        max_verification_retries: Maximum retries if verification fails.
        min_evidence_per_section: Minimum evidence items before generation.
    """

    max_tool_calls_per_section: int = 5
    max_verification_retries: int = 2
    min_evidence_per_section: int = 3


# Section definitions with instructions
SECTION_CONFIGS = {
    "background": {
        "name": "Background Context",
        "instructions": """
Write a concise background section (2-3 paragraphs) that:
1. Establishes the policy context and why this topic matters
2. Summarises the scope of evidence reviewed
3. Highlights the key themes that emerged from the analysis

Focus on setting up the reader to understand the interventions and recommendations.
""",
        "additional": "Format as flowing prose paragraphs. Include 3-5 citations.",
    },
    "interventions": {
        "name": "Policy Interventions Analysis",
        "instructions": """
Create a structured analysis of policy interventions found in the evidence:
1. List each major intervention type identified
2. For each intervention, provide:
   - Brief description of what it involves
   - Evidence strength (how well studied)
   - Effect direction (positive, negative, mixed, unclear)
   - Key findings from the research

Prioritise interventions with stronger evidence bases.
""",
        "additional": "Format as a markdown table with columns: Intervention | Description | Evidence | Effect | Key Findings | Citations",
    },
    "core_answer": {
        "name": "Core Findings",
        "instructions": """
Write the core findings section as flowing prose (2-3 paragraphs) that:
1. Opens with a direct, bold headline answer to the research question (1-2 sentences)
2. Synthesises the most important findings across interventions
3. Highlights what works, what doesn't, and what's uncertain
4. Notes any important caveats or limitations

IMPORTANT: Every factual claim MUST have a citation in [N] format immediately after the claim.
Example: "School-based programmes show consistent effectiveness [4][10]."

This is the most important section - be precise and well-cited.
""",
        "additional": "Every major claim must have at least one citation. Use [N] format consistently.",
    },
    "recommendations": {
        "name": "Policy Recommendations",
        "instructions": """
Provide 3-5 evidence-based policy recommendations. For EACH recommendation, use this EXACT structure:

**[Number]. [Short Action Title]**: [Main recommendation text with supporting evidence and citations]
- **Why**: [Brief explanation of why this is recommended, with citation]
- **Strength of evidence**: [High/Moderate/Low] — [Brief justification]
- **Implementation**: [Key implementation considerations]

Example format:
**1. Scale up multi-component school programmes**: Evidence supports comprehensive school interventions combining nutrition, physical activity and behavioural components [4][10].
- **Why**: Multi-component approaches show larger effects than single-component interventions [4].
- **Strength of evidence**: Moderate — Multiple systematic reviews demonstrate consistent benefits.
- **Implementation**: Integrate into existing curricula; train teachers; ensure parental engagement.

Make each recommendation specific and actionable for policymakers.
""",
        "additional": "Use the exact format shown. Every claim needs a citation in [N] format.",
    },
}


async def generate_briefing(state: SynthesisState) -> SynthesisState:
    """Generate executive briefing using tool-augmented approach.

    Uses the BriefingOrchestrator to:
    1. Gather evidence using tools (get_theme_evidence, search_extractions, etc.)
    2. Generate each section with gpt-5-mini
    3. Verify each section (mandatory) with retry logic

    Args:
        state: Current synthesis state with RCS results.

    Returns:
        State update with structured_briefing and briefing_results.
    """
    print("--- Phase 6: Generating Executive Briefing ---")

    # Get research question for context
    research_question = state.get("research_question", "")
    if not research_question:
        # Try to extract from project data
        research_question = _extract_research_question(state)

    # Initialise orchestrator
    orchestrator = BriefingOrchestrator(state)
    config = BriefingConfig()

    # Track results
    section_outputs: Dict[str, SectionOutput] = {}
    total_tool_calls = 0
    verification_failures: List[str] = []

    # Generate each section
    for section_key, section_config in SECTION_CONFIGS.items():
        print(f"  Generating section: {section_config['name']}...")

        # Add research question context to instructions
        instructions = section_config["instructions"]
        if research_question:
            instructions = f"Research Question: {research_question}\n\n{instructions}"

        try:
            output = await orchestrator.generate_section(
                section_name=section_config["name"],
                section_instructions=instructions,
                additional_instructions=section_config.get("additional", ""),
                max_retries=config.max_verification_retries,
            )

            section_outputs[section_key] = output
            total_tool_calls += output.tool_calls_made

            if not output.verification_passed:
                verification_failures.append(section_key)
                logger.warning(
                    f"Section '{section_key}' verification failed: "
                    f"{output.verification_issues}"
                )

            print(
                f"    ✓ {section_config['name']}: "
                f"{output.tool_calls_made} tool calls, "
                f"verification={'✓' if output.verification_passed else '✗'}"
            )

        except Exception as e:
            logger.error(f"Failed to generate section '{section_key}': {e}")
            # Use fallback content
            section_outputs[section_key] = SectionOutput(
                content=f"[Section generation failed: {e}]",
                citations_used=[],
                verification_passed=False,
                verification_issues=[str(e)],
                tool_calls_made=0,
            )

    # Build structured briefing from sections
    structured_briefing = await _build_structured_briefing(
        section_outputs,
        state.get("grounded_citations") or [],
        state.get("aggregated_interventions") or [],
        research_question,
        state.get("doc_scores") or {},
        state.get("all_scored_contexts") or [],
        state.get("doc_citation_map") or {},
    )

    # Collect all citations used
    all_citations_used = set()
    for output in section_outputs.values():
        all_citations_used.update(output.citations_used)

    # Build citation_map for database persistence (keyed by citation_key like "[1]")
    grounded_citations = state.get("grounded_citations") or []
    citation_map = {
        f"[{c.citation_number}]": c for c in grounded_citations if c.citation_number
    }

    print("\n  Briefing complete:")
    print(f"    - Total tool calls: {total_tool_calls}")
    print(f"    - Unique citations: {len(all_citations_used)}")
    print(f"    - Citation map entries: {len(citation_map)}")
    print(f"    - Verification failures: {len(verification_failures)}")

    return {
        "structured_briefing": structured_briefing,
        "citation_map": citation_map,  # For database persistence
        "briefing_results": {
            "total_tool_calls": total_tool_calls,
            "section_outputs": {
                k: {
                    "tool_calls": v.tool_calls_made,
                    "citations": v.citations_used,
                    "verified": v.verification_passed,
                    "issues": v.verification_issues,
                }
                for k, v in section_outputs.items()
            },
            "verification_failures": verification_failures,
            "all_citations_used": list(all_citations_used),
        },
    }


def _extract_research_question(state: SynthesisState) -> str:
    """Extract research question from state or project data.

    Args:
        state: Current synthesis state.

    Returns:
        Research question string or empty string.
    """
    # Try direct state field
    if state.get("research_question"):
        return state["research_question"]

    # Try to infer from evidence coverage
    coverage = state.get("evidence_coverage")
    if coverage and hasattr(coverage, "total_documents"):
        return (
            f"Analysis of {coverage.total_documents} documents on policy interventions"
        )

    return ""


async def _build_structured_briefing(
    section_outputs: Dict[str, SectionOutput],
    grounded_citations: List[CitationInfo],
    interventions: List,
    research_question: str,
    doc_scores: Dict[str, Dict[str, Any]],
    all_scored_contexts: List[ScoredContext],
    doc_citation_map: Dict[str, int],
) -> StructuredBriefing:
    """Build StructuredBriefing from section outputs.

    Args:
        section_outputs: Generated sections.
        grounded_citations: Available citations.
        interventions: Aggregated interventions for table.
        research_question: The original research question.
        doc_scores: Document quality scores for citation ranking.
        all_scored_contexts: RCS-scored contexts for citation ranking.
        doc_citation_map: Document UUID to citation number mapping.

    Returns:
        StructuredBriefing object matching frontend schema.
    """

    # Parse core answer - use full content, not just first line
    core_output = section_outputs.get(
        "core_answer", SectionOutput(content="", citations_used=[])
    )

    # The full content becomes the answer; extract first sentence as a directive if present
    full_content = core_output.content.strip()

    # Try to extract a headline (first sentence before a period)
    # first_para = full_content.split("\n\n")[0] if full_content else ""

    core_answer = CoreAnswer(
        query=research_question or "Policy intervention analysis",
        answer=full_content,  # Full synthesis content
        directive="",  # Could be populated with a key recommendation
    )

    # Parse background into paragraphs
    bg_output = section_outputs.get(
        "background", SectionOutput(content="", citations_used=[])
    )
    paragraphs = [p.strip() for p in bg_output.content.split("\n\n") if p.strip()]

    background_section = BackgroundSection(
        title="Policy Background & Context",
        paragraphs=paragraphs,
        citation_numbers_used=bg_output.citations_used,
    )

    # Parse interventions table - filter nulls and limit to top 6
    int_output = section_outputs.get(
        "interventions", SectionOutput(content="", citations_used=[])
    )
    all_intervention_rows = _parse_intervention_table(int_output.content, interventions)

    # Filter out null/empty rows and limit to top 6 by citation count
    intervention_rows = [
        row
        for row in all_intervention_rows
        if row.intervention_name
        and row.intervention_name.strip() not in ("", "---", "-")
    ]
    # Sort by number of citations (most evidence first), then limit
    intervention_rows = sorted(
        intervention_rows, key=lambda r: len(r.citation_numbers), reverse=True
    )[:6]

    # Parse recommendations
    rec_output = section_outputs.get(
        "recommendations", SectionOutput(content="", citations_used=[])
    )
    recommendation_items = _parse_recommendations(rec_output.content)

    # Build top citations with LLM-generated contextual reasons
    top_citations = await _build_top_citations_async(
        grounded_citations,
        section_outputs,
        doc_scores,
        all_scored_contexts,
        doc_citation_map,
        research_question,
        max_citations=8,
    )

    # Build evidence snapshot summary
    evidence_snapshot = [
        EvidenceSnapshotRow(
            metric="Total Sources", detail=str(len(grounded_citations))
        ),
    ]

    return StructuredBriefing(
        core_answer=core_answer,
        evidence_snapshot=evidence_snapshot,
        evidence_snapshot_summary=f"Based on {len(grounded_citations)} cited sources.",
        background_section=background_section,
        interventions_table=intervention_rows,
        recommendations=recommendation_items,
        top_citations=top_citations,
        follow_up_suggestions=[],
    )


def _parse_intervention_table(
    content: str, interventions: List
) -> List[InterventionTableRow]:
    """Parse intervention table from markdown content.

    Falls back to using aggregated interventions if parsing fails.

    Args:
        content: Markdown table content.
        interventions: Fallback intervention data.

    Returns:
        List of InterventionTableRow objects matching frontend schema.
    """
    rows: List[InterventionTableRow] = []

    # Try to parse markdown table
    lines = content.strip().split("\n")
    table_started = False

    for line in lines:
        if "|" not in line:
            continue

        # Skip header separator
        if set(line.replace("|", "").replace("-", "").replace(" ", "")) == set():
            table_started = True
            continue

        if not table_started:
            # Skip header row
            table_started = True
            continue

        # Parse data row
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 2:
            # Extract citation numbers from the row
            citation_nums = _extract_citation_numbers(line)

            rows.append(
                InterventionTableRow(
                    intervention_name=cells[0] if len(cells) > 0 else "",
                    citation_numbers=citation_nums,
                    context=cells[1] if len(cells) > 1 else "",
                    impact_narrative=cells[2] if len(cells) > 2 else "",
                    outcome_effects=[],  # Could be populated from intervention data
                )
            )

    # Fallback to aggregated interventions if no rows parsed
    if not rows and interventions:
        for intervention in interventions[:10]:
            rows.append(
                InterventionTableRow(
                    intervention_name=getattr(
                        intervention, "intervention_name", "Unknown"
                    ),
                    citation_numbers=[],
                    context=getattr(intervention, "brief_description", ""),
                    impact_narrative="",
                    outcome_effects=[],
                )
            )

    return rows


def _extract_citation_numbers(text: str) -> List[int]:
    """Extract [N] citation numbers from text.

    Args:
        text: Text containing citations.

    Returns:
        List of citation numbers like [1, 3, 5].
    """
    import re

    matches = re.findall(r"\[(\d+)\]", text)
    return [int(m) for m in matches]


def _parse_recommendations(content: str) -> List[RecommendationItem]:
    """Parse recommendations from numbered list content.

    Handles multiple formats:
    - **1. Title**: Description
    - 1. Title: Description
    - 1) Title: Description

    Args:
        content: Markdown numbered list content.

    Returns:
        List of RecommendationItem objects matching frontend schema.
    """
    import re

    recommendations: List[RecommendationItem] = []

    # Pattern matches: **1. or 1. or 1) at line start (with optional leading whitespace)
    rec_pattern = re.compile(r"^(?:\*\*)?(\d+)[.\)]\s*")

    lines = content.strip().split("\n")
    current_rec_lines: List[str] = []
    current_rec_number = 0

    for line in lines:
        stripped = line.strip()

        # Check if line starts a new numbered recommendation
        match = rec_pattern.match(stripped)
        if match:
            # Save previous recommendation
            if current_rec_lines:
                full_text = " ".join(current_rec_lines)
                title, description = _split_recommendation(full_text)
                citations = _extract_citation_numbers(full_text)
                recommendations.append(
                    RecommendationItem(
                        number=current_rec_number,
                        title=title,
                        description=description,
                        citation_numbers=citations,
                    )
                )

            # Start new recommendation - extract number and remaining text
            current_rec_number = int(match.group(1))
            # Remove the number prefix and any trailing ** from title
            remaining = stripped[match.end() :].lstrip("* ").rstrip("*")
            current_rec_lines = [remaining] if remaining else []
        elif stripped.startswith("-") and current_rec_lines:
            # Sub-item (Why, Strength, Implementation) - append to current
            current_rec_lines.append(stripped)
        elif current_rec_lines and stripped:
            # Continuation of current recommendation
            current_rec_lines.append(stripped)

    # Add last recommendation
    if current_rec_lines:
        full_text = " ".join(current_rec_lines)
        title, description = _split_recommendation(full_text)
        citations = _extract_citation_numbers(full_text)
        recommendations.append(
            RecommendationItem(
                number=current_rec_number,
                title=title,
                description=description,
                citation_numbers=citations,
            )
        )

    # Log if no recommendations found
    if not recommendations and content.strip():
        logger.warning(
            f"Failed to parse recommendations from content "
            f"({len(content)} chars, first 200: {content[:200]})"
        )

    return recommendations


def _split_recommendation(text: str) -> tuple:
    """Split recommendation text into title and description.

    Args:
        text: Full recommendation text.

    Returns:
        Tuple of (title, description).
    """
    # Look for a colon or period to split title from description
    if ":" in text[:60]:
        parts = text.split(":", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    elif ". " in text[:60]:
        parts = text.split(". ", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    else:
        # Use first few words as title
        words = text.split()
        title = " ".join(words[:6])
        description = " ".join(words[6:]) if len(words) > 6 else ""
        return title, description


# =============================================================================
# TOP CITATIONS SELECTION AND REASON GENERATION
# =============================================================================


class CitationReasonOutput(BaseModel):
    """Structured output for citation reason generation."""

    reason: str = Field(
        ...,
        description="A single sentence explaining why this source is important for the policy briefing",
        max_length=150,
    )


def _rank_citations(
    grounded_citations: List[CitationInfo],
    section_outputs: Dict[str, SectionOutput],
    doc_scores: Dict[str, Dict[str, Any]],
    all_scored_contexts: List[ScoredContext],
    doc_citation_map: Dict[str, int],
) -> List[Tuple[CitationInfo, float]]:
    """Rank citations by importance using multiple signals.

    Combines:
    - Usage frequency across briefing sections
    - Document quality scores (evidence strength, predicted impact)
    - Average relevance scores from RCS

    Args:
        grounded_citations: All available citations.
        section_outputs: Outputs from each briefing section.
        doc_scores: Document quality scores.
        all_scored_contexts: RCS-scored contexts.
        doc_citation_map: Document UUID to citation number mapping.

    Returns:
        List of (citation, score) tuples sorted by importance.
    """
    # Count usage across sections
    usage_counts: Counter = Counter()
    for output in section_outputs.values():
        for cit_num in output.citations_used:
            usage_counts[cit_num] += 1

    # Build reverse mapping: citation_number -> doc_uuid
    cit_to_doc = {v: k for k, v in doc_citation_map.items()}

    # Calculate relevance scores by document
    doc_relevance: Dict[str, List[float]] = {}
    for ctx in all_scored_contexts:
        if ctx.document_id not in doc_relevance:
            doc_relevance[ctx.document_id] = []
        doc_relevance[ctx.document_id].append(ctx.relevance_score)

    ranked: List[Tuple[CitationInfo, float]] = []

    for cit in grounded_citations:
        if not cit.citation_number:
            continue

        score = 0.0

        # Usage frequency (0-10 points)
        usage = usage_counts.get(cit.citation_number, 0)
        score += min(usage * 2, 10)

        # Document quality (0-10 points)
        doc_uuid = cit_to_doc.get(cit.citation_number)
        if doc_uuid and doc_uuid in doc_scores:
            quality = doc_scores[doc_uuid]
            evidence_score = quality.get("evidence_score", 0) or 0
            impact_score = quality.get("impact_score", 0) or 0
            score += evidence_score + impact_score  # Both are 0-5 scale

        # Average relevance from RCS (0-10 points)
        if doc_uuid and doc_uuid in doc_relevance:
            avg_relevance = sum(doc_relevance[doc_uuid]) / len(doc_relevance[doc_uuid])
            score += avg_relevance  # 0-10 scale

        ranked.append((cit, score))

    # Sort by score descending
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


async def _generate_citation_reasons_batch(
    citations: List[CitationInfo],
    research_question: str,
    section_outputs: Dict[str, SectionOutput],
) -> Dict[int, str]:
    """Generate LLM-powered reasons for why each citation is important.

    Args:
        citations: Citations to generate reasons for.
        research_question: The original research question.
        section_outputs: Generated briefing sections for context.

    Returns:
        Mapping of citation_number to generated reason.
    """
    if not citations:
        return {}

    # Build context summary from sections
    sections_summary = []
    for name, output in section_outputs.items():
        if output.content:
            # Truncate to avoid token limits
            preview = (
                output.content[:300] + "..."
                if len(output.content) > 300
                else output.content
            )
            sections_summary.append(f"**{name.title()}**: {preview}")

    briefing_context = (
        "\n".join(sections_summary)
        if sections_summary
        else "Policy intervention analysis."
    )

    llm = ChatOpenAI(
        model=GENERATION_MODEL,
        temperature=0.3,
        max_tokens=500,  # Needs to be higher for reasoning models
    )
    structured_llm = llm.with_structured_output(CitationReasonOutput)

    async def generate_single_reason(cit: CitationInfo) -> Tuple[int, str]:
        """Generate reason for a single citation."""
        prompt = f"""You are helping create an executive policy briefing. Generate a single sentence (max 20 words) explaining why this source is important for the briefing.

RESEARCH QUESTION: {research_question}

SOURCE:
- Title: {cit.title or 'Unknown'}
- Author: {cit.author_short or 'Unknown'}, {cit.year or 'n.d.'}
- Key quote: "{(cit.supporting_quote or '')[:200]}"

BRIEFING CONTEXT:
{briefing_context[:500]}

Write ONE sentence explaining what unique evidence or perspective this source contributes to answering the research question. Focus on the specific contribution, not generic descriptions."""

        try:
            result = await structured_llm.ainvoke(prompt)
            return (cit.citation_number, result.reason)
        except Exception as e:
            logger.warning(
                f"Failed to generate reason for citation {cit.citation_number}: {e}"
            )
            # Fallback to simple description
            return (cit.citation_number, _fallback_reason(cit))

    # Run in parallel with concurrency limit
    tasks = [generate_single_reason(cit) for cit in citations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    reasons: Dict[int, str] = {}
    for result in results:
        if isinstance(result, tuple):
            cit_num, reason = result
            reasons[cit_num] = reason
        # Skip exceptions - they'll use fallback when building citations

    return reasons


def _fallback_reason(citation: CitationInfo) -> str:
    """Generate a simple fallback reason when LLM fails.

    Args:
        citation: The citation info object.

    Returns:
        A basic reason based on document characteristics.
    """
    title = (citation.title or "").lower()

    if "systematic review" in title or "meta-analysis" in title:
        return "Synthesises evidence across multiple studies."
    elif "guideline" in title or "guidance" in title:
        return "Provides evidence-based recommendations."
    elif "who" in title or "world health" in title:
        return "WHO guidance on policy approaches."
    elif "review" in title:
        return "Reviews relevant research literature."
    else:
        return "Contributes to the evidence base."


async def _build_top_citations_async(
    grounded_citations: List[CitationInfo],
    section_outputs: Dict[str, SectionOutput],
    doc_scores: Dict[str, Dict[str, Any]],
    all_scored_contexts: List[ScoredContext],
    doc_citation_map: Dict[str, int],
    research_question: str,
    max_citations: int = 8,
) -> List[TopCitationItem]:
    """Build top citations with LLM-generated contextual reasons.

    Selects the most important citations based on usage, quality, and relevance,
    then generates meaningful reasons explaining each source's contribution.

    Args:
        grounded_citations: All available citations.
        section_outputs: Generated briefing sections.
        doc_scores: Document quality scores.
        all_scored_contexts: RCS-scored contexts.
        doc_citation_map: Document UUID to citation number mapping.
        research_question: The original research question.
        max_citations: Maximum citations to include.

    Returns:
        List of TopCitationItem with contextual reasons.
    """
    # Rank citations by importance
    ranked = _rank_citations(
        grounded_citations,
        section_outputs,
        doc_scores,
        all_scored_contexts,
        doc_citation_map,
    )

    # Select top citations
    top_citations_data = [cit for cit, _ in ranked[:max_citations]]

    # Generate reasons via LLM
    reasons = await _generate_citation_reasons_batch(
        top_citations_data,
        research_question,
        section_outputs,
    )

    # Build final citation items
    top_citations = []
    for cit in top_citations_data:
        reason = reasons.get(cit.citation_number, _fallback_reason(cit))

        top_citations.append(
            TopCitationItem(
                citation_number=cit.citation_number,
                title=cit.title or "Untitled",
                author_year=f"{cit.author_short or 'Unknown'}, {cit.year or 'n.d.'}",
                reason=reason,
                url=cit.url,
            )
        )

    return top_citations
