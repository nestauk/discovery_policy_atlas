"""Offline tests for the Phase-9 metrics collation (collect_results.py).

Fixtures stand in for persisted arm results, so the pooling + per-arm scoring logic is pinned
without any live run. (The metric formulas themselves — recall@k_est, k_est, nDCG — are covered by
test_metrics; here we test the cross-arm pooling and the per-arm-against-pool wiring.)
"""

from __future__ import annotations

import json

from reporting.collect_results import (
    arm_query_metrics,
    load_all_arms,
    pooled_judgements,
)


def _rec(query_id, ranked):
    return {
        "query_id": query_id,
        "ranked": [
            {"paper_id": p, "rank": i, "level": lv} for i, (p, lv) in enumerate(ranked)
        ],
    }


# --------------------------------------------------------------------------- #
# pooled_judgements — cross-arm union, max non-null level
# --------------------------------------------------------------------------- #
def test_pooled_judgements_unions_arms_and_takes_max_nonnull_level():
    by_arm = {
        "arm_a": {"q1": _rec("q1", [("p1", 3), ("p2", None), ("p3", 2)])},
        "arm_b": {"q1": _rec("q1", [("p2", 3), ("p4", 0)])},  # p2: a=None, b=3 → 3
        "arm_c": {},  # no result for q1
    }
    pooled = pooled_judgements("q1", by_arm)
    assert pooled == {
        "p1": 3,
        "p2": 3,
        "p3": 2,
        "p4": 0,
    }  # null from arm_a didn't override b's 3


def test_pooled_judgements_empty_when_no_arm_has_query():
    assert pooled_judgements("qX", {"arm_a": {}, "arm_b": {}, "arm_c": {}}) == {}


# --------------------------------------------------------------------------- #
# arm_query_metrics — an arm's ranked list scored against the pooled normalizer
# --------------------------------------------------------------------------- #
def test_arm_query_metrics_against_known_pool():
    # pool: 3 Perfect (p1,p2,p5) → pool_perfect=3 → factor=2 → k_est=6.
    pooled = {"p1": 3, "p2": 3, "p3": 2, "p4": 0, "p5": 3}
    pool_perfect = 3
    # Highly+ (level>=2) pool = p1,p2,p3,p5 = 4 → factor=2 → k_est_highly=8.
    pool_highly = 4
    # arm ranked p1,p4,p2,p6,p3 — p6 is unjudged (not in pool) so it's dropped, not a miss.
    arm_rec = _rec("q1", [("p1", 3), ("p4", 0), ("p2", 3), ("p6", None), ("p3", 2)])
    m = arm_query_metrics(arm_rec, pooled, pool_perfect, pool_highly)

    # judged-in-order window (top k_est=6) = [p1,p4,p2,p3]; Perfects in it = p1,p2 = 2 → recall 2/6.
    assert abs(m["recall_at_k_est"] - 2 / 6) < 1e-9
    assert (
        m["perfect_found"] == 2
    )  # p1, p2 (p5 is Perfect in pool but this arm didn't rank it)
    assert (
        abs(m["precision_at_25"] - 0.5) < 1e-9
    )  # 2 Perfect ÷ 4 judged in the top-25 window
    assert 0.0 < m["ndcg"] <= 1.0
    assert 0.0 <= m["adjusted_f1"] <= 1.0
    # Highly+ parallel metrics: window top-8 = [p1,p4,p2,p3]; level>=2 in it = p1,p2,p3 = 3 → 3/8.
    assert abs(m["recall_at_k_est_highly"] - 3 / 8) < 1e-9
    assert m["highly_found"] == 3  # p1,p2,p3 (level>=2 this arm ranked)


def test_arm_query_metrics_zero_pool_gives_zero_recall():
    pooled = {"p1": 2, "p2": 0}  # no Perfect → pool_perfect 0; Highly+ pool = p1 = 1
    m = arm_query_metrics(
        _rec("q1", [("p1", 2)]), pooled, pool_perfect=0, pool_highly=1
    )
    assert m["recall_at_k_est"] == 0.0 and m["perfect_found"] == 0
    assert m["highly_found"] == 1  # p1 is level 2 → counts at the relaxed bar


# --------------------------------------------------------------------------- #
# load_all_arms — reads results/arms/{arm}/{qid}.json
# --------------------------------------------------------------------------- #
def test_load_all_arms_reads_persisted_files(tmp_path):
    (tmp_path / "arm_a").mkdir()
    (tmp_path / "arm_a" / "q1.json").write_text(json.dumps(_rec("q1", [("p1", 3)])))
    loaded = load_all_arms(tmp_path)
    assert set(loaded) == {"arm_a", "arm_b", "arm_c"}  # all arms keyed, even if empty
    assert loaded["arm_a"]["q1"]["ranked"][0]["paper_id"] == "p1"
    assert loaded["arm_b"] == {} and loaded["arm_c"] == {}
