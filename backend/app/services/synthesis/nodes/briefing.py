"""
Briefing generation nodes for the synthesis workflow.

Phase 5: Generate structured executive briefing with RAG-grounded citations.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Dict, List, Optional

from app.utils.llm.llm_utils import get_llm
from app.services.synthesis.state import SynthesisState
from app.services.synthesis.utils import (
    MAPPING_MODEL,
    BRIEFING_MODEL,
    escape_braces,
    build_langfuse_config,
    normalize_study_type,
)
from app.services.synthesis.schemas import (
    CitationInfo,
    EvidenceCoverageSnapshot,
    EvidenceSnapshotRow,
    BackgroundSection,
    InterventionTableRow,
    OutcomeEffect,
    CoreAnswer,
    RecommendationItem,
    RecommendationsOutput,
    TopCitationItem,
    StructuredBriefing,
    KeyIssue,
    PolicyIntervention,
    OutcomeTheme,
    RetrievedChunk,
)
from app.services.synthesis.prompts import (
    build_background_section_prompt,
    build_impact_narrative_prompt,
    build_recommendations_prompt,
    build_core_answer_prompt,
)

logger = logging.getLogger(__name__)


async def synthesize_executive_briefing(state: SynthesisState) -> SynthesisState:
    """Generate structured executive briefing with RAG-grounded citations.

    Args:
        state: Current workflow state with all aggregated data.

    Returns:
        State update with structured_briefing and citation_map.
    """
    print("--- Synthesizing Executive Briefing ---")
    rq = state.get("research_question") or "Not specified"
    issues = state.get("aggregated_issues") or []
    interventions = state.get("aggregated_interventions") or []
    evidence_coverage = state.get("evidence_coverage")
    theme_evidence = state.get("theme_evidence") or {}
    issue_evidence = state.get("issue_evidence") or {}
    grounded_citations = state.get("grounded_citations") or []
    chunk_to_citation = state.get("chunk_to_citation") or {}

    # 1. Evidence Snapshot (deterministic)
    evidence_snapshot = _build_evidence_snapshot(evidence_coverage)

    # 2. Background Section
    background = await _generate_background(
        state, issues, issue_evidence, chunk_to_citation
    )

    # 3. Interventions Table
    interventions_table = await _generate_interventions_table(
        state, interventions, theme_evidence, chunk_to_citation
    )

    # 4. Core Answer
    core_answer = await _generate_core_answer(state, rq, interventions, background)

    # 5. Recommendations
    recommendations = await _generate_recommendations(
        state, rq, interventions, theme_evidence, chunk_to_citation
    )

    # 6. Top Citations
    top_citations = _build_top_citations(grounded_citations, interventions_table)

    # 7. Follow-up Suggestions
    follow_ups = []
    if evidence_coverage and evidence_coverage.gaps:
        if any("RCT" in g for g in evidence_coverage.gaps):
            follow_ups.append("Search for randomised controlled trials on this topic")
        if any("systematic" in g.lower() for g in evidence_coverage.gaps):
            follow_ups.append("Look for systematic reviews or meta-analyses")
    if not follow_ups:
        follow_ups = ["Consider searching for implementation case studies"]

    structured_briefing = StructuredBriefing(
        core_answer=core_answer,
        evidence_snapshot=evidence_snapshot,
        evidence_snapshot_summary=" ".join(evidence_coverage.gaps)
        if evidence_coverage
        else "",
        background_section=background,
        interventions_table=interventions_table,
        recommendations=recommendations,
        top_citations=top_citations,
        follow_up_suggestions=follow_ups[:3],
    )

    citation_map = {c.citation_key: c for c in grounded_citations}

    return {
        "executive_briefing": "",  # Legacy field, no longer generated
        "structured_briefing": structured_briefing,
        "citation_map": citation_map,
    }


def _build_evidence_snapshot(
    coverage: Optional[EvidenceCoverageSnapshot],
) -> List[EvidenceSnapshotRow]:
    """Build evidence snapshot rows from coverage statistics.

    Args:
        coverage: Evidence coverage statistics.

    Returns:
        List of snapshot rows for display.
    """
    if not coverage:
        return [
            EvidenceSnapshotRow(
                metric="Status", detail="Evidence coverage not computed."
            )
        ]

    rows = [
        EvidenceSnapshotRow(
            metric="Total Studies", detail=f"{coverage.total_sources} documents"
        )
    ]

    if coverage.study_types:
        parts = [
            f"**{st}** ({c})"
            for st, c in sorted(coverage.study_types.items(), key=lambda x: -x[1])[:5]
        ]
        rows.append(EvidenceSnapshotRow(metric="Study Types", detail=", ".join(parts)))

    if coverage.countries:
        parts = [
            f"**{c}** ({n})"
            for c, n in sorted(coverage.countries.items(), key=lambda x: -x[1])[:5]
        ]
        rows.append(
            EvidenceSnapshotRow(metric="Geographic Scope", detail=", ".join(parts))
        )

    rows.append(
        EvidenceSnapshotRow(
            metric="Overall Strength", detail=f"**{coverage.overall_strength}**"
        )
    )
    return rows


async def _generate_background(
    state: SynthesisState,
    issues: List[KeyIssue],
    issue_evidence: Dict[str, List[RetrievedChunk]],
    chunk_to_citation: Dict[str, int],
) -> Optional[BackgroundSection]:
    """Generate background section using RAG evidence.

    Args:
        state: Current workflow state.
        issues: Aggregated issues.
        issue_evidence: RAG evidence for issues.
        chunk_to_citation: Mapping of chunk IDs to citation numbers.

    Returns:
        Background section or None.
    """
    if not issues:
        return None

    all_chunks = []
    for issue in issues[:5]:
        all_chunks.extend(issue_evidence.get(issue.issue_theme, [])[:4])

    if not all_chunks:
        return BackgroundSection(
            title="Policy Background",
            paragraphs=["Background context not available."],
            citation_numbers_used=[],
        )

    evidence_lines = []
    for chunk in all_chunks[:12]:
        cit_num = chunk_to_citation.get(chunk.chunk_id, 0)
        evidence_lines.append(
            f"[{cit_num}] {chunk.author_short or 'Unknown'}, {chunk.year or 'n.d.'}: "
            f'"{chunk.content[:200]}..."'
        )

    issues_summary = "\n".join(
        [f"- {i.issue_theme}: {i.summary_description}" for i in issues[:5]]
    )

    try:
        prompt = build_background_section_prompt()
        llm = get_llm(BRIEFING_MODEL, temperature=0)
        tags = [
            "component:synthesis",
            "component:synthesis.background",
            f"model:{BRIEFING_MODEL}",
        ]

        resp = await llm.ainvoke(
            prompt.format(
                research_question=state.get("research_question", ""),
                issues_summary=escape_braces(issues_summary),
                evidence_context=escape_braces("\n\n".join(evidence_lines)),
            ),
            config={
                **build_langfuse_config(state, tags),
                "run_name": "synthesis.background",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        cit_nums = set(int(m) for m in re.findall(r"\[(\d+)\]", text))

        return BackgroundSection(
            title="Policy Background & Context",
            paragraphs=paragraphs,
            citation_numbers_used=sorted(cit_nums),
        )

    except Exception as e:
        logger.warning(f"Background generation failed: {e}")
        return BackgroundSection(
            title="Policy Background",
            paragraphs=[
                f"Key issues: {', '.join([i.issue_theme for i in issues[:5]])}"
            ],
            citation_numbers_used=[],
        )


async def _generate_interventions_table(
    state: SynthesisState,
    interventions: List[PolicyIntervention],
    theme_evidence: Dict[str, List[RetrievedChunk]],
    chunk_to_citation: Dict[str, int],
) -> List[InterventionTableRow]:
    """Generate interventions table rows with impact narratives.

    Args:
        state: Current workflow state.
        interventions: Aggregated interventions.
        theme_evidence: RAG evidence for interventions.
        chunk_to_citation: Mapping of chunk IDs to citation numbers.

    Returns:
        List of intervention table rows.
    """
    rows: List[InterventionTableRow] = []
    null_values = {"null", "none", "", "unknown", "n/a"}

    aggregated_outcomes: List[OutcomeTheme] = state.get("aggregated_outcomes") or []

    # Order by evidence strength (frequency)
    sorted_interventions = sorted(
        interventions,
        key=lambda i: i.frequency if hasattr(i, "frequency") else 0,
        reverse=True,
    )

    rows_added = 0
    for intervention in sorted_interventions:
        if rows_added >= 5:
            break

        # Require at least 3 supporting documents
        if len(intervention.supporting_doc_ids or []) < 3:
            continue
        chunks = theme_evidence.get(intervention.intervention_name, [])
        if not chunks:
            continue

        cit_nums = [
            chunk_to_citation.get(c.chunk_id, 0)
            for c in chunks
            if c.chunk_id in chunk_to_citation
        ][:8]

        if not cit_nums:
            continue
        intervention_doc_ids = set(intervention.supporting_doc_ids)

        # Build structured context
        context_parts = []

        valid_countries = [
            c for c in intervention.countries if c.lower() not in null_values
        ]
        if valid_countries:
            context_parts.append(f"**Location**: {', '.join(valid_countries[:4])}")

        # Extract setting from description
        desc = intervention.brief_description.lower()
        if "school" in desc:
            context_parts.append("**Setting**: School-based")
        elif "community" in desc:
            context_parts.append("**Setting**: Community-based")
        elif "clinic" in desc or "hospital" in desc or "health" in desc:
            context_parts.append("**Setting**: Clinical/health facility")
        elif "workplace" in desc or "employer" in desc:
            context_parts.append("**Setting**: Workplace")

        valid_studies = [
            s for s in intervention.study_types.keys() if s.lower() not in null_values
        ]
        if valid_studies:
            study_counts = [
                f"{normalize_study_type(s)} ({intervention.study_types[s]})"
                for s in valid_studies[:3]
            ]
            context_parts.append(f"**Studies**: {', '.join(study_counts)}")

        context = " ".join(context_parts) if context_parts else "Various settings"

        # Generate impact narrative
        impact_narrative = await _generate_impact_narrative(
            state, intervention, chunks, chunk_to_citation
        )

        # Match intervention to outcome themes
        outcome_doc_effects: Dict[str, Dict[str, List[str]]] = (
            state.get("outcome_doc_effects") or {}
        )

        outcome_effects: List[OutcomeEffect] = []
        for outcome in aggregated_outcomes:
            theme_doc_ids = set(outcome.source_doc_ids)
            overlap = intervention_doc_ids & theme_doc_ids

            if overlap:
                doc_effects = outcome_doc_effects.get(outcome.outcome_name, {})
                pos, neg, nul = 0, 0, 0
                for doc_id in overlap:
                    for effect in doc_effects.get(doc_id, []):
                        if effect == "positive":
                            pos += 1
                        elif effect == "negative":
                            neg += 1
                        elif effect == "null":
                            nul += 1

                total = pos + neg + nul
                if total == 0:
                    continue

                if pos > neg * 2 and pos > nul:
                    direction = "increase"
                elif neg > pos * 2 and neg > nul:
                    direction = "decrease"
                elif nul > pos and nul > neg:
                    direction = "no change"
                else:
                    direction = "mixed"

                outcome_effects.append(
                    OutcomeEffect(
                        outcome_theme=outcome.outcome_name,
                        direction=direction,
                        positive_count=pos,
                        negative_count=neg,
                        null_count=nul,
                    )
                )

        outcome_effects.sort(
            key=lambda x: -(x.positive_count + x.negative_count + x.null_count)
        )

        rows.append(
            InterventionTableRow(
                intervention_name=intervention.intervention_name,
                citation_numbers=[n for n in cit_nums if n > 0],
                context=context,
                impact_narrative=impact_narrative,
                outcome_effects=outcome_effects[:5],
            )
        )
        rows_added += 1

    return rows


async def _generate_impact_narrative(
    state: SynthesisState,
    intervention: PolicyIntervention,
    chunks: List[RetrievedChunk],
    chunk_to_citation: Dict[str, int],
) -> str:
    """Generate a concise impact narrative for an intervention.

    Args:
        state: Current workflow state.
        intervention: The intervention to describe.
        chunks: RAG evidence chunks.
        chunk_to_citation: Mapping of chunk IDs to citation numbers.

    Returns:
        Impact narrative string.
    """
    if not chunks:
        return intervention.impact_summary or "Impact data not available."

    evidence_lines = []
    for chunk in chunks[:5]:
        cit_num = chunk_to_citation.get(chunk.chunk_id, 0)
        if cit_num > 0:
            evidence_lines.append(f'[{cit_num}] "{chunk.content[:250]}..."')

    if not evidence_lines:
        return intervention.impact_summary or "Impact data not available."

    try:
        prompt = build_impact_narrative_prompt()
        llm = get_llm(MAPPING_MODEL, temperature=0)
        tags = [
            "component:synthesis",
            "component:synthesis.impact_narrative",
            f"model:{MAPPING_MODEL}",
        ]

        resp = await llm.ainvoke(
            prompt.format(
                intervention_name=intervention.intervention_name,
                effect_consensus=intervention.effect_consensus or "mixed",
                evidence_context=escape_braces("\n".join(evidence_lines)),
            ),
            config={
                **build_langfuse_config(state, tags),
                "run_name": "synthesis.impact_narrative",
            },
        )
        return (resp.content if hasattr(resp, "content") else str(resp)).strip()

    except Exception as e:
        logger.warning(f"Impact narrative generation failed: {e}")
        return intervention.impact_summary or "Impact data not available."


async def _generate_core_answer(
    state: SynthesisState,
    rq: str,
    interventions: List[PolicyIntervention],
    background: Optional[BackgroundSection],
) -> CoreAnswer:
    """Generate core answer section.

    Args:
        state: Current workflow state.
        rq: Research question.
        interventions: Aggregated interventions.
        background: Background section.

    Returns:
        Core answer object.
    """
    top_intrs = ", ".join([i.intervention_name for i in interventions[:5]])

    try:
        prompt = build_core_answer_prompt()
        llm = get_llm(BRIEFING_MODEL, temperature=0)
        tags = [
            "component:synthesis",
            "component:synthesis.core_answer",
            f"model:{BRIEFING_MODEL}",
        ]

        resp = await llm.ainvoke(
            prompt.format(
                research_question=rq,
                top_interventions=escape_braces(top_intrs),
                intervention_count=len(interventions),
                background_context=escape_braces(
                    background.paragraphs[0]
                    if background and background.paragraphs
                    else ""
                ),
            ),
            config={
                **build_langfuse_config(state, tags),
                "run_name": "synthesis.core_answer",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()

        try:
            data = json.loads(text)
            return CoreAnswer(
                query=rq,
                answer=data.get("answer", text),
                directive=data.get("directive", ""),
            )
        except json.JSONDecodeError:
            sentences = text.split(". ")
            return CoreAnswer(
                query=rq,
                answer=sentences[0] + "." if sentences else text,
                directive=". ".join(sentences[1:]) if len(sentences) > 1 else "",
            )

    except Exception as e:
        logger.warning(f"Core answer generation failed: {e}")
        return CoreAnswer(
            query=rq,
            answer=f"Evidence review identified {len(interventions)} intervention types.",
            directive="Further analysis recommended.",
        )


async def _generate_recommendations(
    state: SynthesisState,
    rq: str,
    interventions: List[PolicyIntervention],
    theme_evidence: Dict[str, List[RetrievedChunk]],
    chunk_to_citation: Dict[str, int],
) -> List[RecommendationItem]:
    """Generate recommendations with RAG grounding.

    Args:
        state: Current workflow state.
        rq: Research question.
        interventions: Aggregated interventions.
        theme_evidence: RAG evidence for interventions.
        chunk_to_citation: Mapping of chunk IDs to citation numbers.

    Returns:
        List of recommendation items.
    """
    all_evidence = []
    for intr in interventions[:5]:
        for chunk in theme_evidence.get(intr.intervention_name, [])[:3]:
            all_evidence.append((chunk, intr.intervention_name))

    if not all_evidence:
        return []

    evidence_lines = [
        f'[{chunk_to_citation.get(c.chunk_id, 0)}] ({name}) "{c.content[:150]}..."'
        for c, name in all_evidence[:10]
    ]
    top_intrs = [
        f"{i.intervention_name} ({i.effect_consensus or 'mixed'})"
        for i in interventions[:5]
    ]

    prompt = build_recommendations_prompt()
    llm = get_llm(BRIEFING_MODEL, temperature=0)
    tags = [
        "component:synthesis",
        "component:synthesis.recommendations",
        f"model:{BRIEFING_MODEL}",
    ]

    try:
        structured_llm = llm.with_structured_output(RecommendationsOutput)
        result: RecommendationsOutput = await structured_llm.ainvoke(
            prompt.format(
                research_question=rq,
                top_interventions=escape_braces("\n".join(top_intrs)),
                evidence_context=escape_braces("\n".join(evidence_lines)),
            ),
            config={
                **build_langfuse_config(state, tags),
                "run_name": "synthesis.recommendations",
            },
        )
        for idx, rec in enumerate(result.recommendations, 1):
            rec.number = idx
        return result.recommendations
    except Exception as e:
        logger.warning(
            f"Structured recommendations failed: {e}, falling back to text parsing"
        )
        resp = await llm.ainvoke(
            prompt.format(
                research_question=rq,
                top_interventions=escape_braces("\n".join(top_intrs)),
                evidence_context=escape_braces("\n".join(evidence_lines)),
            ),
            config={
                **build_langfuse_config(state, tags),
                "run_name": "synthesis.recommendations.fallback",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return _parse_recommendations(text)


def _parse_recommendations(text: str) -> List[RecommendationItem]:
    """Fallback parser for recommendations.

    Args:
        text: Raw LLM output text.

    Returns:
        List of parsed recommendation items.
    """
    pattern = r"\*\*([^:*]+)\*\*[:\s]*(.+?)(?=\n\*\*|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    return [
        RecommendationItem(
            number=idx,
            title=title.strip(),
            description=desc.strip(),
            citation_numbers=[int(m) for m in re.findall(r"\[(\d+)\]", desc)],
        )
        for idx, (title, desc) in enumerate(matches, 1)
    ]


def _build_top_citations(
    grounded_citations: List[CitationInfo],
    interventions_table: List[InterventionTableRow],
) -> List[TopCitationItem]:
    """Build top citations ranked by usage.

    Args:
        grounded_citations: All grounded citations.
        interventions_table: Intervention table rows.

    Returns:
        List of top citation items.
    """
    usage: Counter = Counter()
    for row in interventions_table:
        for cit_num in row.citation_numbers:
            usage[cit_num] += 1

    citation_by_num = {c.citation_number: c for c in grounded_citations}
    ranked = sorted(usage.keys(), key=lambda n: (-usage[n], n))

    top_citations = []
    for cit_num in ranked[:5]:
        cit = citation_by_num.get(cit_num)
        if cit:
            top_citations.append(
                TopCitationItem(
                    citation_number=cit_num,
                    title=cit.title or "Untitled",
                    author_year=f"{cit.author_short or 'Unknown'}, {cit.year or 'n.d.'}",
                    reason=f"Referenced in {usage[cit_num]} intervention(s)",
                    url=cit.url,
                )
            )

    return top_citations
