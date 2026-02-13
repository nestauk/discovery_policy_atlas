"""
Briefing generation node for the synthesis workflow.

Uses the tool-augmented approach with gpt-5.2 orchestration and
mandatory verification to generate grounded executive briefings.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from app.services.synthesis.state import SynthesisState, ScoredContext
from app.services.synthesis.schemas import (
    StructuredBriefing,
    BackgroundSection,
    CoreAnswer,
    SynthesisSectionProposal,
    CitationInfo,
    ClaimQuote,
    EvidenceSnapshotRow,
    TopCitationItem,
)
from app.services.synthesis.nodes.briefing_utils import (
    parse_intervention_table,
    parse_recommendations,
    parse_synthesis_sections,
    strip_leading_label,
    strip_inline_labels,
    clean_rec_title,
)
from app.services.synthesis.tools.orchestrator import (
    BriefingOrchestrator,
    SectionOutput,
)

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
Write 2-3 short paragraphs (120-180 words total) that:
1) Establish the policy context and why this matters
2) Summarise evidence scope and key themes
3) Set up the reader for interventions/recommendations
""",
        "additional": (
            "Use flowing prose. Include 3-5 inline citations in [N] format. "
            "No bullets or headings."
        ),
    },
    "interventions": {
        "name": "Policy Interventions Analysis",
        "instructions": """
Create a concise interventions table. Include 4-6 rows covering distinct intervention types.

IMPORTANT: Use the get_intervention_outcomes tool to retrieve aggregated outcome data 
(effect sizes, effect consensus, study types) for the interventions table.

ALSO IMPORTANT: Use the get_top_studies tool for each intervention type to identify 1-2 top studies
(ranked by evidence strength and predicted impact) and to extract a concrete implementation example
for the 'Key Study' column.

NOTE: get_top_studies also returns structured extracted outcomes/effect sizes for the key study
(from upstream result extractions), which you should use for the 'Key study outcomes' part of
the Impact & Outcomes cell.

For each row provide:
1. Intervention Type (3-6 words): Clear category name (e.g., "Combined Diet and Activity Programs")
2. Context/Features (15-25 words): Delivery method, setting, key components, notable features
   Example: "School-based with family involvement; integrates nutrition education and structured PA"
3. Key Study (25-40 words): A concrete implementation example drawn from the top-ranked study:
   what was done, where/setting (country/city where available; study setting may differ from publication location), duration/intensity, and key components. Include [N] citation(s).
4. Impact & Outcomes (30-50 words): Start with the key study findings (specific outcomes/effect sizes),
   then briefly describe the broader evidence base in this category (direction, consistency, caveats).
5. Sources: [N] citation references

Ensure each row covers a meaningfully different intervention approach.
""",
        "additional": (
            "Output a markdown table with header exactly: "
            "| Intervention | Context & Features | Key Study | Impact & Outcomes | Sources |\n"
            "Make Context rich with implementation details (delivery method, setting, components). "
            "Make Key Study a concrete implementation example from get_top_studies (ranked by evidence_score + impact_score). "
            "Make Impact & Outcomes specific with effect sizes/outcome measures from the key study, then a short synthesis of the broader category evidence. "
            "For readability inside the table cell, separate 'Key example outcomes' and 'Broader evidence' with a blank line (two newlines). "
            "Prefer 3-4 high-impact, well-evidenced interventions per dominant themes rather than broad lists."
        ),
    },
    "core_answer": {
        "name": "Core Findings",
        "instructions": """
Write a tight core answer (110-150 words) that:
1) Opens with a direct headline answer (1-2 sentences, cite)
2) Synthesises what works/does not work and key uncertainties (cite)
3) Ends with a 1-sentence directive in imperative voice (cite)
""",
        "additional": (
            "Every factual claim must have [N] citations. Keep sentences short. "
            "Do not restate the question. British English. "
            "Do NOT include meta-labels such as 'Core answer:', 'Synthesis:', or 'Directive:' "
            "anywhere in the output."
        ),
    },
    "recommendations": {
        "name": "Policy Recommendations",
        "instructions": """
Provide exactly 3-4 actionable recommendations. Each must have:
- Numbered title (3-7 words, action-led)
- One paragraph (60-90 words) with [N] citations
- At least one citation per recommendation
""",
        "additional": (
            "Return as numbered items; keep lines clean (no stray asterisks). "
            "Use [N] citation format only. "
            "Avoid evidence drift: distinguish clearly between (a) what the evidence supports (intervention components that work) "
            "and (b) implementation options (delivery channels, organisational models) where the evidence does not uniquely favour one. "
            "If you propose an implementation option beyond the evidence, label it explicitly as an option/assumption and keep it conditional."
        ),
    },
}


async def generate_briefing(state: SynthesisState) -> SynthesisState:
    """Generate executive briefing using tool-augmented approach.

    Uses the BriefingOrchestrator to:
    1. Gather evidence using tools (get_theme_evidence, search_extractions, etc.)
    2. Generate each section with gpt-5-mini
    3. Ground each section against source evidence (soft grounding with warnings)

    Args:
        state: Current synthesis state with RCS results.

    Returns:
        State update with structured_briefing and briefing_results.
    """
    print("--- Phase 6: Generating Executive Briefing ---")

    # Ensure doc_citation_map is populated early (critical for tool evidence)
    doc_citation_map = state.get("doc_citation_map") or {}
    if not doc_citation_map:
        grounded_citations = state.get("grounded_citations") or []
        for cit in grounded_citations:
            if cit.analysis_document_id and cit.citation_number:
                doc_citation_map[cit.analysis_document_id] = cit.citation_number
        state["doc_citation_map"] = doc_citation_map
        print(f"  Populated doc_citation_map with {len(doc_citation_map)} entries")

    # Get research question for context
    research_question = state.get("research_question", "")
    if not research_question:
        # Try to extract from project data
        research_question = _extract_research_question(state)

    # Initialise orchestrator
    orchestrator = BriefingOrchestrator(state)
    config = BriefingConfig()

    grounded_citations = state.get("grounded_citations") or []
    num_docs = len(grounded_citations)
    limits = {
        "max_interventions": min(8, max(4, num_docs // 4 or 4)),
        "max_recommendations": min(5, max(3, num_docs // 10 or 3)),
        "max_top_citations": min(10, max(6, (num_docs // 2) or 6)),
        "max_synthesis_sections": 2,
    }

    # Track results
    section_outputs: Dict[str, SectionOutput] = {}
    synthesis_outputs: List[Tuple[str, SectionOutput]] = []
    total_tool_calls = 0
    verification_failures: List[str] = []

    async def _run_section(section_key: str, additional_extra: str = "") -> None:
        nonlocal total_tool_calls
        section_config = SECTION_CONFIGS[section_key]
        print(f"  Generating section: {section_config['name']}...")

        instructions = section_config["instructions"]
        if research_question:
            instructions = f"Research Question: {research_question}\n\n{instructions}"

        # Inject user intent (population/outcomes) to tailor generation without displaying it explicitly.
        target_population = state.get("target_population") or []
        target_outcomes = state.get("target_outcomes") or []
        pop_str = (
            ", ".join([p for p in target_population if p]) if target_population else ""
        )
        out_str = (
            ", ".join([o for o in target_outcomes if o]) if target_outcomes else ""
        )
        if pop_str or out_str:
            intent_lines = []
            if pop_str:
                intent_lines.append(f"Target population: {pop_str}")
            if out_str:
                intent_lines.append(f"Target outcomes: {out_str}")
            intent_lines.append(
                "Use these to prioritise and frame evidence (but do not add a separate section or explicitly display this metadata in the output)."
            )
            instructions = "\n".join(intent_lines) + "\n\n" + instructions

        additional = section_config.get("additional", "") + additional_extra

        try:
            output = await orchestrator.generate_section(
                section_name=section_config["name"],
                section_instructions=instructions,
                additional_instructions=additional,
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
            section_outputs[section_key] = SectionOutput(
                content=f"[Section generation failed: {e}]",
                citations_used=[],
                verification_passed=False,
                verification_issues=[str(e)],
                tool_calls_made=0,
            )

    # Background
    await _run_section("background")

    # Interventions with dynamic limits and tool guidance
    inter_extra = (
        f"Aim for {limits['max_interventions']} rows, prioritising high-impact, well-evidenced interventions. "
        "Use get_intervention_outcomes for effect sizes; get_top_studies for concrete key-study implementation examples; "
        "and get_intervention_details for delivery features and subgroups."
    )
    await _run_section("interventions", additional_extra=f" {inter_extra}")

    # Decide and generate synthesis sections (always propose up to 2)
    proposals = await _decide_synthesis_sections(
        orchestrator=orchestrator,
        research_question=research_question,
        max_sections=limits["max_synthesis_sections"],
        num_sources=num_docs,
    )
    for idx, proposal in enumerate(proposals[: limits["max_synthesis_sections"]]):
        synth_output = await _generate_synthesis_section(
            orchestrator=orchestrator,
            proposal=proposal,
            research_question=research_question,
            section_index=idx + 1,
            max_retries=config.max_verification_retries,
        )
        synthesis_outputs.append((proposal.section_title, synth_output))
        section_outputs[f"synthesis_{idx+1}"] = synth_output
        total_tool_calls += synth_output.tool_calls_made
        if not synth_output.verification_passed:
            verification_failures.append(f"synthesis_{idx+1}")

    # Core Findings
    await _run_section("core_answer")

    # Recommendations with adaptive count
    rec_extra = (
        f"Provide {limits['max_recommendations']} concise recommendations unless evidence is sparse. "
        "Each must include [N] citations."
    )
    await _run_section("recommendations", additional_extra=f" {rec_extra}")

    # Build structured briefing from sections
    structured_briefing = await _build_structured_briefing(
        section_outputs,
        grounded_citations,
        state.get("aggregated_interventions") or [],
        research_question,
        state.get("doc_scores") or {},
        state.get("all_scored_contexts") or [],
        state.get("doc_citation_map") or {},
        state.get("doc_metadata") or {},
        synthesis_outputs,
        limits,
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

    # Merge per-claim quotes from section outputs into citation map
    for section_key, output in section_outputs.items():
        for quote in output.claim_quotes:
            citation_key = f"[{quote.citation_number}]"
            citation = citation_map.get(citation_key)
            if not citation:
                continue
            citation.claim_quotes.append(
                ClaimQuote(
                    claim_text=quote.claim_text,
                    supporting_quote=quote.supporting_quote,
                    attribution=quote.attribution,
                    chunk_id=quote.chunk_id,
                    section=section_key,
                )
            )

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
    doc_metadata: Dict[str, Dict[str, Any]],
    synthesis_outputs: List[Tuple[str, SectionOutput]],
    limits: Dict[str, int],
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

    # Fallback mapping if none provided
    if not doc_citation_map:
        for cit in grounded_citations:
            if cit.analysis_document_id and cit.citation_number:
                doc_citation_map[cit.analysis_document_id] = cit.citation_number

    # Parse core answer - split directive if present
    core_output = section_outputs.get(
        "core_answer", SectionOutput(content="", citations_used=[])
    )

    full_content = core_output.content.strip()
    directive = ""
    answer_text = full_content

    if full_content:
        sentences = re.split(r"(?<=[.!?])\s+", full_content)
        if len(sentences) > 1:
            directive = sentences[-1].strip()
            answer_text = " ".join(sentences[:-1]).strip() or full_content

    # Strip meta-labels if the model included them anyway
    answer_text = strip_leading_label(answer_text, ["Core answer:", "Core answer"])
    answer_text = strip_inline_labels(answer_text, ["Synthesis:", "Synthesis"])
    directive = strip_leading_label(directive, ["Directive:", "Directive"])

    core_answer = CoreAnswer(
        query=research_question or "Policy intervention analysis",
        answer=answer_text,
        directive=directive,
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

    # Parse interventions table - filter nulls and limit to top N
    int_output = section_outputs.get(
        "interventions", SectionOutput(content="", citations_used=[])
    )
    all_intervention_rows = parse_intervention_table(int_output.content, interventions)

    # Filter out null/empty rows and limit to top N by citation count
    intervention_rows = [
        row
        for row in all_intervention_rows
        if row.intervention_name
        and row.intervention_name.strip() not in ("", "---", "-")
    ]
    # Sort by number of citations (most evidence first), then limit
    max_interventions = limits.get("max_interventions", 6)
    intervention_rows = sorted(
        intervention_rows, key=lambda r: len(r.citation_numbers), reverse=True
    )[:max_interventions]

    # Parse recommendations
    rec_output = section_outputs.get(
        "recommendations", SectionOutput(content="", citations_used=[])
    )
    recommendation_items = parse_recommendations(rec_output.content)
    max_recs = limits.get("max_recommendations", len(recommendation_items))
    recommendation_items = recommendation_items[:max_recs]
    for rec in recommendation_items:
        rec.title = clean_rec_title(rec.title)

    # Parse synthesis sections (if any)
    synthesis_sections = parse_synthesis_sections(synthesis_outputs)

    # Build top citations (use precomputed document top_line, no LLM reason generation)
    top_citations = await _build_top_citations_async(
        grounded_citations,
        section_outputs,
        doc_scores,
        all_scored_contexts,
        doc_citation_map,
        doc_metadata,
        max_citations=limits.get("max_top_citations", 8),
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
        synthesis_sections=synthesis_sections,
        recommendations=recommendation_items,
        top_citations=top_citations,
        follow_up_suggestions=[],
    )


class SynthesisSectionDecision(BaseModel):
    """Container for structured section proposals."""

    sections: List[SynthesisSectionProposal] = Field(default_factory=list, max_length=2)


async def _decide_synthesis_sections(
    orchestrator: BriefingOrchestrator,
    research_question: str,
    max_sections: int,
    num_sources: int,
) -> List[SynthesisSectionProposal]:
    """Use the orchestrator LLM to propose synthesis sections."""
    prompt = f"""You are designing synthesis sections for an executive policy briefing.

Research question: {research_question or 'Not provided'}
Evidence base: {num_sources} cited sources

Always propose 1-2 sections to include between the interventions table and recommendations.
Choose from the menu when relevant, or propose a custom title if it better fits the evidence:
- Key Success Factors (moderators, delivery components that drive effect)
- Limitations & Research Gaps (uncertainties, heterogeneity, missing data)
- Implementation Challenges (barriers/facilitators, feasibility)
- Cost-Effectiveness Evidence (economic results if present)
- Stakeholder Perspectives (where evidence includes adoption/acceptability signals)

For each section, provide:
- section_title
- rationale (why this section is needed for this briefing)
- focus (what specific content it will cover)

Avoid generic text; tailor to the evidence themes. Do not reference Consensus."""

    decision_llm = orchestrator.orchestrator_llm.with_structured_output(
        SynthesisSectionDecision,
        method="function_calling",
    )

    try:
        decision = await decision_llm.ainvoke(prompt)
        proposals = decision.sections or []
    except Exception as e:
        logger.warning(f"Synthesis section proposal generation failed: {e}")
        proposals = []

    if not proposals:
        proposals = [
            SynthesisSectionProposal(
                section_title="Limitations and Research Gaps",
                rationale="Evidence shows heterogeneity and limited long-term data; decision-makers need to understand uncertainties.",
                focus="Summarise main gaps, sources of heterogeneity, and priority research needs.",
            )
        ]

    return proposals[:max_sections]


async def _generate_synthesis_section(
    orchestrator: BriefingOrchestrator,
    proposal: SynthesisSectionProposal,
    research_question: str,
    section_index: int,
    max_retries: int,
) -> SectionOutput:
    """Generate a single synthesis section via the orchestrator."""
    instructions = f"""Write a synthesis section titled "{proposal.section_title}" that supports the policy briefing.

Focus: {proposal.focus}
Rationale: {proposal.rationale}

Guidance:
- Do NOT repeat the section title in the content.
- Prefer a concise bullet list with 4-6 bullets; if you use bullets, start lines with '- ' only.
- Use either 2-4 short paragraphs or a 4-6 bullet list (choose the better fit for clarity).
- Aim for 120-180 words total.
- Every factual claim must include [N] citations.
- British English. No headings or extraneous labels.
- If evidence is thin, be explicit about uncertainties rather than inventing detail."""

    additional = (
        "Prioritise precise effect sizes, subgroup/moderator notes, and concrete implementation signals where available. "
        "Do not restate the research question. Do not add an inline heading or repeat the section title."
    )

    return await orchestrator.generate_section(
        section_name=f"Synthesis {section_index}: {proposal.section_title}",
        section_instructions=instructions,
        additional_instructions=additional,
        max_retries=max_retries,
    )


# =============================================================================
# TOP CITATIONS SELECTION (uses analysis_documents.top_line; no LLM reason generation)
# =============================================================================


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


async def _build_top_citations_async(
    grounded_citations: List[CitationInfo],
    section_outputs: Dict[str, SectionOutput],
    doc_scores: Dict[str, Dict[str, Any]],
    all_scored_contexts: List[ScoredContext],
    doc_citation_map: Dict[str, int],
    doc_metadata: Dict[str, Dict[str, Any]],
    max_citations: int = 8,
) -> List[TopCitationItem]:
    """Build top citations using precomputed document 'top_line' (no LLM reason generation).

    Selects the most important citations based on usage, quality, and relevance,
    then generates meaningful reasons explaining each source's contribution.

    Args:
        grounded_citations: All available citations.
        section_outputs: Generated briefing sections.
        doc_scores: Document quality scores.
        all_scored_contexts: RCS-scored contexts.
        doc_citation_map: Document UUID to citation number mapping.
        doc_metadata: Document metadata keyed by doc_uuid (should include 'top_line').
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

    # Build reverse mapping: citation_number -> doc_uuid
    cit_to_doc = {v: k for k, v in doc_citation_map.items()}

    # Select top citations
    top_citations_data = [cit for cit, _ in ranked[:max_citations]]

    # Build final citation items
    top_citations = []
    for cit in top_citations_data:
        doc_uuid = cit_to_doc.get(cit.citation_number) if cit.citation_number else None
        reason = ""
        if doc_uuid:
            reason = (doc_metadata.get(doc_uuid, {}) or {}).get("top_line") or ""
        reason = reason.strip()

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
