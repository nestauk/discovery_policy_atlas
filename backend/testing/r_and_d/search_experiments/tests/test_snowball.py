"""Offline tests for snowball.py — the PF edge-sum scoring + top-k promotion.

Asserts the faithful behaviours: co-citation summation over edges, direction-specific count
field + penalty, Arm-C-only influence term, and stable top-k promotion.
"""

from __future__ import annotations

from config import CONFIG
from core.snowball import (
    SnowballEdge,
    build_edges,
    promote_snowball,
    score_snowball_candidate,
)
from core.source import Candidate, Capabilities

ARM_B = Capabilities()  # no influence signal
ARM_C = Capabilities(has_dense=True, has_influential=True, has_snippets=True)


def _edge(cand: Candidate, rel: float, infl: bool = False) -> SnowballEdge:
    return SnowballEdge(candidate=cand, seed_relevance=rel, is_influential=infl)


# ------------------------------- build_edges ------------------------------- #
# Seeds carry the RAW 0-3 level as seed_relevance (PF-faithful, snowball.py) — not level/3.
def test_build_edges_carries_raw_level_and_influence():
    seed = Candidate(paper_id="S")
    seed.level = 2  # Highly -> seed_relevance 2.0 (raw level, NOT 2/3)
    reached = [Candidate(paper_id="X", is_influential=True), Candidate(paper_id="Y")]
    edges = build_edges(seed, reached)
    assert all(e.seed_relevance == 2.0 for e in edges)
    assert edges[0].is_influential is True and edges[1].is_influential is False


# --------------------------- forward / backward ---------------------------- #
# Example seed_relevance values are raw levels: Perfect=3.0, Highly=2.0 (the only realisable
# seed values, since seeds are level >= 2). The scoring formula is linear in seed_relevance.
def test_forward_score_arm_c_matches_hand_calc():
    x = Candidate(paper_id="X", reference_count=40)
    edges = [
        _edge(x, 3.0, infl=True),  # Perfect seed, influential citation
        _edge(x, 2.0, infl=False),  # Highly seed
        _edge(x, 3.0, infl=False),  # Perfect seed
    ]
    # count = max(40, 3) = 40; per-edge penalty = -0.005*40 = -0.2; influence 0.1 (Arm C)
    # (3.0+0.1-0.2) + (2.0-0.2) + (3.0-0.2) = 2.9 + 1.8 + 2.8 = 7.5
    assert abs(score_snowball_candidate(edges, "forward", ARM_C) - 7.5) < 1e-9


def test_forward_arm_b_drops_influence_term():
    x = Candidate(paper_id="X", reference_count=40)
    edges = [_edge(x, 3.0, infl=True), _edge(x, 2.0), _edge(x, 3.0)]
    # Arm B: no +0.1 influence -> 2.8 + 1.8 + 2.8 = 7.4
    assert abs(score_snowball_candidate(edges, "forward", ARM_B) - 7.4) < 1e-9


def test_backward_uses_citation_count_and_smaller_penalty():
    y = Candidate(paper_id="Y", cited_by_count=100)
    edges = [_edge(y, 3.0), _edge(y, 3.0)]
    # count = max(100, 2) = 100; penalty = -0.0005*100 = -0.05; no influence backward
    # (3.0-0.05) * 2 = 5.9
    assert abs(score_snowball_candidate(edges, "backward", ARM_C) - 5.9) < 1e-9


def test_count_field_is_direction_specific():
    # forward penalises by reference_count, backward by cited_by_count — same paper, both set.
    c = Candidate(paper_id="C", reference_count=200, cited_by_count=2)
    e = [_edge(c, 3.0)]
    fwd = score_snowball_candidate(
        e, "forward", ARM_C
    )  # max(200,1)=200 -> -0.005*200=-1.0
    bwd = score_snowball_candidate(
        e, "backward", ARM_C
    )  # max(2,1)=2 -> -0.0005*2=-0.001
    assert abs(fwd - (3.0 - 1.0)) < 1e-9
    assert abs(bwd - (3.0 - 0.001)) < 1e-9


def test_cocitation_sum_beats_single_edge():
    # The whole point: a paper reached from 3 relevant seeds outscores one reached from 1.
    x = Candidate(paper_id="X", reference_count=10)
    y = Candidate(paper_id="Y", reference_count=10)
    x_edges = [_edge(x, 3.0), _edge(x, 3.0), _edge(x, 3.0)]
    y_edges = [_edge(y, 3.0)]
    assert score_snowball_candidate(
        x_edges, "forward", ARM_C
    ) > score_snowball_candidate(y_edges, "forward", ARM_C)


def test_empty_edges_score_zero():
    assert score_snowball_candidate([], "forward", ARM_C) == 0.0


# ------------------------------ promotion ---------------------------------- #
def test_promote_orders_by_score_and_sets_seed_relevance():
    hi = Candidate(paper_id="hi", reference_count=5)
    lo = Candidate(paper_id="lo", reference_count=5)
    edges = [
        _edge(hi, 3.0),
        _edge(hi, 3.0),
        _edge(hi, 3.0),  # co-cited 3x by Perfect seeds
        _edge(lo, 2.0),  # once, weaker (Highly) seed
    ]
    promoted = promote_snowball(edges, "forward", ARM_C)
    assert [c.paper_id for c in promoted] == ["hi", "lo"]
    # promote records the computed score on seed_relevance for inspection
    assert promoted[0].seed_relevance > promoted[1].seed_relevance


def test_promote_respects_top_k():
    edges = [
        _edge(Candidate(paper_id=f"c{i}", reference_count=1), 3.0) for i in range(10)
    ]
    promoted = promote_snowball(edges, "forward", ARM_C, top_k=3)
    assert len(promoted) == 3


def test_promote_default_top_k_is_config():
    assert (
        CONFIG.budgets.snowball_top_k == 200
    )  # guards the default used by promote_snowball
