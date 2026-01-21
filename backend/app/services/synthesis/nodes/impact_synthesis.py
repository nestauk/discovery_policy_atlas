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
    "resource_intensity": "moderate",
    "delivery_complexity": "moderate",
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
    doc_metadata = state.get("doc_metadata") or {}
    extraction_to_doc = state.get("extraction_to_doc") or {}

    target_inner_setting = state.get("target_inner_setting") or []
    target_population = state.get("target_population") or []
    target_geography = DEFAULT_TARGET_GEOGRAPHY
    target_outcomes = state.get("target_outcomes") or []

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

        magnitude, magnitude_confidence = compute_magnitude_hybrid(
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
                        "magnitude_confidence",
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
                magnitude_confidence=magnitude_confidence,
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
        rating, note, breakdown = await compute_transferability(
            doc_uuids,
            intervention_extractions,
            target_inner_setting,
            target_population,
            target_geography,
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
        linked_intervention_id = link_risk_to_intervention(
            risk_doc_uuids, enriched_interventions, theme_to_doc_uuids
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
            )
        )

    return {
        "aggregated_outcomes": enriched_outcomes,
        "aggregated_interventions": enriched_interventions,
        "final_risk_themes": enriched_risk_themes,
    }


def determine_verdict(
    pos_weight: int,
    neg_weight: int,
    null_weight: int,
    has_attribution_claims: bool,
) -> Tuple[VerdictType, bool, Optional[str]]:
    """Determine verdict using ratio-based discord detection."""
    total = pos_weight + neg_weight + null_weight
    if total < 5:
        return ("insufficient_evidence", False, None)

    if pos_weight > 0 and neg_weight > 0:
        ratio = min(pos_weight, neg_weight) / max(pos_weight, neg_weight)
        if ratio > 0.4:
            return (
                "contested",
                True,
                f"Evidence split: {pos_weight}↑ vs {neg_weight}↓",
            )

    if null_weight > pos_weight and null_weight > neg_weight:
        verdict: VerdictType = "ineffective"
    elif pos_weight > neg_weight:
        verdict = "high_confidence_positive" if pos_weight > 15 else "lean_positive"
    elif neg_weight > pos_weight:
        verdict = "high_confidence_negative" if neg_weight > 15 else "lean_negative"
    else:
        verdict = "insufficient_evidence"

    if not has_attribution_claims and verdict.startswith("high_confidence"):
        verdict = "probable_contribution"

    return (verdict, False, None)


def compute_magnitude_hybrid(
    source_doc_ids: List[str],
    result_extractions: List[Dict],
    doc_scores: Dict[str, Dict],
    doc_uuid_by_doc_id: Dict[str, str],
) -> Tuple[SemanticMagnitudeType, str]:
    """Compute magnitude from effect sizes using hybrid scale detection."""
    parsed_effects: List[Tuple[SemanticMagnitudeType, int, str]] = []
    for ext in result_extractions:
        doc_id = ext.get("doc_id") or ""
        if doc_id not in source_doc_ids:
            continue
        effect_size = ext.get("effect_size", "")
        effect_type = (ext.get("effect_size_type") or "").lower()
        doc_uuid = doc_uuid_by_doc_id.get(doc_id, "")
        quality = doc_scores.get(doc_uuid, {}).get("evidence_score", 1) or 1

        numeric_val = parse_effect_size_value(effect_size)
        if numeric_val is None:
            continue

        scale_type = detect_scale_type(effect_type, effect_size)
        magnitude = apply_magnitude_thresholds(numeric_val, scale_type)
        parsed_effects.append((magnitude, quality, doc_id))

    if not parsed_effects:
        return ("unknown", "No quantifiable effect sizes found")

    weights: Dict[str, int] = {}
    for mag, qual, _ in parsed_effects:
        weights[mag] = weights.get(mag, 0) + qual

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

    unique_doc_count = len({doc_id for _, _, doc_id in parsed_effects if doc_id})
    confidence = (
        f"Based on {len(parsed_effects)} effect size measurements across "
        f"{unique_doc_count} sources"
    )
    return (result, confidence)


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
    llm,
) -> str:
    """Generate an LLM summary of the impact profile for an intervention."""
    outcome_focus = (
        f"User-specified outcomes of interest: {', '.join(target_outcomes)}."
        if target_outcomes
        else "No user-specified outcomes were provided."
    )
    prompt = (
        "You are synthesising the impact profile for a policy intervention in UK policy context. "
        "Write 2-3 concise sentences in British English.\n\n"
        f"Intervention: {intervention.intervention_name}\n"
        f"Description: {intervention.brief_description}\n\n"
        f"Outcome evidence:\n{format_outcomes_for_summary(outcomes)}\n\n"
        f"{outcome_focus}\n\n"
        "Guidance:\n"
        "- Summarise overall direction and confidence.\n"
        "- Highlight contested or uncertain outcomes.\n"
        "- If user-specified outcomes exist, explicitly address them.\n"
    )
    try:
        response = await llm.ainvoke(prompt)
        return (getattr(response, "content", None) or str(response)).strip()
    except Exception:
        return intervention.impact_summary


class TransferabilityAssessment(BaseModel):
    """Structured output for transferability assessment."""

    match_level: str = Field(..., description="Match, Partial, or Mismatch")
    explanation: str = Field(..., description="One sentence explanation")


def normalise_match_level(value: str) -> str:
    """Normalise match level to supported labels."""
    lowered = (value or "").strip().lower()
    if lowered == "match":
        return "Match"
    if lowered == "partial":
        return "Partial"
    if lowered == "mismatch":
        return "Mismatch"
    return "Unknown"


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
        return ("Unknown", "Insufficient context for assessment")

    prompt = (
        "You are assessing transferability of research evidence to a target context.\n\n"
        f"Dimension: {dimension_name}\n"
        f"Target context: {target_values}\n"
        f"Evidence context: {evidence_values}\n\n"
        "Assess how well the evidence context matches the target context for this "
        "dimension.\n\n"
        "Consider:\n"
        "- For geography: socioeconomic development level, healthcare system similarity, "
        "cultural context\n"
        "- For population: age group overlap, demographic similarity, vulnerability factors\n"
        "- For setting: delivery environment similarity, institutional context\n\n"
        "Respond with JSON:\n"
        '{"match_level": "Match|Partial|Mismatch", "explanation": "One sentence reason"}'
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
        return ("Unknown", "LLM assessment failed")


async def compute_transferability(
    doc_uuids: List[str],
    intervention_extractions: List[Dict],
    target_inner_setting: List[str],
    target_population: List[str],
    target_geography: List[str],
    doc_scores: Dict[str, Dict],
    llm,
) -> Tuple[str, str, TransferabilityBreakdown]:
    """Compute transferability across five dimensions.

    Args:
        doc_uuids: Document UUIDs associated with the intervention.
        intervention_extractions: Raw intervention extractions.
        target_inner_setting: Target inner setting values.
        target_population: Target population values.
        target_geography: Target geography values.
        doc_scores: Document score metadata.
        llm: LLM client to use for semantic similarity.

    Returns:
        Tuple[str, str, TransferabilityBreakdown]: Rating, note, and breakdown.
    """
    breakdown = TransferabilityBreakdown(
        inner_setting="Unknown",
        population="Unknown",
        geography="Unknown",
        resource_intensity="Unknown",
        delivery_complexity="Unknown",
        notes={},
    )

    relevant_extractions = [
        e for e in intervention_extractions if e.get("doc_uuid") in doc_uuids
    ]
    if not relevant_extractions:
        return ("Unknown", "No intervention data available", breakdown)

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
    breakdown.resource_intensity = resolve_level_dimension(
        DEFAULT_USER_CONSTRAINTS["resource_intensity"],
        [e.get("resource_intensity") for e in relevant_extractions],
    )
    breakdown.delivery_complexity = resolve_level_dimension(
        DEFAULT_USER_CONSTRAINTS["delivery_complexity"],
        [e.get("delivery_complexity") for e in relevant_extractions],
    )

    dimension_scores = [
        breakdown.inner_setting,
        breakdown.population,
        breakdown.geography,
        breakdown.resource_intensity,
        breakdown.delivery_complexity,
    ]
    match_count = sum(1 for s in dimension_scores if s == "Match")
    partial_count = sum(1 for s in dimension_scores if s == "Partial")
    mismatch_count = sum(1 for s in dimension_scores if s == "Mismatch")
    unknown_count = sum(1 for s in dimension_scores if s == "Unknown")

    if mismatch_count > 0:
        rating = "Low Fit"
        note = "Context mismatch identified in one or more dimensions"
    elif unknown_count >= 3:
        rating = "Unknown"
        note = "Insufficient implementation data for transferability assessment"
    elif match_count >= 2 and unknown_count <= 1:
        rating = "High Fit"
        note = "Good alignment with target context"
    elif match_count >= 1 or partial_count >= 2:
        rating = "Medium Fit"
        note = "Partial alignment with target context"
    else:
        rating = "Low Fit"
        note = "Limited alignment with target context"

    return (rating, note, breakdown)


def compute_causal_mechanism(
    source_doc_ids: List[str],
    result_extractions: List[Dict],
    doc_scores: Dict[str, Dict],
    doc_uuid_by_doc_id: Dict[str, str],
) -> Tuple[Optional[CausalityClaimType], Optional[str]]:
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
    detail = "Weighted support: " + ", ".join(
        f"{claim}={score}" for claim, score in sorted(weights.items())
    )
    return (primary, detail)


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


def link_risk_to_intervention(
    risk_doc_uuids: set[str],
    interventions: List[PolicyIntervention],
    theme_to_doc_uuids: Dict[str, List[str]],
) -> Optional[str]:
    """Link risk theme to intervention via document overlap."""
    if not risk_doc_uuids:
        return None
    best_name = None
    best_overlap = 0
    for intervention in interventions:
        uuids = set(theme_to_doc_uuids.get(intervention.intervention_name, []))
        overlap = len(risk_doc_uuids.intersection(uuids))
        if overlap > best_overlap:
            best_overlap = overlap
            best_name = intervention.intervention_name
    return best_name


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
    if verdict == "high_confidence_positive":
        return "Evidence strongly supports a positive impact."
    if verdict == "high_confidence_negative":
        return "Evidence strongly supports a negative impact."
    if verdict == "contested":
        return "Evidence is split between positive and negative findings."
    if verdict == "ineffective":
        return "Evidence suggests no consistent effect."
    if verdict == "lean_positive":
        return "Evidence trends positive but is not definitive."
    if verdict == "lean_negative":
        return "Evidence trends negative but is not definitive."
    if verdict == "probable_contribution":
        return "Evidence suggests contribution but lacks strong attribution."
    return "Insufficient evidence to determine impact."
