"""Phase 8 smoke — Arm C (Semantic Scholar agentic loop), LIVE end-to-end.

Same query (q11) and shape as the Arm B smoke, but source = S2Source — so the dormant legs light
up: watch for `dense:*` origins in the mix (the §4.3 #1 dense leg), and the loop otherwise mirrors
Arm B. Prints per-iteration stats, origin mix, and top ranked papers with judged levels, for a
direct A↔B↔C contrast on the same query.

SLOWEST smoke: S2 is throttled to 1 req/s (cumulative), so a cold run is dominated by the throttle
(spec §7) on top of ~250 live judgements; cached + resumable thereafter. Run from project dir:
    uv run smoke/phase8_arm_c.py
"""

import asyncio
import functools
from collections import Counter

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from arms.arm_b import _make_judge_fn
from broad_search import broad_search
from queries.loader import load_queries
from query_analysis import analyse_query
from ranking import cohere_rerank

QUERY_ID = "q11"  # same query as Arm A/B smokes, for an A↔B↔C contrast


def _short(t: str | None, n: int = 70) -> str:
    t = (t or "(no title)").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


def _origin_mech(origin: str) -> str:
    return origin.split(":", 1)[0] if origin else "?"


async def run_smoke():
    q = next(x for x in load_queries() if x.query_id == QUERY_ID)
    from retrieval.s2_client import S2Source

    rule("0. analyse_query — content + recency/centrality intent (shared with Arm B)")
    analysis = analyse_query(q.query_id, q.query_text)
    print(f"   query_id = {q.query_id}   content = {_short(analysis.content, 90)!r}")
    print(
        f"   intent   = recency={analysis.intent.recency!r} weights={analysis.intent.weights()}"
    )

    rule(
        "1-4. broad_search over S2Source — DENSE leg + influential snowball + snippet blend ACTIVE"
    )
    source = S2Source()
    print(f"   caps = {source.caps}")
    try:
        result = await broad_search(
            source,
            source.caps,
            analysis,
            judge_fn=_make_judge_fn(q.query_id, q.query_text),
            rerank_fn=functools.partial(cohere_rerank, q.query_id, q.query_text),
        )
    finally:
        await source.aclose()

    for it in result.iterations:
        print(
            f"   iter {it.iteration}: retrieved={it.n_retrieved} "
            f"snowball(fwd={it.n_snowball_fwd},bwd={it.n_snowball_bwd}) "
            f"judged={it.n_judged} ({it.stop_reason})"
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
    n_infl = sum(c.is_influential for c in result.pool)
    n_snip = sum(c.num_snippets > 0 for c in result.pool)
    print(
        f"   §4.3 signals: {n_infl} influential-citation, {n_snip} with dense snippets"
    )

    rule(
        "5. top of final ranking (blend incl. snippet term + Cohere) with judged levels"
    )
    for c in result.ranked[:8]:
        print(f"     L{c.level}  n_snip={c.num_snippets:<2} {_short(c.title)}")

    rule(
        "DONE — Arm C exercised live (S2 dense source; B→C isolates the dense leg). Throttled @1 req/s."
    )
    return result


asyncio.run(run_smoke())
