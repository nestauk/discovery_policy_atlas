"""Offline tests for ranking.py — pure blend, PF sigmoids, direction flips, §4.7 sweep.

No network: cohere_rerank is exercised live in smoke/phase3a_core.py. Here every candidate's
rerank_score is set by hand, so the blend, the PF sigmoid ports, and the sweep are tested in
isolation.
"""

from __future__ import annotations

from config import CONFIG
from query_analysis import QueryAnalysis, QueryIntent
from ranking import (
    central_first_score_sigmoid,
    central_last_score_sigmoid,
    centrality_score,
    content_relevance_score,
    num_snippets_score_sigmoid,
    rank_candidates,
    recency_score,
    recent_first_score_sigmoid,
    rerank_sweep,
    score,
    sigmoid,
)
from source import Candidate, Capabilities

ARM_B = Capabilities()  # no snippets
ARM_C = Capabilities(has_dense=True, has_influential=True, has_snippets=True)


def _analysis(recency=None, centrality=None) -> QueryAnalysis:
    return QueryAnalysis(
        raw_query="q",
        content="q",
        intent=QueryIntent(recency=recency, centrality=centrality),
    )


def _cand(
    pid, *, level=0, rerank=0.0, snippets=0, year=2020, cites=0, rscore=None
) -> Candidate:
    return Candidate(
        paper_id=pid,
        level=level,
        relevance_score=rscore,  # None -> blend falls back to level/3 (preserves older tests)
        rerank_score=rerank,
        num_snippets=snippets,
        year=year,
        cited_by_count=cites,
    )


# --------------------------- sigmoid helpers ------------------------------- #
def test_sigmoid_base():
    assert sigmoid(0.0) == 0.5
    assert sigmoid(0.0, center_shift=0.0, steepness=1.0) == 0.5
    assert sigmoid(100) > 0.99 and sigmoid(-100) < 0.01


def test_num_snippets_score_zero_and_monotonic():
    assert num_snippets_score_sigmoid(0) == 0.0
    assert num_snippets_score_sigmoid(-3) == 0.0
    vals = [num_snippets_score_sigmoid(n) for n in (1, 2, 5, 20, 100)]
    assert vals == sorted(vals)  # monotonically non-decreasing in snippet count
    assert all(0.0 < v <= 1.0 for v in vals)


# --------------------------- content blend --------------------------------- #
def test_content_relevance_score_with_and_without_snippet():
    rj, rerank, snips = 1.0, 1.0, 10
    without = content_relevance_score(rj, rerank, snips, include_snippet=False)
    with_snip = content_relevance_score(rj, rerank, snips, include_snippet=True)
    # Arm B blend: 0.9*1 + 0.075*1, no snippet term.
    assert abs(without - (CONFIG.blend.rj_weight + CONFIG.blend.rerank_weight)) < 1e-9
    # Arm C adds a positive snippet term on top.
    assert with_snip > without
    assert (
        abs(
            (with_snip - without)
            - CONFIG.blend.snippet_weight * num_snippets_score_sigmoid(snips)
        )
        < 1e-9
    )


def test_content_relevance_score_clamps_negatives():
    # PF clamps rj and rerank to >=0 before weighting.
    assert content_relevance_score(-5.0, -5.0, 0, include_snippet=False) == 0.0


def test_snippet_term_inert_when_no_snippets():
    # include_snippet=True but zero snippets -> identical to Arm B (the term is 0).
    a = content_relevance_score(0.5, 0.3, 0, include_snippet=True)
    b = content_relevance_score(0.5, 0.3, 0, include_snippet=False)
    assert a == b


# ----------------------- recency / centrality (PF ports) ------------------- #
def test_recent_first_newest_scores_near_one_not_half():
    # The whole point of porting PF: the newest paper is ~1.0, not the shorthand's 0.5.
    assert recent_first_score_sigmoid(2024, 2024) == 1.0
    assert recent_first_score_sigmoid(2010, 2024) < 0.05  # ~14y old -> near zero


def test_recency_direction_flip():
    new, old, base = 2024, 2010, 2024
    r_new = recency_score(new, base, "recent")
    r_old = recency_score(old, base, "recent")
    e_new = recency_score(new, base, "early")
    e_old = recency_score(old, base, "early")
    assert r_new > r_old  # "recent" favours the newer paper
    assert e_old > e_new  # "early" favours the older paper


def test_recency_unknown_year_is_zero():
    assert recency_score(None, 2024, "recent") == 0.0
    assert recency_score(2020, None, "recent") == 0.0


def test_centrality_centred_at_fifty_cites():
    # PF centres the citation sigmoid at 50 -> exactly 0.5 there.
    assert abs(central_first_score_sigmoid(50) - 0.5) < 1e-9
    assert central_last_score_sigmoid(50) == 1 - central_first_score_sigmoid(50)


def test_centrality_direction_flip():
    hi, lo = 200, 2
    assert centrality_score(hi, "central") > centrality_score(lo, "central")
    assert centrality_score(lo, "less") > centrality_score(hi, "less")


def test_centrality_uncited_edges_match_pf():
    # PF: central_first of an uncited paper is 0.0; central_last is 1.0.
    assert centrality_score(0, "central") == 0.0
    assert centrality_score(0, "less") == 1.0


# ------------------------------ ranking ------------------------------------ #
def test_rank_candidates_orders_by_level_under_just_topic():
    # Hold year/cites constant so recency+centrality are equal across the pool and the
    # judge level (content) decides the order.
    pool = [
        _cand("low", level=0, year=2024, cites=50),
        _cand("perfect", level=3, year=2024, cites=50),
        _cand("mid", level=1, year=2024, cites=50),
    ]
    ranked = rank_candidates(pool, _analysis(), ARM_B)
    assert [c.paper_id for c in ranked] == ["perfect", "mid", "low"]


def test_rank_candidates_respects_final_cap():
    # CONFIG is a frozen dataclass (the instrument is immutable), so we exercise the real cap
    # by overflowing it rather than monkeypatching.
    cap = CONFIG.budgets.final_result_cap
    pool = [_cand(f"W{i}", level=i % 4) for i in range(cap + 10)]
    ranked = rank_candidates(pool, _analysis(), ARM_B)
    assert len(ranked) == cap


def test_score_is_pure_does_not_mutate():
    c = _cand("W1", level=2, rerank=0.4)
    before = c.rerank_score
    _ = score(c, _analysis(), ARM_B, baseline_year=2024)
    assert c.rerank_score == before  # scoring reads, never writes


# ----------------- rj term: continuous score vs level/3 fallback ----------- #
def test_blend_prefers_continuous_relevance_score_over_level():
    # Two papers at the SAME bucketed level (2) but different continuous scores: the higher
    # continuous score must rank first. With level/3 alone they'd tie (PF keeps this granularity).
    pool = [
        _cand("weakly_hi", level=2, rscore=0.70, year=2020, cites=50),
        _cand("strongly_hi", level=2, rscore=0.98, year=2020, cites=50),
    ]
    ranked = rank_candidates(pool, _analysis(), ARM_B)
    assert [c.paper_id for c in ranked] == ["strongly_hi", "weakly_hi"]


def test_blend_falls_back_to_level_over_three_when_score_unset():
    # relevance_score=None -> rj = level/3, so it scores identically to a candidate whose
    # continuous score IS exactly 2/3 (everything else held equal).
    base = _analysis()
    none_cand = _cand("none", level=2, rscore=None, year=2020, cites=50)
    eq_cand = _cand("eq", level=2, rscore=2 / 3, year=2020, cites=50)
    assert (
        abs(score(none_cand, base, ARM_B, 2024) - score(eq_cand, base, ARM_B, 2024))
        < 1e-9
    )


# ------------------------------ §4.7 sweep --------------------------------- #
def _pool():
    return [
        _cand("a", level=3, rerank=0.9, snippets=5, year=2024, cites=200),
        _cand("b", level=2, rerank=0.2, snippets=0, year=2012, cites=3),
        _cand("c", level=1, rerank=0.5, snippets=2, year=2020, cites=40),
    ]


def test_sweep_variant_count_arm_b_vs_arm_c():
    n_weights = len(CONFIG.blend.intent_weights)
    # Arm B: snippet axis pinned off -> weights x {rerank on/off}.
    assert len(rerank_sweep(_pool(), _analysis(), ARM_B)) == n_weights * 2
    # Arm C: snippet axis varies too -> x2 again.
    assert len(rerank_sweep(_pool(), _analysis(), ARM_C)) == n_weights * 2 * 2


def test_sweep_arm_b_never_turns_snippet_on():
    names = rerank_sweep(_pool(), _analysis(), ARM_B).keys()
    assert all("snippet=off" in n for n in names)


def test_sweep_each_variant_is_a_full_permutation_capped():
    pool = _pool()
    ids = {c.paper_id for c in pool}
    for ranked_ids in rerank_sweep(pool, _analysis(), ARM_C).values():
        assert (
            set(ranked_ids) == ids
        )  # every variant ranks the whole pool, none dropped


def test_sweep_rerank_toggle_changes_order():
    # Two candidates equal on every term except the Cohere score. With the high-rerank paper
    # placed SECOND, "rerank=on" must lift it to the front; "rerank=off" removes the only
    # differentiator, so the scores tie and stable-sort keeps the original (low-first) order.
    pool = [
        _cand("lo_rerank", level=1, rerank=0.01, year=2020, cites=10),
        _cand("hi_rerank", level=1, rerank=0.99, year=2020, cites=10),
    ]
    sweep = rerank_sweep(pool, _analysis(), ARM_B)
    assert sweep["just_topic|rerank=on|snippet=off"][0] == "hi_rerank"
    assert sweep["just_topic|rerank=off|snippet=off"][0] == "lo_rerank"
