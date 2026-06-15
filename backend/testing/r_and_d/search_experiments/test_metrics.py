"""Parity tests: our metrics.py vs the ASTA-bench formulas (spec §2 Harness, §3).

These are the contract that lets us claim "ASTA-bench metric formulas reimplemented
(~100 lines) with parity unit tests — no inspect-ai dependency." Each expected value is
hand-computed from the BENCH source (cited inline), not from metrics.py, so a regression
in metrics.py can't silently move the goalposts.

Run:  uv run pytest test_metrics.py -v
"""

from __future__ import annotations

import math

import pytest

from metrics import (
    adjusted_f1,
    bucket_0_to_3,
    count_relevant,
    find_dcg,
    harmonic_mean,
    inflation_factor,
    k_est,
    lower_bound_corrected_ndcg,
    precision_at_k,
    recall_at_k_est,
    relevance_criteria_score,
)


# --------------------------------------------------------------------------- #
# Inflation factor + k_est (BENCH paper_finder_utils.py get_factor, spec §4.6)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "count, expected_k",
    [
        (1, 10),  # count==1 -> max_factor cap (×10)
        (
            2,
            6,
        ),  # 2/ln(2)=2.885 -> ceil(2×2.885)=ceil(5.77)=6  (only case above the ×2 floor)
        (3, 6),  # 2/ln(3)=1.82 -> floored to ×2 -> ceil(6)=6
        (5, 10),  # floored to ×2 -> ceil(10)=10
        (10, 20),  # floored to ×2 -> ceil(20)=20
        (100, 200),  # floored to ×2 -> ceil(200)=200
    ],
)
def test_k_est_worked_examples(count, expected_k):
    assert k_est(count) == expected_k


def test_inflation_factor_count_2():
    # 2/ln(2) = 2 / 0.6931... = 2.8853...
    assert inflation_factor(2) == pytest.approx(2.8853900817779268)


def test_inflation_factor_floor_and_cap():
    assert inflation_factor(1) == 10.0  # max_factor cap
    assert inflation_factor(50) == 2.0  # 2/ln(50)=0.51 -> ×2 floor


def test_inflation_factor_rejects_nonpositive():
    with pytest.raises(ValueError):
        inflation_factor(0)


# --------------------------------------------------------------------------- #
# find_dcg — NATURAL log (BENCH eval.py:166–170)
# --------------------------------------------------------------------------- #
def test_find_dcg_natural_log_fixed_list():
    rels = [3, 0, 2]
    # Hand-computed with natural log: 3/ln(2) + 0/ln(3) + 2/ln(4)
    expected = 3 / math.log(2) + 0 / math.log(3) + 2 / math.log(4)
    assert find_dcg(rels) == pytest.approx(expected)
    # Sanity: a log2 implementation would give a *different* number — guard the regression.
    log2_value = 3 / math.log2(2) + 0 / math.log2(3) + 2 / math.log2(4)
    assert find_dcg(rels) != pytest.approx(log2_value)


# --------------------------------------------------------------------------- #
# lower_bound_corrected_ndcg (BENCH eval.py:173–182)
# --------------------------------------------------------------------------- #
def test_ndcg_perfectly_sorted_desc_is_one():
    assert lower_bound_corrected_ndcg([3, 2, 1, 0]) == pytest.approx(1.0)


def test_ndcg_sorted_asc_is_zero():
    assert lower_bound_corrected_ndcg([0, 1, 2, 3]) == 0.0


def test_ndcg_all_equal_is_zero():
    # max_dcg == min_dcg -> denom 0 -> 0.0 (not a division error)
    assert lower_bound_corrected_ndcg([2, 2, 2]) == 0.0


def test_ndcg_partial_order_between_zero_and_one():
    val = lower_bound_corrected_ndcg([3, 0, 2, 1])
    assert 0.0 < val < 1.0


# --------------------------------------------------------------------------- #
# harmonic_mean / adjusted_f1 (BENCH eval.py:185–193)
# --------------------------------------------------------------------------- #
def test_harmonic_mean_matches_formula():
    r, n = 0.4, 0.6
    expected = 2 / (1 / r + 1 / n)
    assert harmonic_mean([r, n]) == pytest.approx(expected)


def test_harmonic_mean_any_zero_is_zero():
    assert harmonic_mean([0.0, 0.6]) == 0.0
    assert harmonic_mean([0.5, 0.0]) == 0.0


def test_adjusted_f1_is_harmonic_mean_of_recall_ndcg():
    assert adjusted_f1(0.4, 0.6) == pytest.approx(harmonic_mean([0.4, 0.6]))


# --------------------------------------------------------------------------- #
# relevance_criteria_score + bucket_0_to_3 (BENCH relevance.py:248–274)
# --------------------------------------------------------------------------- #
def test_relevance_score_two_equal_criteria_3_and_0():
    # Two equal-weight (0.5) criteria, codes 3 and 0:
    #   score = 0.5*3/3 + 0.5*0/3 = 0.5  -> bucket 1 (<=0.67)
    score = relevance_criteria_score([0.5, 0.5], [3, 0])
    assert score == pytest.approx(0.5)
    assert bucket_0_to_3(score) == 1


def test_relevance_score_clamped_to_one():
    # Weights that would overshoot are clamped to 1.0 -> bucket 3.
    score = relevance_criteria_score([1.0, 1.0], [3, 3])
    assert score == 1.0
    assert bucket_0_to_3(score) == 3


@pytest.mark.parametrize(
    "score, bucket",
    [
        (0.0, 0),
        (0.25, 0),  # boundary: <= 0.25
        (0.26, 1),
        (0.67, 1),  # boundary: <= 0.67
        (0.68, 2),
        (0.99, 2),  # boundary: <= 0.99
        (1.0, 3),
    ],
)
def test_bucket_boundaries(score, bucket):
    assert bucket_0_to_3(score) == bucket


def test_relevance_score_length_mismatch_raises():
    with pytest.raises(ValueError):
        relevance_criteria_score([0.5], [3, 0])


# --------------------------------------------------------------------------- #
# count_relevant — Perfect (=3) ONLY (BENCH eval.py:88–101)
# --------------------------------------------------------------------------- #
def test_count_relevant_counts_only_level_3():
    judgements = {"a": 3, "b": 2, "c": 3, "d": 1, "e": 0}
    assert count_relevant(judgements) == 2  # a, c only


def test_count_relevant_restricted():
    judgements = {"a": 3, "b": 3, "c": 3}
    assert count_relevant(judgements, restrict_to={"a", "b"}) == 2


# --------------------------------------------------------------------------- #
# recall_at_k_est / precision_at_k (BENCH eval.py:117–163, spec §4.6/§4.7)
# --------------------------------------------------------------------------- #
def test_recall_at_k_est_small_ranked_list():
    # "x" is unjudged and must be dropped BEFORE taking the window.
    ranked = ["a", "x", "b", "c"]
    judgements = {"a": 3, "b": 3, "c": 0}
    # pool_perfect_count=1 -> k_est=10. Judged-in-order = [a, b, c]; top-10 = all 3.
    # Perfect in window = {a, b} = 2.  recall = 2 / 10 = 0.2  (denominator is k_est).
    assert recall_at_k_est(ranked, judgements, pool_perfect_count=1) == pytest.approx(
        0.2
    )


def test_recall_at_k_est_window_truncates():
    # 5 judged Perfect papers but k_est=6 (count=3) -> all fit; recall = 3_perfect / 6.
    ranked = ["a", "b", "c", "d", "e"]
    judgements = {"a": 3, "b": 0, "c": 3, "d": 1, "e": 3}
    # pool_perfect_count=3 -> k_est=6. Perfect in top-6 judged = {a, c, e} = 3.
    assert recall_at_k_est(ranked, judgements, pool_perfect_count=3) == pytest.approx(
        3 / 6
    )


def test_precision_at_k_top_window():
    ranked = ["a", "b", "c", "d"]
    judgements = {"a": 3, "b": 0, "c": 3, "d": 3}
    # top-2 judged = [a, b]; Perfect = {a} = 1; precision = 1/2.
    assert precision_at_k(ranked, judgements, k=2) == pytest.approx(0.5)


def test_precision_at_k_empty_window_is_zero():
    assert precision_at_k(["x", "y"], {"a": 3}, k=10) == 0.0
