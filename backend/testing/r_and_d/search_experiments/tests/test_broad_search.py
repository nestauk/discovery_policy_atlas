"""Offline integration test for broad_search.py over FakeSource (no network, no LLM).

Exercises the whole closed loop end-to-end with a deterministic fake judge, asserting the
structural invariants: budget respected, two iterations, snowball seeded from iteration-0
judgements, source-forced caps honoured (Arm B has no dense leg), and determinism.
"""

from __future__ import annotations

from core.broad_search import broad_search
from config import CONFIG
from query_analysis import QueryAnalysis, QueryIntent
from core.source import Candidate, Capabilities, FakeSource

ARM_B = Capabilities()
ARM_C = Capabilities(has_dense=True, has_influential=True, has_snippets=True)


def _analysis() -> QueryAnalysis:
    return QueryAnalysis(
        raw_query="minimum wage and employment",
        content="minimum wage and employment",
        intent=QueryIntent(),
    )


def _judge_keyword_seeds():
    """Fake judge: a couple of keyword hits per query are Perfect (-> seeds); rest Not-relevant.

    Grading by origin + id keeps the seed set small and deterministic so snowball is bounded.
    """

    async def judge(batch: list[Candidate]) -> None:
        for c in batch:
            origin = min(c.origins) if c.origins else ""
            is_seed = origin.startswith("keyword") and c.paper_id.endswith(("-0", "-1"))
            c.level = 3 if is_seed else 0

    return judge


async def test_loop_runs_two_iterations_and_snowballs_from_seeds():
    result = await broad_search(
        FakeSource(caps=ARM_B), ARM_B, _analysis(), judge_fn=_judge_keyword_seeds()
    )
    assert len(result.iterations) == CONFIG.budgets.n_search_iterations

    it0, it1 = result.iterations
    assert it0.n_seeds == 0  # nothing judged yet on the first pass
    assert it0.n_retrieved > 0
    # iteration 0 produced Perfect keyword seeds -> iteration 1 can snowball from them
    assert it1.n_seeds > 0
    assert it1.n_snowball_fwd > 0 and it1.n_snowball_bwd > 0


async def test_budget_respected_and_ranked_capped():
    result = await broad_search(
        FakeSource(caps=ARM_B), ARM_B, _analysis(), judge_fn=_judge_keyword_seeds()
    )
    assert result.n_judged <= CONFIG.budgets.judge_quota
    assert len(result.ranked) <= CONFIG.budgets.final_result_cap
    assert len(result.ranked) > 0


async def test_origins_accrete_snowball_tags():
    result = await broad_search(
        FakeSource(caps=ARM_B), ARM_B, _analysis(), judge_fn=_judge_keyword_seeds()
    )
    all_origins = {o for c in result.pool for o in c.origins}
    assert any(o.startswith("keyword") for o in all_origins)
    assert any(o.startswith("snowball_fwd") for o in all_origins)


async def test_arm_b_has_no_dense_leg_but_arm_c_does():
    # Arm B must never call dense_search (it would raise); Arm C populates dense origins.
    res_b = await broad_search(
        FakeSource(caps=ARM_B), ARM_B, _analysis(), judge_fn=_judge_keyword_seeds()
    )
    res_c = await broad_search(
        FakeSource(caps=ARM_C), ARM_C, _analysis(), judge_fn=_judge_keyword_seeds()
    )
    origins_b = {o for c in res_b.pool for o in c.origins}
    origins_c = {o for c in res_c.pool for o in c.origins}
    assert not any(o.startswith("dense") for o in origins_b)
    assert any(o.startswith("dense") for o in origins_c)


async def test_loop_is_deterministic_under_seed():
    a = await broad_search(
        FakeSource(caps=ARM_B),
        ARM_B,
        _analysis(),
        judge_fn=_judge_keyword_seeds(),
        seed=3,
    )
    b = await broad_search(
        FakeSource(caps=ARM_B),
        ARM_B,
        _analysis(),
        judge_fn=_judge_keyword_seeds(),
        seed=3,
    )
    assert [c.paper_id for c in a.ranked] == [c.paper_id for c in b.ranked]


async def test_rerank_fn_is_applied_when_provided():
    # A stub rerank_fn sets rerank_score in place; broad_search should call it before ranking.
    async def fake_rerank(pool: list[Candidate]) -> None:
        for c in pool:
            c.rerank_score = 0.5

    result = await broad_search(
        FakeSource(caps=ARM_B),
        ARM_B,
        _analysis(),
        judge_fn=_judge_keyword_seeds(),
        rerank_fn=fake_rerank,
    )
    assert all(c.rerank_score == 0.5 for c in result.pool)
