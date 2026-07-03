"""Offline tests for Arm B's pure result-shaping (Phase 7).

Arm B is mostly wiring of already-tested pieces — the loop itself is covered by test_broad_search
(over FakeSource), the fanout by test_fanout, the OpenAlex mappers by test_openalex_client, and the
full live path by smoke/phase7_arm_b.py. The one genuinely new pure unit here is `_ranked_records`
(final ranked candidates → the persisted {paper_id, rank, level} rows)."""

from __future__ import annotations

from arms.arm_b import _ranked_records
from core.source import Candidate


def test_ranked_records_assigns_ranks_and_carries_level_plus_blend_features():
    # Blend features (rerank_score/num_snippets/year/cited_by_count) are persisted for the §4.7 sweep.
    cands = [
        Candidate(
            paper_id="a",
            title="A",
            level=3,
            rerank_score=0.9,
            num_snippets=4,
            year=2020,
            cited_by_count=50,
        ),
        Candidate(
            paper_id="b", title="B", level=None
        ),  # unjudged → null; features at defaults
    ]
    assert _ranked_records(cands) == [
        {
            "paper_id": "a",
            "rank": 0,
            "level": 3,
            "rerank_score": 0.9,
            "num_snippets": 4,
            "year": 2020,
            "cited_by_count": 50,
        },
        {
            "paper_id": "b",
            "rank": 1,
            "level": None,
            "rerank_score": 0.0,
            "num_snippets": 0,
            "year": None,
            "cited_by_count": 0,
        },
    ]


def test_ranked_records_empty():
    assert _ranked_records([]) == []
