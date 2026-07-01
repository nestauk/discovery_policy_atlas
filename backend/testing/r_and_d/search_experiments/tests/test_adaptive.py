"""Offline tests for adaptive.py — reward, short-circuit, and the BTS allocation behaviour.

No LLM/network: the "judge" is a deterministic stub that grades by origin, so we can assert the
bandit concentrates budget on rewarding origins and the short-circuit fires correctly.
"""

from __future__ import annotations

from adaptive import (
    HighlyRelevantShortcircuit,
    adaptive_load,
    assign_to_origins,
    to_reward,
)
from config import CONFIG
from source import Candidate


def _cand(pid: str, origin: str) -> Candidate:
    return Candidate(paper_id=pid, origins={origin})


def _judge_by(level_fn):
    """Build an async judge that sets cand.level from a per-candidate function."""

    async def judge(batch):
        for c in batch:
            c.level = level_fn(c)

    return judge


# ------------------------------- to_reward --------------------------------- #
def test_to_reward_exact_values():
    # PF ((2**level)/8) - 0.125 — exponential, level 3 worth ~2.3x level 2.
    assert to_reward(0) == 0.0
    assert to_reward(1) == 0.125
    assert to_reward(2) == 0.375
    assert to_reward(3) == 0.875
    assert to_reward(None) == 0.0  # unjudged treated as 0


def test_to_reward_is_monotone_and_convex():
    r = [to_reward(level) for level in range(4)]
    assert r == sorted(r)
    # convex: each step bigger than the last (the Perfect-seeking shape)
    gaps = [r[i + 1] - r[i] for i in range(3)]
    assert gaps == sorted(gaps) and gaps[2] > gaps[0]


# -------------------------- HighlyRelevantShortcircuit --------------------- #
def test_shortcircuit_needs_both_perfect_and_cap():
    sc = HighlyRelevantShortcircuit(score_cap=4)
    sc.accumulate([_lvl("a", 2), _lvl("b", 2)])  # score 2, no perfect
    assert not sc.should_break()  # has the mass but no Perfect anchor
    sc.accumulate([_lvl("c", 3)])  # +2 -> score 4, now has a Perfect
    assert sc.should_break()


def test_shortcircuit_scores_2_perfect_1_highly_0_below():
    sc = HighlyRelevantShortcircuit(score_cap=10**9)
    sc.accumulate([_lvl("p", 3), _lvl("h", 2), _lvl("s", 1), _lvl("n", 0)])
    assert (
        sc.accumulated_score
        == CONFIG.adaptive.score_per_perfect + CONFIG.adaptive.score_per_highly
    )
    assert sc.found_perfect


def test_shortcircuit_dedups_by_paper_id():
    sc = HighlyRelevantShortcircuit(score_cap=10**9)
    sc.accumulate([_lvl("x", 3)])
    sc.accumulate([_lvl("x", 3)])  # same paper re-seen across batches -> not re-counted
    assert sc.accumulated_score == CONFIG.adaptive.score_per_perfect


def _lvl(pid: str, level: int) -> Candidate:
    c = Candidate(paper_id=pid)
    c.level = level
    return c


# ----------------------------- assign_to_origins --------------------------- #
def test_assign_to_origins_multi_membership_and_empty():
    # A co-surfaced candidate is filed under EVERY origin (PF multi_group_by), so it is
    # reachable from any of its arms; an origin-less candidate goes under "".
    a = Candidate(paper_id="a", origins={"keyword:q1", "dense:q0"})
    b = Candidate(paper_id="b", origins=set())
    grouped = assign_to_origins([a, b])
    assert grouped["keyword:q1"] == [a]
    assert grouped["dense:q0"] == [a]  # under BOTH, not just min()
    assert grouped[""] == [b]


# ------------------------------- adaptive_load ----------------------------- #
async def test_budget_is_never_exceeded():
    cands = [_cand(f"x{i}", "X") for i in range(100)]
    judged, reason = await adaptive_load(
        cands,
        _judge_by(lambda c: 0),
        quota=37,
        shortcircuit=HighlyRelevantShortcircuit(score_cap=10**9),
    )
    assert len(judged) == 37
    assert reason == "quota"


async def test_exhausted_when_fewer_candidates_than_quota():
    cands = [_cand(f"a{i}", "A") for i in range(3)] + [
        _cand(f"b{i}", "B") for i in range(10)
    ]
    judged, reason = await adaptive_load(
        cands,
        _judge_by(lambda c: 0),
        quota=500,
        shortcircuit=HighlyRelevantShortcircuit(score_cap=10**9),
    )
    assert len(judged) == 13  # every candidate judged exactly once
    assert reason == "exhausted"
    assert len({c.paper_id for c in judged}) == 13


async def test_preload_touches_every_origin():
    # With a tiny quota, the uniform preload still reaches both origins (no arm unexplored).
    cands = [_cand(f"a{i}", "A") for i in range(10)] + [
        _cand(f"b{i}", "B") for i in range(10)
    ]
    preload = CONFIG.adaptive.uniform_preload_size
    judged, _ = await adaptive_load(
        cands,
        _judge_by(lambda c: 0),
        quota=2 * preload,
        shortcircuit=HighlyRelevantShortcircuit(score_cap=10**9),
    )
    origins = {min(c.origins) for c in judged}
    assert origins == {"A", "B"}


async def test_bandit_concentrates_budget_on_high_reward_origin():
    # "good" always yields Perfect (reward 0.875), "bad" always Not-relevant (0.0). With the
    # short-circuit disabled, the bandit should spend most of the post-preload budget on "good".
    cands = [_cand(f"g{i}", "good") for i in range(100)] + [
        _cand(f"b{i}", "bad") for i in range(100)
    ]
    judged, reason = await adaptive_load(
        cands,
        _judge_by(lambda c: 3 if "good" in c.origins else 0),
        quota=60,
        shortcircuit=HighlyRelevantShortcircuit(score_cap=10**9),
        seed=0,
    )
    good = sum("good" in c.origins for c in judged)
    bad = sum("bad" in c.origins for c in judged)
    assert reason == "quota" and len(judged) == 60
    assert good > bad  # probability-matching steered budget toward the rewarding origin
    assert good > 2 * bad  # and decisively so


async def test_bandit_allocation_is_deterministic_under_seed():
    def run():
        cands = [_cand(f"g{i}", "good") for i in range(50)] + [
            _cand(f"b{i}", "bad") for i in range(50)
        ]
        return cands

    async def go():
        cands = run()
        judged, _ = await adaptive_load(
            cands,
            _judge_by(lambda c: 3 if "good" in c.origins else 0),
            quota=40,
            shortcircuit=HighlyRelevantShortcircuit(score_cap=10**9),
            seed=7,
        )
        return [c.paper_id for c in judged]

    assert await go() == await go()  # same seed -> identical Thompson draws


async def test_co_found_paper_is_reached_via_its_hot_origin():
    """Starvation regression (multi-origin fix). X is relevant but sits DEEP in a cold origin's
    queue (never pulled past preload) AND was also co-surfaced by a hot origin, where it sits
    just past preload depth. Under single-origin assignment X would be filed under "cold" (min
    tag) and never judged; under multi_group_by it rides the hot arm and gets judged.
    """
    cold = [
        _cand(f"c{i}", "cold") for i in range(50)
    ]  # all level 0, bandit starves this arm
    x = Candidate(
        paper_id="X", origins={"cold", "hot"}
    )  # graded 3 (has "hot"); see level_fn
    # hot queue order = input order: 10 hot papers BEFORE X, so X is at hot-index 10 (past the
    # 5-deep preload), reachable only once the bandit pulls "hot" enough times.
    hot = [_cand(f"h{i}", "hot") for i in range(60)]
    cands = cold + hot[:10] + [x] + hot[10:]

    judged, _ = await adaptive_load(
        cands,
        _judge_by(lambda c: 3 if "hot" in c.origins else 0),
        quota=40,
        shortcircuit=HighlyRelevantShortcircuit(score_cap=10**9),
        seed=0,
    )
    judged_x = [c for c in judged if c.paper_id == "X"]
    assert len(judged_x) == 1  # judged exactly once (is-loaded guard), not stranded
    assert judged_x[0].level == 3


async def test_shortcircuit_stops_a_run_early():
    cands = [_cand(f"p{i}", "P") for i in range(200)]  # all Perfect
    judged, reason = await adaptive_load(
        cands,
        _judge_by(lambda c: 3),
        quota=200,
        shortcircuit=HighlyRelevantShortcircuit(),  # default cap 50
    )
    assert reason == "short_circuit"
    assert (
        len(judged) < 200
    )  # stopped once a Perfect + score>=50 accumulated (~25 Perfects)
