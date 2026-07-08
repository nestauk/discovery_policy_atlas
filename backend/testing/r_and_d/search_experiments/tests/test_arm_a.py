"""Offline tests for Arm A's pure retrieval logic (Phase 6).

The network pieces (boolean generation, OpenAlex search, judging) are exercised live in
smoke/phase6_arm_a.py. Here we pin the two pure functions that decide Arm A's candidate set and
ordering: the SR/RCT fanout expansion and the production-faithful sort+dedup (relevance_score desc,
variant_priority asc, dedup keep-first on paper_id). These import clean — ArmA lazy-imports app.*
inside __init__, so the module-level helpers pull no backend env.
"""

from __future__ import annotations

from arms.arm_a import _dedupe_and_sort

# Same priority map production uses (systematic_review wins ties, then rct, then base).
VP = {"systematic_review": 0, "rct": 1, "base": 2}


# --------------------------------------------------------------------------- #
# _dedupe_and_sort   (the fanout helper itself is covered by tests/test_fanout.py)
# --------------------------------------------------------------------------- #
def test_dedupe_and_sort_orders_by_relevance_then_variant_and_keeps_best_copy():
    rows = [
        {"id": "1", "relevance_score": 0.9, "variant": "base"},
        {"id": "2", "relevance_score": 0.5, "variant": "base"},
        {
            "id": "1",
            "relevance_score": 0.5,
            "variant": "systematic_review",
        },  # dup of 1, lower rel
        {"id": "3", "relevance_score": 0.5, "variant": "systematic_review"},
        {
            "id": "2",
            "relevance_score": 0.5,
            "variant": "systematic_review",
        },  # dup of 2, tie on rel
    ]
    out = _dedupe_and_sort(rows, VP)

    # relevance dominates (id 1 first); among the 0.5 ties, SR (priority 0) beats base (priority 2).
    assert [r["id"] for r in out] == ["1", "3", "2"]
    # id 1's surviving copy is the higher-relevance base one (relevance beats variant priority)...
    assert next(r for r in out if r["id"] == "1")["variant"] == "base"
    # ...but id 2 tied on relevance, so the SR-tagged copy wins the tie-break.
    assert next(r for r in out if r["id"] == "2")["variant"] == "systematic_review"


def test_dedupe_and_sort_skips_blank_ids():
    rows = [
        {"id": "", "relevance_score": 1.0, "variant": "base"},
        {"id": "x", "relevance_score": 0.1, "variant": "base"},
    ]
    assert [r["id"] for r in _dedupe_and_sort(rows, VP)] == ["x"]


def test_dedupe_and_sort_handles_missing_relevance_as_zero():
    rows = [
        {"id": "a", "variant": "base"},  # no relevance_score -> treated as 0
        {"id": "b", "relevance_score": 0.2, "variant": "base"},
    ]
    assert [r["id"] for r in _dedupe_and_sort(rows, VP)] == ["b", "a"]
