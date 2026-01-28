"""Scoring utilities for Policy Atlas impact and intervention scoring."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


IMPACT_SCORE_WEIGHTS = {
    "q": 0.4,
    "t": 0.3,
    "m": 0.2,
    "r": 0.1,
}


def get_impact_score_weights() -> Dict[str, float]:
    """Return constant weights for impact scoring."""
    return dict(IMPACT_SCORE_WEIGHTS)


def compute_magnitude_adjustment(magnitude_estimate: Optional[str]) -> float:
    magnitude_values = {
        "transformational": 0.5,
        "substantial": 0.3,
        "moderate": 0.15,
        "marginal": 0.05,
        "unknown": 0.1,
    }
    return magnitude_values.get((magnitude_estimate or "unknown").lower(), 0.1)


def compute_harm_multiplier(
    has_negative_impact: bool,
    risks_identified: Optional[List[str]] = None,
) -> float:
    risks_identified = risks_identified or []
    if has_negative_impact:
        return 0.5
    if len(risks_identified) > 2:
        return 0.8
    if len(risks_identified) > 0:
        return 0.9
    return 1.0


def compute_document_impact_score(
    evidence_strength: Optional[int],
    transferability_score: Optional[float],
    magnitude_adjustment: float,
    harm_multiplier: float,
) -> Tuple[int, str, Dict[str, object]]:
    """Compute document impact score using weighted multiplicative formula."""
    weights = get_impact_score_weights()
    q_val = evidence_strength if evidence_strength is not None else 1
    t_val = transferability_score if transferability_score is not None else 0.5
    t_val = max(0.2, min(1.0, t_val))
    m_val = max(0.0, min(0.5, magnitude_adjustment))
    r_val = max(0.5, min(1.0, harm_multiplier))

    raw = (
        (q_val ** weights["q"])
        * (t_val ** weights["t"])
        * ((1 + m_val) ** weights["m"])
        * (r_val ** weights["r"])
    )

    # Scale to 1-5 range based on theoretical min/max for current weights.
    # Q in [1,5], T in [0.2,1.0], M in [0,0.5], R in [0.5,1.0]
    min_raw = (
        (1 ** weights["q"])
        * (0.2 ** weights["t"])
        * (1.0 ** weights["m"])
        * (0.5 ** weights["r"])
    )
    max_raw = (
        (5 ** weights["q"])
        * (1.0 ** weights["t"])
        * (1.5 ** weights["m"])
        * (1.0 ** weights["r"])
    )
    if max_raw <= min_raw:
        scaled = 1.0
    else:
        scaled = 1 + (raw - min_raw) * (4.0 / (max_raw - min_raw))
    final_score = max(1, min(5, round(scaled)))

    labels = {5: "High Impact", 4: "Good Impact", 3: "Moderate", 2: "Limited", 1: "Low"}

    return (
        final_score,
        labels[final_score],
        {
            "evidence_strength": q_val,
            "transferability": round(t_val, 2),
            "magnitude_adjustment": round(m_val, 2),
            "harm_multiplier": round(r_val, 2),
            "raw_score": round(raw, 3),
            "min_raw": round(min_raw, 3),
            "max_raw": round(max_raw, 3),
            "weights": weights,
        },
    )


def compute_intervention_impact_score(
    document_scores: List[Tuple[int, Dict[str, object], str]],
    risk_themes: List[Dict[str, object]],
) -> Tuple[int, str, Dict[str, object]]:
    """Compute intervention impact score with effect-direction separation."""
    doc_count = len(document_scores)
    if doc_count == 1:
        return (2, "Single Source", {"doc_count": 1})

    pos_sum = neg_sum = null_sum = 0.0
    pos_weight = neg_weight = null_weight = 0.0

    for score, breakdown, direction in document_scores:
        weight = breakdown.get("evidence_strength", 1) or 1
        weighted = score * weight
        if direction in ("positive", "increase"):
            pos_sum += weighted
            pos_weight += weight
        elif direction in ("negative", "decrease"):
            neg_sum += weighted
            neg_weight += weight
        else:
            null_sum += weighted
            null_weight += weight

    effective_weight = pos_weight + neg_weight + (null_weight * 0.5)
    if effective_weight == 0:
        return (2, "No Evidence", {"doc_count": doc_count})

    net_impact = (pos_sum - neg_sum - (null_sum * 0.5)) / effective_weight

    if effective_weight >= 15:
        conf_mult = 1.15
    elif effective_weight < 5:
        conf_mult = 0.85
    else:
        conf_mult = 1.0

    is_contested = (
        pos_weight > 3
        and neg_weight > 3
        and min(pos_weight, neg_weight) / max(pos_weight, neg_weight) > 0.4
    )
    discord_penalty = 0.5 if is_contested else 0.0

    harm_count = sum(1 for r in risk_themes if r.get("has_harm_warning"))
    harm_penalty = harm_count * 0.25

    base = 3 + (net_impact * 0.4)
    final_raw = (base * conf_mult) - discord_penalty - harm_penalty
    final_score = max(1, min(5, round(final_raw)))

    labels = {
        5: "High Potential",
        4: "Promising",
        3: "Moderate",
        2: "Limited",
        1: "Low/Risky",
    }

    return (
        final_score,
        labels[final_score],
        {
            "doc_count": doc_count,
            "positive_evidence": round(pos_weight, 1),
            "negative_evidence": round(neg_weight, 1),
            "null_evidence": round(null_weight, 1),
            "net_impact": round(net_impact, 2),
            "confidence": "High"
            if conf_mult > 1
            else ("Low" if conf_mult < 1 else "Moderate"),
            "discord_detected": is_contested,
            "harm_warnings": harm_count,
        },
    )
