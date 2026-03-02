"""
Briefing generation node for the synthesis workflow.

Uses the tool-augmented approach with gpt-5.2 orchestration and
mandatory verification to generate grounded executive briefings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

from app.services.synthesis.state import SynthesisState
from app.services.synthesis.schemas import (
    StructuredBriefing,
    BackgroundSection,
    CoreAnswer,
    SynthesisSectionProposal,
    CitationInfo,
    ClaimQuote,
    EvidenceSnapshotRow,
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
        "max_synthesis_sections": 2,
    }

    # Track results
    section_outputs: Dict[str, SectionOutput] = {}
    synthesis_outputs: List[Tuple[str, SectionOutput]] = []
    total_tool_calls = 0
    verification_failures: List[str] = []
    running_section_context: List[str] = []

    def _current_prior_sections_summary() -> str:
        # Keep prompt size bounded while preserving recent narrative flow.
        return "\n".join(running_section_context[-6:])

    def _summarise_section_for_context(
        section_title: str,
        output: SectionOutput,
    ) -> str:
        content = re.sub(r"(?m)^\\s*\\|.*\\|\\s*$", " ", output.content or "")
        content = re.sub(r"<br\\s*/?>", " ", content)
        content = re.sub(r"\\s+", " ", content).strip()
        words = content.split()
        if len(words) > 150:
            content = " ".join(words[:150]).rstrip() + "..."
        citations = sorted(set(output.citations_used))
        citations_text = (
            ", ".join(f"[{c}]" for c in citations[:8]) if citations else "none"
        )
        return f"- {section_title}: {content} (citations: {citations_text})"

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
                prior_sections_summary=_current_prior_sections_summary(),
            )

            section_outputs[section_key] = output
            total_tool_calls += output.tool_calls_made
            running_section_context.append(
                _summarise_section_for_context(section_config["name"], output)
            )

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
            prior_sections_summary=_current_prior_sections_summary(),
        )
        synthesis_outputs.append((proposal.section_title, synth_output))
        section_outputs[f"synthesis_{idx+1}"] = synth_output
        total_tool_calls += synth_output.tool_calls_made
        running_section_context.append(
            _summarise_section_for_context(
                f"Synthesis {idx + 1}: {proposal.section_title}",
                synth_output,
            )
        )
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

    # Enforce strict citation token style so downstream quote/detail features can
    # always resolve citations reliably.
    for output in section_outputs.values():
        output.content = _normalise_compound_citation_brackets(output.content or "")
        for claim in output.claim_quotes:
            claim.claim_text = _normalise_compound_citation_brackets(
                claim.claim_text or ""
            )

    # Pre-sort interventions table rows to match frontend display order *before*
    # renumbering so the scan order equals the rendered order.
    int_out = section_outputs.get("interventions")
    if int_out and int_out.content:
        int_out.content = _sort_interventions_table_markdown(int_out.content)

    # Renumber citations by order of first appearance in final briefing content.
    _renumber_citations_by_appearance(
        section_outputs=section_outputs,
        synthesis_outputs=synthesis_outputs,
        state=state,
    )

    # Build structured briefing from sections
    structured_briefing = await _build_structured_briefing(
        section_outputs,
        grounded_citations,
        state.get("aggregated_interventions") or [],
        research_question,
        state.get("doc_citation_map") or {},
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


def _sort_interventions_table_markdown(content: str) -> str:
    """Sort markdown table data rows by citation count (most first).

    Matches the display-order sort applied later in _build_structured_briefing
    so that _renumber_citations_by_appearance scans rows in the same order
    the frontend renders them.
    """
    if not content or "|" not in content:
        return content

    lines = content.strip().split("\n")
    header_lines: List[str] = []
    data_lines: List[str] = []
    past_separator = False

    for line in lines:
        stripped = line.strip()
        if not past_separator:
            header_lines.append(line)
            if (
                set(stripped.replace("|", "").replace("-", "").replace(" ", ""))
                == set()
            ):
                past_separator = True
        else:
            data_lines.append(line)

    if len(data_lines) <= 1:
        return content

    data_lines.sort(
        key=lambda row: len(re.findall(r"\[\d+\]", row)),
        reverse=True,
    )
    return "\n".join(header_lines + data_lines)


def _normalise_compound_citation_brackets(text: str) -> str:
    """Rewrite bracketed citation lists into strict `[N] [N]` format.

    Args:
        text: Free text that may contain bracketed citation lists such as
            ``[1, 3, 12]``.

    Returns:
        Text with citation lists expanded to individual bracketed citations.
    """
    if not text:
        return text

    def _expand(match: re.Match[str]) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if not numbers:
            return match.group(0)
        seen = set()
        ordered = []
        for num in numbers:
            if num <= 0 or num in seen:
                continue
            seen.add(num)
            ordered.append(num)
        return " ".join(f"[{num}]" for num in ordered) if ordered else match.group(0)

    return re.sub(r"\[([0-9][0-9,\s;]*)\]", _expand, text)


def _apply_citation_mapping(text: str, mapping: Dict[int, int]) -> str:
    """Replace [old] citation tokens with [new] tokens safely."""
    if not text or not mapping:
        return text
    text = _normalise_compound_citation_brackets(text)
    placeholder_prefix = "__CIT_PLACEHOLDER_"
    updated = text
    for old_num in mapping:
        updated = updated.replace(f"[{old_num}]", f"[{placeholder_prefix}{old_num}__]")
    for old_num, new_num in mapping.items():
        updated = updated.replace(
            f"[{placeholder_prefix}{old_num}__]",
            f"[{new_num}]",
        )
    return updated


def _normalise_inline_citation_groups(text: str) -> str:
    """Sort adjacent inline citation groups numerically (e.g., [3] [1] -> [1] [3])."""
    if not text:
        return text
    text = _normalise_compound_citation_brackets(text)

    def _sort_group(match: re.Match[str]) -> str:
        citations = [int(num) for num in re.findall(r"\[(\d+)\]", match.group(0))]
        ordered = sorted(set(citations))
        return " ".join(f"[{num}]" for num in ordered)

    return re.sub(r"(?:\[\d+\]\s*){2,}", _sort_group, text)


def _renumber_citations_by_appearance(
    section_outputs: Dict[str, SectionOutput],
    synthesis_outputs: List[Tuple[str, SectionOutput]],
    state: SynthesisState,
) -> Dict[int, int]:
    """Renumber citations sequentially by first appearance order in briefing output."""
    # Must match frontend display order in ExecutiveBriefing.tsx.
    ordered_section_keys: List[str] = ["core_answer", "background", "interventions"]
    ordered_section_keys.extend(
        [f"synthesis_{i+1}" for i in range(len(synthesis_outputs))]
    )
    ordered_section_keys.extend(["recommendations"])

    seen_in_order: List[int] = []
    seen_set = set()
    for key in ordered_section_keys:
        output = section_outputs.get(key)
        if not output or not output.content:
            continue
        normalised_content = _normalise_compound_citation_brackets(output.content)
        for match in re.findall(r"\[(\d+)\]", normalised_content):
            num = int(match)
            if num not in seen_set:
                seen_set.add(num)
                seen_in_order.append(num)

    grounded_citations = state.get("grounded_citations") or []
    for citation in grounded_citations:
        num = getattr(citation, "citation_number", 0) or 0
        if num > 0 and num not in seen_set:
            seen_set.add(num)
            seen_in_order.append(num)

    mapping = {old_num: idx for idx, old_num in enumerate(seen_in_order, start=1)}
    if not mapping:
        return {}

    for output in section_outputs.values():
        output.content = _normalise_inline_citation_groups(
            _apply_citation_mapping(output.content or "", mapping)
        )
        output.citations_used = sorted(
            {
                mapping.get(int(c), int(c))
                for c in (output.citations_used or [])
                if int(c) > 0
            }
        )
        for claim in output.claim_quotes:
            claim.citation_number = mapping.get(
                int(claim.citation_number), int(claim.citation_number)
            )
            claim.claim_text = _normalise_inline_citation_groups(
                _apply_citation_mapping(claim.claim_text or "", mapping)
            )

    new_doc_citation_map: Dict[str, int] = {}
    for doc_id, old_num in (state.get("doc_citation_map") or {}).items():
        old_int = int(old_num) if old_num else 0
        if old_int <= 0:
            continue
        new_doc_citation_map[doc_id] = mapping.get(old_int, old_int)
    state["doc_citation_map"] = new_doc_citation_map

    for citation in grounded_citations:
        old_num = int(getattr(citation, "citation_number", 0) or 0)
        if old_num <= 0:
            continue
        new_num = mapping.get(old_num, old_num)
        citation.citation_number = new_num
        citation.citation_key = f"[{new_num}]"
        for cq in citation.claim_quotes:
            cq.claim_text = _normalise_inline_citation_groups(
                _apply_citation_mapping(cq.claim_text or "", mapping)
            )

    return mapping


async def _build_structured_briefing(
    section_outputs: Dict[str, SectionOutput],
    grounded_citations: List[CitationInfo],
    interventions: List,
    research_question: str,
    doc_citation_map: Dict[str, int],
    synthesis_outputs: List[Tuple[str, SectionOutput]],
    limits: Dict[str, int],
) -> StructuredBriefing:
    """Build StructuredBriefing from section outputs.

    Args:
        section_outputs: Generated sections.
        grounded_citations: Available citations.
        interventions: Aggregated interventions for table.
        research_question: The original research question.
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
    prior_sections_summary: str = "",
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
        prior_sections_summary=prior_sections_summary,
    )
