"""Arm C — Semantic Scholar agentic loop (spec §4.3a, Phase 8).

Arm C is Arm B with one swap: `source = S2Source()` instead of `OpenAlexSource()`. Because S2Source's
`caps` are all-True, the SAME shared `broad_search` loop lights up the legs that stayed dormant in
Arm B (the four §4.3 source-forced diffs):

  - has_dense       → the dense leg runs (formulate_dense_queries + dense_search, S2 /snippet/search)
  - has_influential → forward snowball carries the +0.1·is_influential term (snowball.py)
  - has_snippets    → the +0.025·sigmoid(num_snippets) term enters the §4.3 blend (ranking.py)
  - native_abstracts→ abstracts/tldr come inline (no Crossref enrich); text_basis set by the S2 client

So B→C isolates exactly the dense source: same loop, same judge, same blend mechanism — only the
source (and the capabilities it unlocks) changes. The judge_fn + ranked-record shaping are reused
from arm_b verbatim (`classify_text_basis` is Arm-C-safe — it leaves tldr/snippet flags untouched).

S2 is rate-limited (1 req/s cumulative) and S2Source holds an httpx client, so run_query closes it in
a finally. A cold run is slow (the throttle dominates, spec §7); cached + resumable thereafter.

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from arms.arm_c import run_query
    from queries.loader import load_queries
    res = asyncio.run(run_query(load_queries()[0]))   # runs the loop + persists
"""

from __future__ import annotations

import functools
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from _timing import StageTimer, stage_timings
from arms.arm_b import (
    _make_judge_fn,
    _ranked_records,
)  # source-agnostic loop helpers (reused)
from core.broad_search import broad_search
from queries.loader import Query, load_queries
from query_analysis import analyse_query
from core.ranking import cohere_rerank

logger = logging.getLogger(__name__)

_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "arms" / "arm_c"


@dataclass
class ArmCResult:
    query_id: str
    query_text: str
    n_pool: int
    n_judged: int
    ranked: list[dict] = field(default_factory=list)  # [{paper_id, rank, level}]
    timings: dict = field(
        default_factory=dict
    )  # _timing.stage_timings (latency instrumentation)


async def run_query(q: Query, *, persist: bool = True, seed: int = 0) -> ArmCResult:
    """Run the Arm C loop for one query (Step 0 → broad_search over S2Source → persist)."""
    from _backend import get_settings
    from retrieval.s2_client import S2Source  # lazy (pulls backend env)

    analysis = analyse_query(q.query_id, q.query_text)
    # Same production-default floor as Arm A/B (decided 2026-06-26) so B→C isolates the SOURCE, not the
    # floor: S2 floors its keyword+dense legs at cited_by_count>min_citations (snowball/suggest unfloored,
    # mirroring OpenAlexSource). See FINDINGS 2026-06-26.
    source = S2Source(min_citations=get_settings().DEFAULT_MIN_CITATIONS)
    timer = StageTimer()  # one timer shared by broad_search's stages AND the judge_fn
    t0 = time.monotonic()
    try:
        result = await broad_search(
            source,
            source.caps,  # all-True → dense + influential + snippet legs active
            analysis,
            judge_fn=_make_judge_fn(q.query_id, q.query_text, timer),
            rerank_fn=functools.partial(cohere_rerank, q.query_id, q.query_text),
            seed=seed,
            timer=timer,
        )
    finally:
        await source.aclose()  # close the httpx client (S2-specific)
    total_s = time.monotonic() - t0

    res = ArmCResult(
        query_id=q.query_id,
        query_text=q.query_text,
        n_pool=len(result.pool),
        n_judged=result.n_judged,
        ranked=_ranked_records(result.ranked),
        timings=stage_timings(total_s, timer, result.n_judged),
    )
    if persist:
        _persist(res)
    return res


def _persist(result: ArmCResult) -> None:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"{result.query_id}.json"
    out.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    logger.info(
        "Arm C: wrote %s (pool=%d, judged=%d)", out, result.n_pool, result.n_judged
    )


async def run_all() -> list[ArmCResult]:
    """Run Arm C over the whole curated query set (expensive: S2 1 req/s throttle + loop + judging)."""
    results = []
    for q in load_queries():
        logger.info("Arm C: running %s", q.query_id)
        results.append(await run_query(q))
    return results
