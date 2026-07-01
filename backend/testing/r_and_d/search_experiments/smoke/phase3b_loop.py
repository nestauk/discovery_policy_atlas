"""Phase 3b smoke test — the closed-loop agentic core, OFFLINE over FakeSource (no API/LLM).

Unlike phase2/phase3a (live), this one is deterministic and offline: FakeSource returns canned
candidates and a *fake judge* grades them by origin, so you can watch the mechanism without
spending tokens. Two stages:

  Stage 1 — `adaptive_load` SPOTLIGHT: a hand-built pool where candidates >> budget, so you can
            SEE Batched Thompson Sampling concentrate the judging budget on high-reward origins
            and starve the low-reward one.
  Stage 2 — the full `broad_search` loop (Arm C caps) end-to-end: per-iteration retrieve →
            snowball → adaptive judge, then the §4.3 Step-5 ranking.

Run from the project dir:
    uv run smoke/phase3b_loop.py
"""

import asyncio
from collections import defaultdict

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from adaptive import HighlyRelevantShortcircuit, adaptive_load, to_reward
from broad_search import broad_search
from config import CONFIG
from query_analysis import QueryAnalysis, QueryIntent
from source import Candidate, Capabilities, FakeSource

ARM_C = Capabilities(has_dense=True, has_influential=True, has_snippets=True)


def _mechanism(origin: str) -> str:
    """Collapse a granular arm ("keyword:i0q3") to its mechanism ("keyword") for display."""
    return origin.split(":")[0] if origin else "(none)"


# --------------------------------------------------------------------------- #
# A fake judge: grades by origin so reward is heterogeneous across origins.
# --------------------------------------------------------------------------- #
def _fake_judge(level_for):
    async def judge(batch):
        for c in batch:
            c.level = level_for(c)

    return judge


def _spotlight_level(c: Candidate) -> int:
    origin = min(c.origins) if c.origins else ""
    if origin.startswith("dense"):
        return 3  # a great dense query — 60%+ Perfect
    if origin.startswith("keyword"):
        return 3 if c.paper_id.endswith(("-0", "-3", "-6", "-9")) else 1  # mixed
    return 0  # parametric suggestions: weak on policy (spec warns)


def _loop_level(c: Candidate) -> int:
    origin = min(c.origins) if c.origins else ""
    pid = c.paper_id
    if origin.startswith("dense"):
        return 3 if pid.endswith(("-0", "-1", "-2")) else 1
    if origin.startswith("keyword"):
        return 3 if pid.endswith("-0") else (2 if pid.endswith("-1") else 0)
    if origin.startswith("snowball"):
        return 2 if pid.endswith("-0") else 0
    return 0  # suggest


# --------------------------------------------------------------------------- #
async def run_smoke():
    # ===== STAGE 1: BTS allocation spotlight ================================ #
    rule("1. adaptive_load SPOTLIGHT — does the bandit spend budget where reward is?")
    pool = (
        [Candidate(paper_id=f"dense-{i}", origins={"dense:q0"}) for i in range(120)]
        + [Candidate(paper_id=f"kw-{i}", origins={"keyword:q0"}) for i in range(120)]
        + [Candidate(paper_id=f"sug-{i}", origins={"suggest"}) for i in range(120)]
    )
    quota = CONFIG.budgets.per_iteration_judge_budget  # 150
    print(f"   pool: 360 candidates across 3 origins; judging budget = {quota}")
    print(
        "   reward by origin:  dense -> all Perfect (0.875) | keyword -> mixed | suggest -> 0.0\n"
    )

    judged, reason = await adaptive_load(
        pool,
        _fake_judge(_spotlight_level),
        quota=quota,
        shortcircuit=HighlyRelevantShortcircuit(
            score_cap=10**9
        ),  # disabled, to show full spend
        seed=0,
    )
    alloc: dict[str, list[int]] = defaultdict(list)
    for c in judged:
        alloc[_mechanism(min(c.origins))].append(c.level)
    print(f"   judged {len(judged)}/{quota} ({reason}). Budget split by origin:")
    for mech in ("dense", "keyword", "suggest"):
        lvls = alloc.get(mech, [])
        mean_r = sum(to_reward(level) for level in lvls) / len(lvls) if lvls else 0.0
        bar = "#" * round(len(lvls) / 3)
        print(f"     {mech:8s} judged={len(lvls):3d}  mean_reward={mean_r:.3f}  {bar}")
    print(
        "   ^ BTS starves 'suggest' (reward 0) and concentrates on dense/keyword — the point."
    )

    # ===== STAGE 2: full broad_search loop ================================= #
    rule("2. broad_search — full closed loop over FakeSource (Arm C), 2 iterations")
    analysis = QueryAnalysis(
        raw_query="latest evidence on the minimum wage and employment",
        content="effect of the minimum wage on employment",
        intent=QueryIntent(recency="recent"),
    )
    print(
        f"   content={analysis.content!r}  intent.weight_key={analysis.intent.weight_key()}\n"
    )
    result = await broad_search(
        FakeSource(caps=ARM_C),
        ARM_C,
        analysis,
        judge_fn=_fake_judge(_loop_level),
        seed=0,
    )
    for s in result.iterations:
        print(
            f"   iter {s.iteration}: seeds={s.n_seeds:2d}  retrieved={s.n_retrieved:3d}  "
            f"snowball(fwd={s.n_snowball_fwd:3d},bwd={s.n_snowball_bwd:3d})  "
            f"judged={s.n_judged:3d}  ({s.stop_reason})"
        )
    print(
        f"   total judged={result.n_judged}  pool={len(result.pool)}  ranked={len(result.ranked)}"
    )

    rule("3. judged pool by mechanism (which origins earned their budget)")
    by_mech: dict[str, list[int]] = defaultdict(list)
    for c in result.pool:
        if c.level is not None:
            by_mech[_mechanism(min(c.origins))].append(c.level)
    for mech in sorted(by_mech, key=lambda m: -len(by_mech[m])):
        lvls = by_mech[mech]
        n_perfect = sum(level == 3 for level in lvls)
        print(f"     {mech:14s} judged={len(lvls):3d}  perfect(L3)={n_perfect:3d}")

    rule("4. final ranking — top 8 (§4.3 Step 5 blend; no Cohere offline so rerank=0)")
    for rank, c in enumerate(result.ranked[:8], 1):
        print(
            f"   #{rank}  L{c.level}  {_mechanism(min(c.origins)):12s}  {c.year}  {c.paper_id}"
        )
    return result


asyncio.run(run_smoke())
