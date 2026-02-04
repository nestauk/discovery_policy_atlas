"""Scoring utilities for Policy Atlas impact and intervention scoring."""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Tuple, Union

from .schemas_langchain import ResultItem

MATCH_SCORES = {
    "match": 1.0,
    "similar": 0.85,
    "comparable": 0.7,
    "partial": 0.4,
    "mismatch": 0.15,
    "unknown": 0.5,
}

MAGNITUDE_NORMALISED = {
    "substantial": 1.0,
    "large": 0.75,
    "moderate": 0.5,
    "marginal": 0.25,
    "unknown": 0.25,
    "transformational": 1.0,
}

CAUSAL_WEIGHTS = {
    "attribution": 1.0,
    "contribution": 0.9,
    "correlation": 0.7,
    # Missing/unknown should be neutral-ish (do not punish missingness heavily).
    None: 0.9,
}


def _normalise_causality_claim(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip().lower()
        if not raw or raw == "null" or raw == "none":
            return None
        if raw in ("attribution", "contribution", "correlation"):
            return raw
        return None
    return _normalise_causality_claim(str(value))


def _causal_weight(value: object) -> float:
    claim = _normalise_causality_claim(value)
    return float(CAUSAL_WEIGHTS.get(claim, 0.9))


def _normalise_requirement_level(value: object) -> Optional[str]:
    """Normalise an extracted implementation requirement level.

    The extraction sometimes returns:
    - actual nulls
    - the string "null"
    - a pipe-delimited string like "Moderate|null"
    - a list of any of the above (when aggregating across interventions)

    Args:
        value (object): Raw requirement level.

    Returns:
        Optional[str]: One of {"low", "moderate", "high"} or None if unavailable.
    """
    if value is None:
        return None

    if isinstance(value, list):
        levels = [_normalise_requirement_level(item) for item in value]
        levels = [level for level in levels if level]
        if not levels:
            return None
        level_order = {"low": 1, "moderate": 2, "high": 3}
        return max(levels, key=lambda level: level_order.get(level, 0))

    if isinstance(value, str):
        raw = value.strip().lower()
        if not raw or raw == "null":
            return None
        tokens = [token.strip() for token in raw.split("|") if token.strip()]
        for token in tokens:
            if token in ("low", "moderate", "high"):
                return token
        return None

    return _normalise_requirement_level(str(value))


def compute_signed_magnitude(outcome: ResultItem) -> float:
    """Return signed magnitude in the range -1.0 to +1.0.

    Args:
        outcome (ResultItem): Extracted outcome with direction and benefit flags.

    Returns:
        float: Signed magnitude (beneficial positive, harmful negative, null zero).
    """
    if outcome.effect_direction in ("null", "mixed", "inconclusive"):
        return 0.0

    magnitude_key = getattr(outcome, "magnitude_estimate", None) or "unknown"
    magnitude = MAGNITUDE_NORMALISED.get(magnitude_key, 0.0)
    return magnitude if outcome.is_beneficial else -magnitude


def compute_harm_warning(
    has_negative_impact: bool,
    risks_identified: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Return harm warning flag and reason.

    Args:
        has_negative_impact (bool): Whether adverse outcomes were found.
        risks_identified (Optional[List[str]]): Extracted list of risks.

    Returns:
        Tuple[bool, Optional[str]]: Harm warning flag and reason.
    """
    risks_identified = risks_identified or []
    if has_negative_impact:
        return (True, "Study found adverse outcomes")
    if len(risks_identified) > 2:
        return (True, f"{len(risks_identified)} risks identified")
    return (False, None)


async def assess_dimension(
    dimension_name: str,
    target_value: Optional[Union[str, List[str]]],
    evidence_value: Optional[Union[str, List[str]]],
    llm,
) -> str:
    """Assess similarity for a transferability dimension.

    Args:
        dimension_name (str): Dimension being assessed (e.g., geography).
        target_value (Optional[Union[str, List[str]]]): Target context values from the user.
        evidence_value (Optional[str]): Evidence context value from extraction.
        llm (Any): LLM client with async invoke.

    Returns:
        str: Match level in {match, similar, comparable, partial, mismatch, unknown}.
    """
    if not evidence_value or not target_value:
        return "unknown"

    if isinstance(target_value, list):
        targets = [value for value in target_value if value]
        if not targets:
            return "unknown"
    else:
        targets = [target_value]

    if isinstance(evidence_value, list):
        evidence_values = [value for value in evidence_value if value]
        if not evidence_values:
            return "unknown"
    else:
        evidence_values = [evidence_value]

    evidence_norms = [str(value).strip().lower() for value in evidence_values]
    for target in targets:
        target_norm = str(target).strip().lower()
        if target_norm in evidence_norms:
            return "match"

    target_text = "; ".join(str(value) for value in targets)
    evidence_text = "; ".join(str(value) for value in evidence_values)

    geography_guidance = ""
    if dimension_name.strip().lower() in (
        "geography",
        "country",
        "location",
        "jurisdiction",
    ):
        geography_guidance = (
            "\nGeography guidance:\n"
            "- Do NOT require the same country to avoid mismatch. Treat geography as macro-context comparability.\n"
            "- Reserve mismatch for clearly non-comparable macro-contexts (e.g., substantially different levels of\n"
            "  economic development, governance capacity, or health system maturity), not simply because it is a different country.\n"
            "- If uncertain between partial and mismatch, prefer partial.\n"
            "\nCalibration examples (target is UK):\n"
            "- Evidence='Germany' -> similar or comparable (NOT mismatch)\n"
            "- Evidence='New Zealand' -> comparable (NOT mismatch)\n"
            "- Evidence='EU Member States' -> comparable or partial (NOT mismatch)\n"
            "- Evidence='Italy' -> comparable or partial (NOT match)\n"
        )

    prompt = (
        "You are assessing transferability of research evidence to a target context.\n\n"
        f"Dimension: {dimension_name}\n"
        f"Target options: {target_text}\n"
        f"Evidence options: {evidence_text}\n\n"
        "Select the best achievable match level against ANY of the target options.\n"
        "Evidence may include multiple contexts; choose the BEST match level across evidence options (best-case),\n"
        "and only return mismatch if NONE of the evidence options has meaningful overlap with ANY target option.\n"
        "Match levels:\n"
        "- match: direct match\n"
        "- similar: highly similar\n"
        "- comparable: comparable context\n"
        "- partial: some overlap\n"
        "- mismatch: no meaningful overlap\n\n"
        f"{geography_guidance}\n"
        "Respond with JSON only:\n"
        '{"match_level": "match|similar|comparable|partial|mismatch|unknown"}'
    )

    try:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", None) or str(response)
        data = json.loads(content.strip())
        match_level = str(data.get("match_level", "unknown")).strip().lower()
        return match_level if match_level in MATCH_SCORES else "unknown"
    except Exception:
        return "unknown"


async def compute_document_transferability(
    doc_context: Dict,
    target_context: Dict,
    implementation_evidence: Dict,
    user_constraints: Optional[Dict],
    llm,
) -> Tuple[float, Dict[str, object]]:
    """Compute document transferability with constraint veto.

    Args:
        doc_context (Dict): Document context (country, inner_setting, population_intervened).
        target_context (Dict): User target context (geography, population, setting).
        implementation_evidence (Dict): Evidence for implementation requirements.
        user_constraints (Optional[Dict]): User tolerance limits for cost, staffing, complexity.
        llm (Any): LLM client with async invoke.

    Returns:
        Tuple[float, Dict[str, object]]: Transferability score and breakdown.
    """
    geo_match, pop_match, set_match = await asyncio.gather(
        assess_dimension(
            "geography",
            target_context.get("geography"),
            doc_context.get("country"),
            llm,
        ),
        assess_dimension(
            "population",
            target_context.get("population"),
            doc_context.get("population_intervened"),
            llm,
        ),
        assess_dimension(
            "inner_setting",
            target_context.get("setting"),
            doc_context.get("inner_setting"),
            llm,
        ),
    )

    matches = [
        ("geography", geo_match),
        ("population", pop_match),
        ("inner_setting", set_match),
    ]
    scores = [
        MATCH_SCORES.get(match_level)
        for _, match_level in matches
        if match_level != "unknown"
    ]
    valid = [score for score in scores if score is not None]
    context_fit = sum(valid) / len(valid) if valid else 0.5

    constraint_penalty = 1.0
    exceeds: Dict[str, object] = {}
    constraint_levels: Dict[str, Optional[str]] = {}
    evidence_levels: Dict[str, Optional[str]] = {}
    level_order = {"low": 1, "moderate": 2, "high": 3}
    for dim in ["cost", "staffing", "implementation_complexity"]:
        tolerance = (
            _normalise_requirement_level(user_constraints.get(dim))
            if user_constraints
            else None
        )
        evidence = _normalise_requirement_level(
            implementation_evidence.get(f"{dim}_level")
        )
        constraint_levels[dim] = tolerance
        evidence_levels[dim] = evidence
        if tolerance and evidence:
            if level_order.get(evidence, 0) > level_order.get(tolerance, 3):
                exceeds[dim] = True
                constraint_penalty *= 0.5

    transferability = max(0.2, min(1.0, context_fit * constraint_penalty))

    return (
        transferability,
        {
            "context_fit": round(context_fit, 2),
            "geography": geo_match,
            "population": pop_match,
            "inner_setting": set_match,
            "constraints_provided": bool(user_constraints),
            "constraint_levels": constraint_levels if user_constraints else {},
            "implementation_evidence": evidence_levels,
            "extracted_context": {
                "countries": doc_context.get("country"),
                "populations": doc_context.get("population_intervened"),
                "settings": doc_context.get("inner_setting"),
            },
            "exceeds_constraints": exceeds,
        },
    )


async def compute_outcome_similarity(
    outcome_variable: str,
    target_outcomes: List[str],
    llm,
) -> Tuple[float, str]:
    """Compute similarity between outcome and user's targets.

    Args:
        outcome_variable (str): Outcome label from extraction.
        target_outcomes (List[str]): User-specified target outcomes.
        llm (Any): LLM client with async invoke.

    Returns:
        Tuple[float, str]: Similarity score (0.0-1.0) and reasoning string.
    """
    prompt = f"""Rate how relevant this study outcome is to the user's target outcomes.

Study outcome: "{outcome_variable}"
User targets: {', '.join(f'"{target}"' for target in target_outcomes)}

Scoring guide:
- 1.0 = Directly measures the target outcome (exact match or validated measure of it)
- 0.7 = Established proxy measure that directly quantifies the same construct
- 0.4 = Contributing factor or intermediate outcome that influences but does not directly measure the target
- 0.1 = Same broad domain but weak or indirect relationship
- 0.0 = Unrelated

Important distinction:
- A PROXY directly measures the same underlying construct as the target (0.7)
- A CONTRIBUTING FACTOR causes or influences the target but measures something different (0.4)

Examples:
- "test scores" is a proxy for "academic achievement" (0.7) - same construct
- "study time" is a contributing factor to "academic achievement" (0.4) - different measure
- "employee satisfaction" is a proxy for "workforce morale" (0.7) - same construct
- "training hours" is a contributing factor to "workforce productivity" (0.4) - different measure

Respond in JSON only:
{{"score": <number>, "reason": "<brief explanation>"}}
"""
    try:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", None) or str(response)
        data = json.loads(content.strip())
        score = float(data.get("score", 0.0))
        reason = str(data.get("reason", "")).strip()
        return (max(0.0, min(1.0, score)), reason)
    except Exception:
        return (0.0, "Similarity assessment failed")


async def compute_document_impact_score(
    outcomes: List[ResultItem],
    target_outcomes: Optional[List[str]],
    transferability: float,
    llm,
) -> Tuple[Optional[float], str, Dict[str, object]]:
    """Compute document impact score using signed magnitude and similarity weighting.

    Args:
        outcomes (List[ResultItem]): Extracted outcomes for the document.
        target_outcomes (Optional[List[str]]): User-selected target outcomes.
        transferability (float): Transferability score (0.2 to 1.0).
        llm (Any): LLM client with async invoke.

    Returns:
        Tuple[Optional[float], str, Dict[str, object]]: Score, label, and breakdown.
    """
    if not outcomes:
        return (None, "N/A", {"note": "no extractable outcomes"})

    primary = [outcome for outcome in outcomes if outcome.is_primary]
    if not primary:
        return (
            None,
            "N/A",
            {
                "note": "no primary outcomes extracted",
                "outcomes_available": len(outcomes),
            },
        )

    selected = primary

    weighted_sum = 0.0
    weight_sum = 0.0
    similarity_sum = 0.0
    included_count = 0
    breakdown: List[Dict[str, object]] = []

    for outcome in selected:
        signed_magnitude = compute_signed_magnitude(outcome)
        magnitude_estimate = getattr(outcome, "magnitude_estimate", None)
        causal_w = _causal_weight(getattr(outcome, "causality_claim", None))

        if target_outcomes:
            similarity, _reason = await compute_outcome_similarity(
                outcome.outcome_variable, target_outcomes, llm
            )
        else:
            similarity = 1.0

        included = True
        excluded_reason = None
        if target_outcomes and similarity < 0.5:
            included = False
            excluded_reason = "low similarity"
        combined_weight = similarity * causal_w
        contribution = signed_magnitude * combined_weight
        if included:
            weighted_sum += contribution
            weight_sum += combined_weight
            similarity_sum += similarity
            included_count += 1

        breakdown.append(
            {
                "outcome": outcome.outcome_variable,
                "is_primary": outcome.is_primary,
                "is_beneficial": outcome.is_beneficial,
                "magnitude": magnitude_estimate,
                "signed_magnitude": round(signed_magnitude, 2),
                "similarity": round(similarity, 2),
                "causality_claim": getattr(outcome, "causality_claim", None),
                "causal_weight": round(causal_w, 2),
                "combined_weight": round(combined_weight, 3),
                "contribution": round(contribution, 3),
                "included_in_score": included,
                "excluded_reason": excluded_reason,
            }
        )

    if included_count == 0:
        return (
            1.0,
            "No relevant outcomes",
            {
                "note": "no outcomes matched target similarity or had usable magnitude",
                "outcomes_available": len(selected),
                "outcomes_used": 0,
                "primary_only": bool(primary),
                "outcome_breakdown": breakdown,
            },
        )

    net_magnitude = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    avg_causal_weight = (
        (weight_sum / similarity_sum)
        if similarity_sum > 0
        else CAUSAL_WEIGHTS.get(None, 0.9)
    )
    base_score = 2.5 + (net_magnitude * 2.5)
    dampened = base_score * (max(0.2, min(1.0, transferability)) ** 0.3)
    final_score = round(max(1.0, min(5.0, dampened)), 1)

    if final_score >= 4.5:
        label = "High"
    elif final_score >= 3.5:
        label = "Good"
    elif final_score >= 2.5:
        label = "Moderate"
    elif final_score >= 1.5:
        label = "Limited"
    else:
        label = "Low"

    return (
        final_score,
        label,
        {
            "outcomes_used": len(selected),
            "primary_only": bool(primary),
            "net_magnitude": round(net_magnitude, 3),
            "base_score": round(base_score, 2),
            "transferability": round(transferability, 2),
            "avg_causal_weight": round(float(avg_causal_weight), 3),
            "outcome_breakdown": breakdown,
        },
    )


def compute_intervention_impact_score(
    document_scores: List[Tuple[float, str, Dict[str, object], float]],
) -> Tuple[float, str, Dict[str, object]]:
    """Aggregate document impact scores into an intervention score.

    Args:
        document_scores (List[Tuple[float, str, Dict[str, object], float]]):
            Document scores with labels, breakdown (including net magnitude),
            and evidence score weight.

    Returns:
        Tuple[float, str, Dict[str, object]]: Score, label, and breakdown.
    """
    excluded_labels = {"No Outcomes", "No relevant outcomes"}
    doc_count = len(document_scores)
    excluded_floor_ones_reasons: Dict[str, int] = {}

    def _is_floor_one(
        score: float, label: str, breakdown: Dict[str, object]
    ) -> Tuple[bool, Optional[str]]:
        if score != 1.0:
            return (False, None)
        if label in excluded_labels:
            return (True, "excluded_label")
        note = str(breakdown.get("note", "")).strip().lower()
        floor_notes = [
            "no extractable outcomes",
            "no primary outcomes",
            "no outcomes matched target similarity",
            "no outcomes matched target",
            "no outcomes matched",
        ]
        if any(phrase in note for phrase in floor_notes):
            return (True, "note_floor")
        outcomes_used = breakdown.get("outcomes_used")
        net_magnitude = breakdown.get("net_magnitude")
        if outcomes_used == 0 and net_magnitude is None:
            return (True, "no_outcomes_used")
        return (False, None)

    filtered: List[Tuple[float, str, Dict[str, object], float]] = []
    for score, label, breakdown, evidence in document_scores:
        if label in excluded_labels:
            excluded_floor_ones_reasons["excluded_label"] = (
                excluded_floor_ones_reasons.get("excluded_label", 0) + 1
            )
            continue
        is_floor, reason = _is_floor_one(score, label, breakdown)
        if is_floor:
            reason_key = reason or "floor_one"
            excluded_floor_ones_reasons[reason_key] = (
                excluded_floor_ones_reasons.get(reason_key, 0) + 1
            )
            continue
        filtered.append((score, label, breakdown, evidence))

    excluded_floor_ones_count = sum(excluded_floor_ones_reasons.values())
    excluded_count = doc_count - len(filtered)
    if not filtered:
        return (
            2.5,
            "Insufficient Evidence",
            {
                "doc_count": doc_count,
                "excluded_count": excluded_count,
                "excluded_floor_ones_count": excluded_floor_ones_count,
                "excluded_floor_ones_reasons": excluded_floor_ones_reasons,
            },
        )

    pos_docs = 0
    neg_docs = 0
    for _, _, breakdown, _ in filtered:
        net_magnitude = float(breakdown.get("net_magnitude", 0.0))
        if net_magnitude > 0.1:
            pos_docs += 1
        elif net_magnitude < -0.1:
            neg_docs += 1
    discord_flag = pos_docs > 0 and neg_docs > 0

    if len(filtered) == 1:
        score, _, _, evidence = filtered[0]
        weighted = score if evidence >= 4 else score * 0.85
        final_score = round(max(1.0, min(5.0, weighted)), 1)
        return (
            final_score,
            "Single Source",
            {
                "doc_count": doc_count,
                "contributing_docs": 1,
                "excluded_count": excluded_count,
                "excluded_floor_ones_count": excluded_floor_ones_count,
                "excluded_floor_ones_reasons": excluded_floor_ones_reasons,
                "evidence_weight_total": float(evidence),
                "discord_flag": discord_flag,
            },
        )

    weighted_sum = 0.0
    weight_total = 0.0
    for score, _, _, evidence in filtered:
        weight = float(evidence) if evidence is not None else 1.0
        weighted_sum += float(score) * weight
        weight_total += weight

    if weight_total == 0:
        return (
            2.5,
            "Insufficient Evidence",
            {
                "doc_count": doc_count,
                "contributing_docs": len(filtered),
                "excluded_count": excluded_count,
                "excluded_floor_ones_count": excluded_floor_ones_count,
                "excluded_floor_ones_reasons": excluded_floor_ones_reasons,
                "discord_flag": discord_flag,
            },
        )

    weighted_avg = weighted_sum / weight_total
    final_score = round(max(1.0, min(5.0, weighted_avg)), 1)

    if final_score >= 4.5:
        label = "High"
    elif final_score >= 3.5:
        label = "Good"
    elif final_score >= 2.5:
        label = "Moderate"
    elif final_score >= 1.5:
        label = "Limited"
    else:
        label = "Low"

    return (
        final_score,
        label,
        {
            "doc_count": doc_count,
            "contributing_docs": len(filtered),
            "excluded_count": excluded_count,
            "excluded_floor_ones_count": excluded_floor_ones_count,
            "excluded_floor_ones_reasons": excluded_floor_ones_reasons,
            "positive_docs": pos_docs,
            "negative_docs": neg_docs,
            "discord_flag": discord_flag,
            "weighted_avg": round(weighted_avg, 3),
            "evidence_weight_total": round(weight_total, 3),
        },
    )
