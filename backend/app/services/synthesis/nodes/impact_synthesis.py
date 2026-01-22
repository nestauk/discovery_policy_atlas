"""
Impact synthesis node for Tier 2 verdict, magnitude, and transferability computation.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.services.synthesis.state import SynthesisState, FinalTheme
from app.services.synthesis.schemas import (
    OutcomeTheme,
    PolicyIntervention,
    TransferabilityBreakdown,
    VerdictType,
    SemanticMagnitudeType,
    CausalityClaimType,
    RiskTheme,
    MagnitudeDetail,
    CausalityDetail,
)
from app.utils.llm.llm_utils import get_llm


EFFECT_SIZE_SCALES = {
    "cohens_d": {
        "marginal": 0.2,
        "moderate": 0.5,
        "substantial": 0.8,
        "transformational": 1.2,
    },
    "smd": {
        "marginal": 0.2,
        "moderate": 0.5,
        "substantial": 0.8,
        "transformational": 1.2,
    },
    "or": {
        "marginal": 1.2,
        "moderate": 1.5,
        "substantial": 2.0,
        "transformational": 3.0,
    },
    "rr": {
        "marginal": 1.2,
        "moderate": 1.5,
        "substantial": 2.0,
        "transformational": 3.0,
    },
    "percentage": {
        "marginal": 5,
        "moderate": 15,
        "substantial": 30,
        "transformational": 50,
    },
    "percent": {
        "marginal": 5,
        "moderate": 15,
        "substantial": 30,
        "transformational": 50,
    },
}


DEFAULT_USER_CONSTRAINTS = {
    "cost": "moderate",
    "staffing": "moderate",
    "implementation_complexity": "moderate",
}

TRANSFERABILITY_MODEL = os.getenv("TRANSFERABILITY_MODEL", "gpt-4o-mini")
IMPACT_SUMMARY_MODEL = os.getenv("IMPACT_SUMMARY_MODEL", "gpt-4o-mini")

# Target context for transferability evaluation (Policy Atlas users are UK-based).
DEFAULT_TARGET_GEOGRAPHY = ["UK"]


UK_COUNTRY_SET = {
    "uk",
    "united kingdom",
    "great britain",
    "england",
    "scotland",
    "wales",
    "northern ireland",
}


async def compute_impact_syntheses(state: SynthesisState) -> SynthesisState:
    """Compute Tier 2 impact synthesis and enrich aggregated tables."""
    print("--- Computing Impact Syntheses (Tier 2) ---")

    interventions = state.get("aggregated_interventions") or []
    outcomes = state.get("aggregated_outcomes") or []
    risk_themes: List[FinalTheme] = state.get("final_risk_themes") or []
    raw_extractions = state.get("raw_extractions") or []
    doc_scores = state.get("doc_scores") or {}
    theme_to_doc_uuids = state.get("theme_to_doc_uuids") or {}
    theme_to_extraction_ids = state.get("theme_to_extraction_ids") or {}
    doc_metadata = state.get("doc_metadata") or {}
    extraction_to_doc = state.get("extraction_to_doc") or {}

    target_inner_setting = state.get("target_inner_setting") or []
    target_population = state.get("target_population") or []
    target_geography = DEFAULT_TARGET_GEOGRAPHY
    target_outcomes = state.get("target_outcomes") or []
    implementation_constraints = state.get("implementation_constraints") or {}

    intervention_extractions = [
        e for e in raw_extractions if e.get("type") == "intervention"
    ]
    result_extractions = [e for e in raw_extractions if e.get("type") == "result"]
    conclusion_extractions = [
        e for e in raw_extractions if e.get("type") == "conclusion"
    ]

    doc_id_by_uuid = {
        str(uuid): str(meta.get("doc_id") or "") for uuid, meta in doc_metadata.items()
    }
    doc_uuid_by_doc_id = {
        str(meta.get("doc_id")): str(uuid)
        for uuid, meta in doc_metadata.items()
        if meta.get("doc_id")
    }

    # Enrich outcomes with verdict and magnitude
    enriched_outcomes: List[OutcomeTheme] = []
    for outcome in outcomes:
        verdict_label, discord_flag, discord_reason = determine_verdict(
            outcome.positive_count,
            outcome.negative_count,
            outcome.null_count,
            has_attribution_claims=check_attribution_claims(
                outcome.source_doc_ids, result_extractions
            ),
        )

        magnitude, magnitude_detail = compute_magnitude_hybrid(
            outcome.source_doc_ids,
            result_extractions,
            doc_scores,
            doc_uuid_by_doc_id,
        )
        primary_causal_mechanism, causal_mechanism_detail = compute_causal_mechanism(
            outcome.source_doc_ids,
            result_extractions,
            doc_scores,
            doc_uuid_by_doc_id,
        )

        intervention_theme_id = outcome.intervention_theme_id

        enriched_outcomes.append(
            OutcomeTheme(
                **outcome.model_dump(
                    exclude={
                        "verdict_label",
                        "verdict_description",
                        "discord_flag",
                        "discord_reason",
                        "predicted_magnitude",
                        "magnitude_detail",
                        "intervention_theme_id",
                        "primary_causal_mechanism",
                        "causal_mechanism_detail",
                    }
                ),
                verdict_label=verdict_label,
                verdict_description=generate_verdict_description(
                    verdict_label, outcome
                ),
                discord_flag=discord_flag,
                discord_reason=discord_reason,
                predicted_magnitude=magnitude,
                magnitude_detail=magnitude_detail,
                intervention_theme_id=intervention_theme_id,
                primary_causal_mechanism=primary_causal_mechanism,
                causal_mechanism_detail=causal_mechanism_detail,
            )
        )

    outcomes_by_intervention: Dict[str, List[OutcomeTheme]] = {}
    for outcome in enriched_outcomes:
        intervention_key = outcome.intervention_theme_id
        if intervention_key:
            outcomes_by_intervention.setdefault(intervention_key, []).append(outcome)

    # Enrich interventions with transferability and causal mechanism
    transferability_llm = get_llm(TRANSFERABILITY_MODEL, temperature=0.0)
    impact_summary_llm = get_llm(IMPACT_SUMMARY_MODEL, temperature=0.2)

    async def build_intervention(
        intervention: PolicyIntervention,
    ) -> PolicyIntervention:
        doc_uuids = theme_to_doc_uuids.get(intervention.intervention_name, [])
        extraction_ids = theme_to_extraction_ids.get(intervention.intervention_name, [])
        rating, note, breakdown = await compute_transferability(
            doc_uuids,
            extraction_ids,
            intervention_extractions,
            target_inner_setting,
            target_population,
            target_geography,
            implementation_constraints,
            doc_scores,
            transferability_llm,
        )
        outcome_list = outcomes_by_intervention.get(intervention.intervention_name, [])
        impact_summary = intervention.impact_summary
        if outcome_list:
            impact_summary = await generate_impact_summary(
                intervention,
                outcome_list,
                target_outcomes,
                state.get("research_question") or "Not specified",
                impact_summary_llm,
            )
        return PolicyIntervention(
            **intervention.model_dump(
                exclude={
                    "impact_summary",
                    "transferability_rating",
                    "transferability_note",
                    "transferability_breakdown",
                }
            ),
            impact_summary=impact_summary,
            transferability_rating=rating,
            transferability_note=note,
            transferability_breakdown=breakdown,
        )

    enriched_interventions = await asyncio.gather(
        *(build_intervention(intervention) for intervention in interventions)
    )

    # Link risk themes to interventions and compute harm warnings
    enriched_risk_themes: List[RiskTheme] = []
    for risk_theme in risk_themes:
        risk_doc_uuids = set()
        for concept in risk_theme.concepts or []:
            doc_uuid = extraction_to_doc.get(concept.id)
            if not doc_uuid and "_risk_" in concept.id:
                base_id = concept.id.rsplit("_risk_", 1)[0]
                doc_uuid = extraction_to_doc.get(base_id)
            if doc_uuid:
                risk_doc_uuids.add(doc_uuid)
        risk_doc_ids = {
            doc_id_by_uuid.get(doc_uuid)
            for doc_uuid in risk_doc_uuids
            if doc_id_by_uuid.get(doc_uuid)
        }
        linked_interventions = link_risk_to_interventions(
            risk_doc_uuids, enriched_interventions, theme_to_doc_uuids
        )
        linked_intervention_id = next(
            (
                item["intervention_name"]
                for item in linked_interventions
                if item.get("link_strength") == "primary"
            ),
            None,
        )
        has_harm_warning = compute_harm_warning(
            list(risk_doc_ids), conclusion_extractions, doc_scores, doc_uuid_by_doc_id
        )

        enriched_risk_themes.append(
            RiskTheme(
                theme_name=risk_theme.name,
                summary_description=risk_theme.description,
                frequency=risk_theme.frequency,
                source_doc_ids=sorted(risk_doc_ids),
                has_harm_warning=has_harm_warning,
                linked_intervention_theme_id=linked_intervention_id,
                linked_interventions=linked_interventions,
            )
        )

    return {
        "aggregated_outcomes": enriched_outcomes,
        "aggregated_interventions": enriched_interventions,
        "final_risk_themes": enriched_risk_themes,
    }


WELL_EVIDENCED_THRESHOLD = 15
EVIDENCED_THRESHOLD = 8
MINIMUM_THRESHOLD = 5
DISCORD_RATIO = 0.4


def determine_verdict(
    pos_weight: int,
    neg_weight: int,
    null_weight: int,
    has_attribution_claims: bool,
) -> Tuple[VerdictType, bool, Optional[str]]:
    """Determine verdict using ratio-based discord detection."""
    total = pos_weight + neg_weight + null_weight
    if total < MINIMUM_THRESHOLD:
        return ("insufficient_evidence", False, None)

    if pos_weight > 0 and neg_weight > 0:
        ratio = min(pos_weight, neg_weight) / max(pos_weight, neg_weight)
        if ratio > DISCORD_RATIO:
            return (
                "contested",
                True,
                f"Evidence split: {pos_weight}↑ vs {neg_weight}↓",
            )

    if null_weight > pos_weight and null_weight > neg_weight:
        verdict: VerdictType = "no_effect"
    elif pos_weight > neg_weight:
        if pos_weight > WELL_EVIDENCED_THRESHOLD:
            verdict = "well_evidenced_increase"
        elif pos_weight > EVIDENCED_THRESHOLD:
            verdict = "evidenced_increase"
        else:
            verdict = "suggested_increase"
    elif neg_weight > pos_weight:
        if neg_weight > WELL_EVIDENCED_THRESHOLD:
            verdict = "well_evidenced_decrease"
        elif neg_weight > EVIDENCED_THRESHOLD:
            verdict = "evidenced_decrease"
        else:
            verdict = "suggested_decrease"
    else:
        verdict = "insufficient_evidence"

    if not has_attribution_claims and verdict.startswith("well_evidenced"):
        verdict = "probable_contribution"

    return (verdict, False, None)


def compute_magnitude_hybrid(
    source_doc_ids: List[str],
    result_extractions: List[Dict],
    doc_scores: Dict[str, Dict],
    doc_uuid_by_doc_id: Dict[str, str],
) -> Tuple[SemanticMagnitudeType, Optional[MagnitudeDetail]]:
    """Compute magnitude from effect sizes using hybrid scale detection."""
    parsed_effects: List[Dict[str, object]] = []
    direction_weights = {"increase": 0, "decrease": 0}
    for ext in result_extractions:
        doc_id = ext.get("doc_id") or ""
        if doc_id not in source_doc_ids:
            continue
        effect_size = ext.get("effect_size", "")
        effect_type = (ext.get("effect_size_type") or "").lower()
        doc_uuid = doc_uuid_by_doc_id.get(doc_id, "")
        quality = doc_scores.get(doc_uuid, {}).get("evidence_score", 1) or 1
        effect_direction = (ext.get("effect_direction") or "").lower()
        if effect_direction in direction_weights:
            direction_weights[effect_direction] += quality

        numeric_val = parse_effect_size_value(effect_size)
        if numeric_val is None:
            continue

        scale_type = detect_scale_type(effect_type, effect_size)
        magnitude = apply_magnitude_thresholds(numeric_val, scale_type)
        parsed_effects.append(
            {
                "magnitude": magnitude,
                "quality": quality,
                "doc_id": doc_id,
                "direction": effect_direction,
                "scale_type": scale_type,
            }
        )

    if not parsed_effects:
        return ("unknown", None)

    direction = resolve_effect_direction(direction_weights)
    aligned_effects = [
        effect
        for effect in parsed_effects
        if direction == "contested" or effect.get("direction") == direction
    ]
    if not aligned_effects:
        return ("unknown", None)

    weights: Dict[str, int] = {}
    scale_counts: Dict[str, int] = {}
    for effect in aligned_effects:
        mag = effect["magnitude"]
        qual = int(effect["quality"])
        scale = str(effect["scale_type"])
        weights[mag] = weights.get(mag, 0) + qual
        scale_counts[scale] = scale_counts.get(scale, 0) + 1

    magnitude_order = ["marginal", "moderate", "substantial", "transformational"]
    max_weight = max(weights.values())
    top = [m for m, w in weights.items() if w == max_weight]
    if len(top) > 1:
        result = min(
            top,
            key=lambda m: magnitude_order.index(m) if m in magnitude_order else 99,
        )
    else:
        result = top[0]

    unique_doc_count = len(
        {effect["doc_id"] for effect in aligned_effects if effect.get("doc_id")}
    )
    total_sources = len({doc_id for doc_id in source_doc_ids if doc_id})
    measurement_count = len(aligned_effects)
    dominant_scale = max(scale_counts.items(), key=lambda x: x[1])[0]
    detail = MagnitudeDetail(
        direction=direction,
        bucket_counts=weights,
        source_count=unique_doc_count,
        total_sources=total_sources,
        measurement_count=measurement_count,
        thresholds=format_effect_thresholds(dominant_scale),
    )
    return (result, detail)


def format_outcomes_for_summary(outcomes: List[OutcomeTheme]) -> str:
    """Format outcome themes for summary synthesis."""
    lines = []
    for outcome in outcomes:
        verdict = outcome.verdict_label or "insufficient_evidence"
        magnitude = outcome.predicted_magnitude or "unknown"
        counts = (
            f"{outcome.positive_count}↑ {outcome.negative_count}↓ {outcome.null_count}—"
        )
        lines.append(
            f"- {outcome.outcome_name}: verdict={verdict}, magnitude={magnitude}, counts={counts}"
        )
    return "\n".join(lines)


async def generate_impact_summary(
    intervention: PolicyIntervention,
    outcomes: List[OutcomeTheme],
    target_outcomes: List[str],
    research_question: str,
    llm,
) -> str:
    """Generate an LLM summary of the impact profile for an intervention."""
    outcome_focus = (
        f"User-specified outcomes of interest: {', '.join(target_outcomes)}."
        if target_outcomes
        else "No user-specified outcomes were provided."
    )
    prompt = (
        "You are summarising the impact of a policy intervention for UK policymakers.\n\n"
        f"Research question: {research_question}\n"
        f"Intervention: {intervention.intervention_name}\n"
        f"Description: {intervention.brief_description}\n\n"
        f"Outcome evidence:\n{format_outcomes_for_summary(outcomes)}\n\n"
        f"{outcome_focus}\n\n"
        "Write 2-3 sentences that:\n"
        "1. Directly state the intervention's effect on the outcome of interest (if specified)\n"
        "2. Note the evidence strength (well-evidenced, evidenced, or suggested)\n"
        "3. Flag any contested or insufficient evidence areas\n\n"
        "Be direct and factual. Interpret direction in context (e.g., a decrease in obesity is positive). "
        "Do not use jargon. Write for a non-specialist policy audience."
    )
    try:
        response = await llm.ainvoke(prompt)
        return (getattr(response, "content", None) or str(response)).strip()
    except Exception:
        return intervention.impact_summary


class TransferabilityAssessment(BaseModel):
    """Structured output for transferability assessment."""

    match_level: str = Field(
        ..., description="match, similar, comparable, partial, or mismatch"
    )
    explanation: str = Field(..., description="One sentence explanation")


def normalise_match_level(value: str) -> str:
    """Normalise match level to supported labels."""
    lowered = (value or "").strip().lower()
    if lowered == "match":
        return "match"
    if lowered == "similar":
        return "similar"
    if lowered == "comparable":
        return "comparable"
    if lowered == "partial":
        return "partial"
    if lowered == "mismatch":
        return "mismatch"
    return "unknown"


def normalise_level(value: Optional[str]) -> Optional[str]:
    """Normalise ordinal levels to low/moderate/high."""
    if not value:
        return None
    lowered = value.strip().lower()
    if "high" in lowered:
        return "high"
    if "moderate" in lowered:
        return "moderate"
    if "low" in lowered:
        return "low"
    return None


def infer_evidence_level(levels: List[Optional[str]]) -> str:
    """Infer the most common evidence level from extracted data."""
    counts: Dict[str, int] = {}
    for raw in levels:
        level = normalise_level(raw)
        if not level:
            continue
        counts[level] = counts.get(level, 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=counts.get)


def build_evidence_note(
    dimension_name: str, level: str, justifications: List[Optional[str]]
) -> str:
    """Summarise evidence context notes for a dimension."""
    if level == "unknown":
        return f"Insufficient evidence context for {dimension_name.replace('_', ' ')}."
    return f"Evidence suggests {level} {dimension_name.replace('_', ' ')}."


async def assess_transferability_dimension(
    dimension_name: str,
    target_values: List[str],
    evidence_values: List[Optional[str]],
    llm,
) -> Tuple[str, str]:
    """Assess semantic similarity for a transferability dimension.

    Args:
        dimension_name: Name of the dimension being assessed.
        target_values: Target context values for the dimension.
        evidence_values: Evidence context values for the dimension.
        llm: LLM client to use for assessment.

    Returns:
        Tuple[str, str]: Match level and explanation.
    """
    target_values = [v for v in target_values if v and v.strip()]
    evidence_values = [v for v in evidence_values if v and v.strip()]
    if not target_values or not evidence_values:
        return ("unknown", "Insufficient context for assessment")

    prompt = (
        "You are assessing transferability of research evidence to a target context.\n\n"
        f"Dimension: {dimension_name}\n"
        f"Target context options: {target_values}\n"
        f"Evidence context: {evidence_values}\n\n"
        "The user is interested in any of the target context options. If the evidence "
        "matches one or more of the target options, that is a good match.\n\n"
        "Match levels:\n"
        "- match: Evidence matches at least one target option directly\n"
        "- similar: Evidence is highly similar to at least one target option\n"
        "- comparable: Evidence is from a comparable context to at least one target option\n"
        "- partial: Some overlap with target options, but adaptation needed\n"
        "- mismatch: No meaningful overlap\n\n"
        "Consider:\n"
        "- For geography: socioeconomic development level, healthcare system similarity, "
        "cultural context\n"
        "- For population: age group overlap, demographic similarity, vulnerability factors\n"
        "- For setting: delivery environment similarity, institutional context\n\n"
        "Respond with JSON:\n"
        '{"match_level": "match|similar|comparable|partial|mismatch", "explanation": "One sentence reason"}'
    )

    try:
        structured_llm = llm.with_structured_output(
            TransferabilityAssessment, method="function_calling"
        )
        response: TransferabilityAssessment = await structured_llm.ainvoke(prompt)
        match_level = normalise_match_level(response.match_level)
        explanation = (response.explanation or "").strip()
        if not explanation:
            explanation = "No explanation provided"
        return (match_level, explanation)
    except Exception:
        return ("unknown", "LLM assessment failed")


async def explain_tolerance_dimension(
    dimension_name: str,
    tolerance_level: str,
    evidence_level: str,
    exceeds_tolerance: bool,
    llm,
) -> str:
    """Summarise tolerance alignment using a short LLM explanation.

    Args:
        dimension_name: Name of the dimension being assessed.
        tolerance_level: User-specified tolerance level.
        evidence_level: Evidence-based level from extractions.
        exceeds_tolerance: Whether evidence exceeds the tolerance.
        llm: LLM client to use for explanation.

    Returns:
        Short explanation sentence.
    """
    status = (
        "exceeds the user tolerance"
        if exceeds_tolerance
        else "is within the user tolerance"
    )
    prompt = (
        "Write one short sentence explaining tolerance alignment.\n\n"
        f"Dimension: {dimension_name}\n"
        f"User tolerance: {tolerance_level}\n"
        f"Evidence level: {evidence_level}\n"
        f"Status: {status}\n\n"
        "Keep it factual and concise."
    )
    try:
        response = await llm.ainvoke(prompt)
        return (getattr(response, "content", None) or str(response)).strip() or (
            f"{dimension_name.replace('_', ' ')} evidence {status}."
        )
    except Exception:
        return f"{dimension_name.replace('_', ' ')} evidence {status}."


async def compute_transferability(
    doc_uuids: List[str],
    extraction_ids: List[str],
    intervention_extractions: List[Dict],
    target_inner_setting: List[str],
    target_population: List[str],
    target_geography: List[str],
    implementation_constraints: Optional[Dict[str, Optional[str]]],
    doc_scores: Dict[str, Dict],
    llm,
) -> Tuple[str, str, TransferabilityBreakdown]:
    """Compute transferability across context and implementation dimensions.

    Args:
        doc_uuids: Document UUIDs associated with the intervention.
        extraction_ids: Extraction IDs assigned to the intervention theme.
        intervention_extractions: Raw intervention extractions.
        target_inner_setting: Target inner setting values.
        target_population: Target population values.
        target_geography: Target geography values.
        implementation_constraints: Optional user-specified implementation constraints.
        doc_scores: Document score metadata.
        llm: LLM client to use for semantic similarity.

    Returns:
        Tuple[str, str, TransferabilityBreakdown]: Rating, note, and breakdown.
    """
    breakdown = TransferabilityBreakdown(
        inner_setting="unknown",
        population="unknown",
        geography="unknown",
        notes={},
        implementation_constraints_specified=False,
        implementation_evidence={},
        implementation_constraints={},
        implementation_exceeds_tolerance={},
    )

    extraction_id_set = {str(ex_id) for ex_id in extraction_ids if ex_id}
    if extraction_id_set:
        relevant_extractions = [
            e for e in intervention_extractions if str(e.get("id")) in extraction_id_set
        ]
    else:
        relevant_extractions = [
            e for e in intervention_extractions if e.get("doc_uuid") in doc_uuids
        ]
    if not relevant_extractions:
        return ("Unknown", "No intervention data available", breakdown)

    cost_levels = [
        e.get("cost_level") or e.get("resource_intensity") for e in relevant_extractions
    ]
    cost_justifications = [e.get("cost_justification") for e in relevant_extractions]
    staffing_levels = [
        e.get("staffing_level") or e.get("resource_intensity")
        for e in relevant_extractions
    ]
    staffing_justifications = [
        e.get("staffing_justification") for e in relevant_extractions
    ]
    complexity_levels = [
        e.get("implementation_complexity_level") or e.get("delivery_complexity")
        for e in relevant_extractions
    ]
    complexity_justifications = [
        e.get("implementation_complexity_justification") for e in relevant_extractions
    ]

    (
        (inner_setting_level, inner_setting_note),
        (population_level, population_note),
        (geography_level, geography_note),
    ) = await asyncio.gather(
        assess_transferability_dimension(
            "inner_setting",
            target_inner_setting,
            [e.get("inner_setting") for e in relevant_extractions],
            llm,
        ),
        assess_transferability_dimension(
            "population",
            target_population,
            [e.get("population_intervened") for e in relevant_extractions],
            llm,
        ),
        assess_transferability_dimension(
            "geography",
            target_geography,
            [e.get("country") for e in relevant_extractions],
            llm,
        ),
    )

    breakdown.inner_setting = inner_setting_level
    breakdown.population = population_level
    breakdown.geography = geography_level
    breakdown.notes = {
        "inner_setting": inner_setting_note,
        "population": population_note,
        "geography": geography_note,
    }

    constraints = implementation_constraints or {}
    constraint_values = {
        "cost": normalise_level(constraints.get("cost")),
        "staffing": normalise_level(constraints.get("staffing")),
        "implementation_complexity": normalise_level(
            constraints.get("implementation_complexity")
        ),
    }
    specified_constraints = {
        key: value for key, value in constraint_values.items() if value
    }
    breakdown.implementation_constraints_specified = bool(specified_constraints)
    breakdown.implementation_constraints = specified_constraints
    breakdown.implementation_exceeds_tolerance = {
        key: False for key in ("cost", "staffing", "implementation_complexity")
    }

    evidence_levels = {
        "cost": infer_evidence_level(cost_levels),
        "staffing": infer_evidence_level(staffing_levels),
        "implementation_complexity": infer_evidence_level(complexity_levels),
    }
    breakdown.implementation_evidence = evidence_levels

    def compare_tolerance_level(
        tolerance_level: Optional[str], evidence_level: Optional[str]
    ) -> Optional[bool]:
        level_map = {"low": 1, "moderate": 2, "high": 3}
        if not tolerance_level or not evidence_level:
            return None
        tolerance_val = level_map.get(tolerance_level)
        evidence_val = level_map.get(evidence_level)
        if tolerance_val is None or evidence_val is None:
            return None
        return evidence_val > tolerance_val

    async def assess_or_infer_level(
        dimension: str,
        target_level: Optional[str],
        levels: List[Optional[str]],
        justifications: List[Optional[str]],
    ) -> Tuple[str, str]:
        inferred = evidence_levels.get(dimension, "unknown")
        if target_level:
            exceeds = compare_tolerance_level(target_level, inferred)
            breakdown.implementation_exceeds_tolerance[dimension] = bool(exceeds)
            return inferred, await explain_tolerance_dimension(
                dimension,
                target_level,
                inferred,
                bool(exceeds),
                llm,
            )
        return inferred, build_evidence_note(dimension, inferred, justifications)

    (
        (cost_level, cost_note),
        (staffing_level, staffing_note),
        (complexity_level, complexity_note),
    ) = await asyncio.gather(
        assess_or_infer_level(
            "cost",
            specified_constraints.get("cost"),
            cost_levels,
            cost_justifications,
        ),
        assess_or_infer_level(
            "staffing",
            specified_constraints.get("staffing"),
            staffing_levels,
            staffing_justifications,
        ),
        assess_or_infer_level(
            "implementation_complexity",
            specified_constraints.get("implementation_complexity"),
            complexity_levels,
            complexity_justifications,
        ),
    )

    breakdown.notes.update(
        {
            "cost": cost_note,
            "staffing": staffing_note,
            "implementation_complexity": complexity_note,
        }
    )

    match_scores = {
        "match": 1.0,
        "similar": 0.85,
        "comparable": 0.7,
        "partial": 0.4,
        "mismatch": 0.0,
        "unknown": None,
    }

    def compute_fit_rating(
        scores: List[Optional[float]], scope_label: str
    ) -> Tuple[str, str]:
        valid_scores = [score for score in scores if score is not None]
        if len(valid_scores) < 2:
            return (
                "Unknown",
                f"Insufficient {scope_label} data for transferability assessment",
            )
        if any(score == 0.0 for score in valid_scores):
            return (
                "Poor Fit",
                f"{scope_label.capitalize()} mismatch identified in one or more dimensions",
            )
        average_score = sum(valid_scores) / len(valid_scores)
        if average_score >= 0.85:
            return ("Excellent Fit", "Strong alignment with target context")
        if average_score >= 0.70:
            return ("Good Fit", "Good alignment with minor gaps")
        if average_score >= 0.50:
            return ("Moderate Fit", "Partial alignment; adaptation likely needed")
        if average_score >= 0.30:
            return (
                "Limited Fit",
                "Significant gaps; substantial adaptation likely needed",
            )
        return ("Poor Fit", "Minimal alignment with target context")

    context_scores = [
        match_scores.get(breakdown.inner_setting),
        match_scores.get(breakdown.population),
        match_scores.get(breakdown.geography),
    ]
    context_rating, context_note = compute_fit_rating(context_scores, "context")

    breakdown.context_fit_rating = context_rating
    breakdown.implementation_fit_rating = None
    if breakdown.implementation_constraints_specified:
        exceeds_values = list(breakdown.implementation_exceeds_tolerance.values())
        if not exceeds_values:
            breakdown.implementation_fit_rating = "Unknown"
        elif all(exceeds_values):
            breakdown.implementation_fit_rating = "Poor Fit"
        elif any(exceeds_values):
            breakdown.implementation_fit_rating = "Limited Fit"
        else:
            breakdown.implementation_fit_rating = "Good Fit"

    return (context_rating, context_note, breakdown)


def compute_causal_mechanism(
    source_doc_ids: List[str],
    result_extractions: List[Dict],
    doc_scores: Dict[str, Dict],
    doc_uuid_by_doc_id: Dict[str, str],
) -> Tuple[Optional[CausalityClaimType], Optional[CausalityDetail]]:
    """Determine primary causal mechanism based on result-level claims."""
    weights: Dict[str, int] = {}
    for ext in result_extractions:
        doc_id = ext.get("doc_id") or ""
        if doc_id not in source_doc_ids:
            continue
        claim = ext.get("causality_claim")
        if not claim:
            continue
        doc_uuid = doc_uuid_by_doc_id.get(doc_id, "")
        quality = doc_scores.get(doc_uuid, {}).get("evidence_score", 1) or 1
        weights[claim] = weights.get(claim, 0) + quality
    if not weights:
        return (None, None)
    primary = max(weights.items(), key=lambda x: x[1])[0]
    detail = CausalityDetail(
        attribution=weights.get("attribution", 0),
        contribution=weights.get("contribution", 0),
        correlation=weights.get("correlation", 0),
    )
    return (primary, detail)


def resolve_effect_direction(direction_weights: Dict[str, int]) -> str:
    """Resolve the dominant effect direction for magnitude counting."""
    increase = direction_weights.get("increase", 0)
    decrease = direction_weights.get("decrease", 0)
    if increase == 0 and decrease == 0:
        return "contested"
    if increase and decrease:
        ratio = min(increase, decrease) / max(increase, decrease)
        if ratio > DISCORD_RATIO:
            return "contested"
    if increase >= decrease:
        return "increase"
    return "decrease"


def format_effect_thresholds(scale_type: str) -> str:
    """Format effect size thresholds for tooltip display."""
    if scale_type in ("cohens_d", "smd"):
        return "d<0.2=marginal, 0.2-0.5=moderate, 0.5-0.8=substantial, >0.8=transformational"
    if scale_type in ("or", "rr"):
        return "1.0-1.2=marginal, 1.2-1.5=moderate, 1.5-2.0=substantial, >2.0=transformational"
    return "0-5=marginal, 5-15=moderate, 15-30=substantial, >30=transformational"


def check_attribution_claims(
    source_doc_ids: List[str], result_extractions: List[Dict]
) -> bool:
    """Check for any attribution claims in result extractions."""
    for ext in result_extractions:
        if ext.get("doc_id") not in source_doc_ids:
            continue
        if ext.get("causality_claim") == "attribution":
            return True
    return False


def find_linked_intervention(
    outcome_doc_ids: List[str],
    interventions: List[PolicyIntervention],
    theme_to_doc_uuids: Dict[str, List[str]],
    doc_id_by_uuid: Dict[str, str],
) -> Optional[str]:
    """Find the intervention theme with max document overlap."""
    outcome_doc_ids_set = set(outcome_doc_ids)
    best_name = None
    best_overlap = 0
    for intervention in interventions:
        uuids = theme_to_doc_uuids.get(intervention.intervention_name, [])
        doc_ids = {doc_id_by_uuid.get(u) for u in uuids if doc_id_by_uuid.get(u)}
        overlap = len(outcome_doc_ids_set.intersection(doc_ids))
        if overlap > best_overlap:
            best_overlap = overlap
            best_name = intervention.intervention_name
    return best_name


def link_risk_to_interventions(
    risk_doc_uuids: set[str],
    interventions: List[PolicyIntervention],
    theme_to_doc_uuids: Dict[str, List[str]],
    min_overlap: int = 1,
) -> List[Dict[str, str]]:
    """Link risk theme to multiple interventions via document overlap.

    Args:
        risk_doc_uuids: Document UUIDs associated with the risk theme.
        interventions: Aggregated intervention themes.
        theme_to_doc_uuids: Mapping from theme name to associated document UUIDs.
        min_overlap: Minimum overlap count to establish a link.

    Returns:
        List[Dict[str, str]]: Linked interventions with link_strength.
    """
    if not risk_doc_uuids:
        return []
    overlaps: List[Tuple[str, int]] = []
    for intervention in interventions:
        uuids = set(theme_to_doc_uuids.get(intervention.intervention_name, []))
        overlap = len(risk_doc_uuids.intersection(uuids))
        if overlap >= min_overlap:
            overlaps.append((intervention.intervention_name, overlap))

    if not overlaps:
        return []

    overlaps.sort(key=lambda x: x[1], reverse=True)
    max_overlap = overlaps[0][1]
    linked = []
    for name, overlap in overlaps:
        strength = "primary" if overlap == max_overlap else "secondary"
        linked.append({"intervention_name": name, "link_strength": strength})
    return linked


def compute_harm_warning(
    source_doc_ids: List[str],
    conclusion_extractions: List[Dict],
    doc_scores: Dict[str, Dict],
    doc_uuid_by_doc_id: Dict[str, str],
) -> bool:
    """Check if >20% of high-quality docs have unintended consequences."""
    high_quality_docs = []
    for doc_id in source_doc_ids:
        doc_uuid = doc_uuid_by_doc_id.get(doc_id, "")
        score_entry = doc_scores.get(doc_uuid) or {}
        evidence_score = score_entry.get("evidence_score") or 0
        if evidence_score >= 4:
            high_quality_docs.append(doc_id)
    if not high_quality_docs:
        return False

    unintended_count = 0
    for ext in conclusion_extractions:
        if ext.get("doc_id") not in high_quality_docs:
            continue
        predicted_impact = ext.get("predicted_impact") or {}
        if predicted_impact.get("unintended_consequences_detected") is True:
            unintended_count += 1

    return (unintended_count / len(high_quality_docs)) > 0.2


def parse_effect_size_value(effect_size: str) -> Optional[float]:
    """Extract numeric value from effect size string."""
    if not effect_size:
        return None
    match = re.search(r"[-+]?\d*\.?\d+", effect_size)
    return float(match.group()) if match else None


def detect_scale_type(effect_type: str, effect_size: str) -> str:
    """Detect effect size scale type from metadata or string patterns."""
    if effect_type in EFFECT_SIZE_SCALES:
        return effect_type
    lower = effect_size.lower()
    if "%" in effect_size or "percent" in lower:
        return "percentage"
    if "or" in lower or "odds" in lower:
        return "or"
    if "d=" in lower or "cohen" in lower:
        return "cohens_d"
    return "percentage"


def apply_magnitude_thresholds(value: float, scale_type: str) -> SemanticMagnitudeType:
    """Apply scale-specific thresholds to determine magnitude."""
    thresholds = EFFECT_SIZE_SCALES.get(scale_type, EFFECT_SIZE_SCALES["percentage"])
    value = abs(value)
    if value >= thresholds["transformational"]:
        return "transformational"
    if value >= thresholds["substantial"]:
        return "substantial"
    if value >= thresholds["moderate"]:
        return "moderate"
    return "marginal"


def resolve_text_match_dimension(
    targets: List[str], evidence_values: List[Optional[str]]
) -> str:
    """Resolve match status for free-text dimensions with multiple targets."""
    target_norms = [t.strip().lower() for t in targets if t and t.strip()]
    if not target_norms:
        return "Unknown"
    evidence_norms = [
        (v or "").strip().lower() for v in evidence_values if v is not None
    ]
    if not evidence_norms:
        return "Unknown"
    for target_norm in target_norms:
        for ev in evidence_norms:
            if target_norm in ev or ev in target_norm:
                return "Match"
    for target_norm in target_norms:
        for ev in evidence_norms:
            if any(tok in ev for tok in target_norm.split()):
                return "Partial"
    return "Mismatch"


def resolve_geography_dimension(
    target_geography: List[str], evidence_values: List[Optional[str]]
) -> str:
    """Resolve match status for geography."""
    target_norms = [t.strip().lower() for t in target_geography if t]
    evidence_norms = [
        (v or "").strip().lower() for v in evidence_values if v is not None
    ]
    if not target_norms:
        return "Unknown"
    if not evidence_norms:
        return "Unknown"
    if any(t in UK_COUNTRY_SET for t in target_norms):
        if any(e in UK_COUNTRY_SET for e in evidence_norms):
            return "Match"
    for t in target_norms:
        for e in evidence_norms:
            if t in e or e in t:
                return "Partial"
    return "Mismatch"


def resolve_level_dimension(target: str, evidence_values: List[Optional[str]]) -> str:
    """Resolve match for ordinal levels: low/moderate/high."""
    level_map = {"low": 1, "moderate": 2, "medium": 2, "high": 3}
    target_val = level_map.get((target or "").strip().lower())
    if target_val is None:
        return "Unknown"
    evidence_vals = [
        level_map.get((v or "").strip().lower()) for v in evidence_values if v
    ]
    evidence_vals = [v for v in evidence_vals if v is not None]
    if not evidence_vals:
        return "Unknown"
    avg = sum(evidence_vals) / len(evidence_vals)
    diff = abs(avg - target_val)
    if diff == 0:
        return "Match"
    if diff <= 1:
        return "Partial"
    return "Mismatch"


def generate_verdict_description(verdict: VerdictType, outcome: OutcomeTheme) -> str:
    """Generate a concise verdict description."""
    if verdict == "well_evidenced_increase":
        return "Evidence strongly supports an upward effect on this outcome."
    if verdict == "well_evidenced_decrease":
        return "Evidence strongly supports a downward effect on this outcome."
    if verdict == "evidenced_increase":
        return "Evidence supports an upward effect on this outcome."
    if verdict == "evidenced_decrease":
        return "Evidence supports a downward effect on this outcome."
    if verdict == "suggested_increase":
        return "Limited evidence suggests an upward effect on this outcome."
    if verdict == "suggested_decrease":
        return "Limited evidence suggests a downward effect on this outcome."
    if verdict == "contested":
        return "Evidence is split between upward and downward effects."
    if verdict == "no_effect":
        return "Evidence suggests no consistent effect."
    if verdict == "probable_contribution":
        return "Evidence suggests contribution but lacks strong attribution."
    return "Insufficient evidence to determine impact."
