"""Retrieval metrics — reimplemented from ASTA-bench, parity-tested (spec §4.5–§4.7).

Source of truth = BENCH (`asta-bench/astabench/evals/paper_finder/`):
  - `eval.py`            -> find_dcg, lower_bound_corrected_ndcg, count_relevant,
                            calc_recall_at_k, calc_precision, _calc_any_f, calc_adjusted_f1
  - `relevance.py`       -> calculate_relevance_criteria_score, calculate_0_to_3_relevance
  - `paper_finder_utils.py` -> get_factor (inflation) + k_est

Why reimplement instead of import BENCH? BENCH pulls in inspect-ai + a HF dataset
download for its normalizer reference; we only need ~10 pure functions. So we port
them verbatim (~100 lines) and pin parity with `test_metrics.py` (spec §2 Harness row).

Everything here is a *pure function* — no I/O, no logging. Metrics are called in tight
per-paper / per-query loops, so logging belongs in the orchestration layer (arms/,
collect_results.py) where a single line summarises a whole query, not in here where it
would be per-element noise. REPL usage:

    from metrics import k_est, recall_at_k_est
    k_est(2)  # 6

Two BENCH deviations, both intentional and documented in config.py / the spec:
  1. Inflation is applied to *every* query (§4.6); BENCH gates it on qids starting
     "semantic" (a dataset quirk). We drop that conditional.
  2. We thread thresholds/factors through CONFIG rather than hard-coding them, so the
     frozen operating point lives in one auditable place.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from config import CONFIG

# A judgement set maps paper id (str) -> 0..3 relevance level (int).
Judgements = dict[str, int]

PERFECT = 3  # only Perfect counts toward recall/precision (BENCH count_relevant)


# --------------------------------------------------------------------------- #
# Relevance scoring + 0–3 bucketing (BENCH relevance.py:248–274)
# --------------------------------------------------------------------------- #
def relevance_criteria_score(
    criterion_weights: Sequence[float], criterion_codes: Sequence[int]
) -> float:
    """Weighted, normalised criteria score in [0, 1].

    BENCH `calculate_relevance_criteria_score`: score = Σ weight_i · code_i / 3,
    clamped to 1.0. `criterion_codes` are per-criterion 0–3 labels (Perfectly=3,
    Highly=2, Somewhat=1, Not=0). Weights are expected to sum to ~1 across criteria.
    """
    if len(criterion_weights) != len(criterion_codes):
        raise ValueError(
            f"weights/codes length mismatch: "
            f"{len(criterion_weights)} != {len(criterion_codes)}"
        )
    score = sum(w * code / 3 for w, code in zip(criterion_weights, criterion_codes))
    return min(1.0, score)


def bucket_0_to_3(score: float) -> int:
    """Map a [0,1] weighted score to a 0–3 bucket (BENCH calculate_0_to_3_relevance).

    Thresholds come from CONFIG.judge: <=0.25 ->0, <=0.67 ->1, <=0.99 ->2, else 3.
    """
    t = CONFIG.judge
    if score <= t.not_relevant:  # <= 0.25
        return 0
    if score <= t.somewhat_relevant:  # <= 0.67
        return 1
    if score <= t.highly_relevant:  # <= 0.99
        return 2
    return 3


# --------------------------------------------------------------------------- #
# Pooled-normalizer inflation (BENCH paper_finder_utils.py:154–196, spec §4.6)
# --------------------------------------------------------------------------- #
def inflation_factor(perfect_count: int) -> float:
    """BENCH get_factor: max(min_factor, 2/ln(count)) for count>1, else max_factor.

    The max_factor cap only ever bites at count==1 (where 2/ln(1) is undefined);
    for count>=2 the value is always between the ×2 floor and ×2.885 (at count==2).
    """
    if perfect_count <= 0:
        raise ValueError(f"perfect_count must be > 0, got {perfect_count}")
    inf = CONFIG.inflation
    if perfect_count == 1:
        return float(inf.max_factor)
    return max(float(inf.min_factor), 2 / math.log(perfect_count))


def k_est(perfect_count: int) -> int:
    """Inflated relevant-set estimate: ceil(count × factor). Spec §4.6.

    Worked: 1->10, 2->6, 3->6, 5->10, 10->20, 100->200.
    """
    return math.ceil(perfect_count * inflation_factor(perfect_count))


# --------------------------------------------------------------------------- #
# Recall / precision (BENCH eval.py:88–163)
# --------------------------------------------------------------------------- #
def count_relevant(
    judgements: Judgements, restrict_to: Iterable[str] | None = None
) -> int:
    """Count Perfect (=3) judgements, optionally restricted to a set of ids.

    BENCH count_relevant: Perfect-only numerator for both recall and precision.
    """
    allowed = set(restrict_to) if restrict_to is not None else None
    return sum(
        1
        for pid, level in judgements.items()
        if level == PERFECT and (allowed is None or pid in allowed)
    )


def _judged_in_order(ranked_ids: Sequence[str], judgements: Judgements) -> list[str]:
    """Filter a ranked id list down to those that were judged, preserving rank order.

    BENCH does this BEFORE taking the top-k (eval.py:142–146): unjudged ids — e.g.
    papers the judge failed on — are dropped rather than counted as misses, so the
    caller isn't punished for judge failures.
    """
    return [pid for pid in ranked_ids if pid in judgements]


def recall_at_k_est(
    ranked_ids: Sequence[str], judgements: Judgements, pool_perfect_count: int
) -> float:
    """Headline metric: Perfect papers in the top-k_est judged window ÷ k_est.

    `pool_perfect_count` is the Perfect count over the *pooled normalizer* (§4.6),
    which sets k_est. Denominator is k_est itself (BENCH stores the inflated count as
    `total_relevant`), so recall is capped at 1/factor by construction.
    """
    k = k_est(pool_perfect_count)
    window = _judged_in_order(ranked_ids, judgements)[:k]
    return count_relevant(judgements, restrict_to=window) / k


def precision_at_k(ranked_ids: Sequence[str], judgements: Judgements, k: int) -> float:
    """Perfect papers in the top-k judged window ÷ size of that window. Spec §4.7.

    Mirrors BENCH calc_precision (Perfect ÷ judged), scoped to the top-k judged ids.
    Returns 0.0 on an empty window.
    """
    window = _judged_in_order(ranked_ids, judgements)[:k]
    if not window:
        return 0.0
    return count_relevant(judgements, restrict_to=window) / len(window)


# --------------------------------------------------------------------------- #
# DCG / corrected nDCG / F1 (BENCH eval.py:166–193)
# --------------------------------------------------------------------------- #
def find_dcg(relevances: Sequence[int]) -> float:
    """Discounted cumulative gain with a NATURAL-log discount (BENCH find_dcg).

    score = Σ rel_i / ln(i + 1), i enumerated from 1. NB: natural log, NOT log2 —
    matched verbatim to BENCH so the corrected-nDCG numbers are comparable.
    """
    score = 0.0
    for order, rel in enumerate(relevances, 1):
        score += float(rel) / math.log(order + 1)
    return score


def lower_bound_corrected_ndcg(relevances: Sequence[int]) -> float:
    """(DCG − min_DCG)/(max_DCG − min_DCG); 0.0 when the denominator is 0.

    BENCH lower_bound_corrected_ndcg: min/max DCG come from sorting the same multiset
    ascending / descending. All-equal (or single-element) inputs -> denom 0 -> 0.0.
    """
    rels = list(relevances)
    max_dcg = find_dcg(sorted(rels, reverse=True))
    min_dcg = find_dcg(sorted(rels))
    denom = max_dcg - min_dcg
    if not denom:
        return 0.0
    return (find_dcg(rels) - min_dcg) / denom


def harmonic_mean(values: Sequence[float]) -> float:
    """n / Σ(1/x_i); 0.0 if any value is falsy (BENCH _calc_any_f)."""
    if not all(values):
        return 0.0
    return len(values) / sum(1 / v for v in values)


def adjusted_f1(recall: float, ndcg: float) -> float:
    """Harmonic mean of recall@k_est and corrected nDCG (BENCH calc_adjusted_f1)."""
    return harmonic_mean([recall, ndcg])
