"""Phase 7 smoke — Arm B (OpenAlex agentic loop), LIVE end-to-end.

Runs one curated query through the FULL shared loop with OpenAlexSource: Step-0 analysis →
2 iterations (multi-query + SR/RCT fanout + parametric suggest, then reformulate + snowball) →
adaptive BTS judging → §4.3 blend + Cohere rerank. Prints per-iteration stats, the origin mix,
and the top ranked papers with judged levels — so you can eyeball the loop and contrast with
Arm A on the SAME query (q11).

HEAVIEST smoke: judges up to CONFIG.budgets.judge_quota (250) live (cached + resumable, so a
rerun is fast; the run also warms the shared judge cache). Cohere degrades to rerank_score=0 with
no COHERE_API_KEY. Run from project dir:
    uv run smoke/phase7_arm_b.py
"""

import asyncio
import functools
from collections import Counter

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from arms.arm_b import _make_judge_fn
from broad_search import broad_search
from query_analysis import analyse_query
from queries.loader import load_queries
from ranking import cohere_rerank

QUERY_ID = "q11"  # same query as the Arm A smoke, for an A↔B contrast


def _short(t: str | None, n: int = 70) -> str:
    t = (t or "(no title)").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


def _origin_mech(origin: str) -> str:
    return origin.split(":", 1)[0] if origin else "?"


async def run_smoke():
    q = next(x for x in load_queries() if x.query_id == QUERY_ID)
    from retrieval.openalex_client import OpenAlexSource

    rule(
        "0. analyse_query — content + recency/centrality intent (Step 0, shared with Arm C)"
    )
    analysis = analyse_query(q.query_id, q.query_text)
    print(f"   query_id = {q.query_id}   query_text = {_short(q.query_text, 90)!r}")
    print(f"   content  = {_short(analysis.content, 90)!r}")
    print(
        f"   intent   = recency={analysis.intent.recency!r} weights={analysis.intent.weights()}"
    )

    rule(
        "1-4. broad_search loop — multi-query+fanout, suggest, snowball, adaptive judge, blend rank"
    )
    source = (
        OpenAlexSource()
    )  # no citation floor (PF-faithful) — vs Arm A's min_citations=5
    result = await broad_search(
        source,
        source.caps,
        analysis,
        judge_fn=_make_judge_fn(q.query_id, q.query_text),
        rerank_fn=functools.partial(cohere_rerank, q.query_id, q.query_text),
    )

    for it in result.iterations:
        print(
            f"   iter {it.iteration}: retrieved={it.n_retrieved} "
            f"snowball(fwd={it.n_snowball_fwd},bwd={it.n_snowball_bwd}) "
            f"judged={it.n_judged} ({it.stop_reason}); seeds_in={it.n_seeds}"
        )
    print(
        f"   pool={len(result.pool)}  judged={result.n_judged}  ranked={len(result.ranked)}"
    )

    origins = Counter(
        _origin_mech(min(c.origins) if c.origins else "") for c in result.pool
    )
    print(
        "   origin mix (pool): "
        + "  ".join(f"{k}={v}" for k, v in origins.most_common())
    )

    rule("5. top of final ranking (blend + Cohere) with judged levels")
    for c in result.ranked[:8]:
        print(f"     L{c.level}  {_short(c.title)}")

    rule(
        "DONE — Arm B loop exercised live (contrast Arm A: +loop, +snowball, +suggest, blend rank)."
    )
    return result


asyncio.run(run_smoke())
