"""Arm B — OpenAlex agentic loop (spec §4.3, Phase 7).

Arm B is a thin wrapper: it runs the shared `broad_search` loop with `OpenAlexSource`. Almost all
the machinery already exists — this module supplies the three things the loop needs injected and
persists the result in Arm A's schema for Phase 9 pooling:

  - Step 0: `analyse_query` → content + recency/centrality intent (cached; shared with Arm C).
  - judge_fn: judges a batch IN PLACE (sets cand.level) via the shared `judge.judge_papers`; the
    adaptive BTS loop calls this incrementally, and the cross-arm cache judges each paper once.
  - rerank_fn: `cohere_rerank` (sets cand.rerank_score; degrades to 0 with no Cohere key).

Contrast with Arm A (same source + multi-query formulation + SR/RCT fanout + ~250 judge budget):
Arm B adds the LOOP — 2 iterations w/ reformulation, snowball, parametric suggestions, adaptive
judging, and the source-agnostic §4.3 blend ranker (not OpenAlex relevance_score). The citation floor
is held at production's DEFAULT_MIN_CITATIONS across all three arms (2026-06-26) so the ladder isolates
only the loop (A→B) and the source (B→C) — see the run_query note + FINDINGS for why no-floor was dropped.

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from arms.arm_b import run_query
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
from core.broad_search import broad_search
from queries.loader import Query, load_queries
from query_analysis import analyse_query
from core.ranking import cohere_rerank
from core.source import Candidate

logger = logging.getLogger(__name__)

_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "arms" / "arm_b"


def _ranked_records(ranked: list[Candidate]) -> list[dict]:
    """Final ranked candidates → persisted rows (pure, testable). Carries the four §4.3-blend
    FEATURES (rerank_score, num_snippets, year, cited_by_count) alongside paper_id/rank/level so the
    §4.7 reranker sweep can re-score the pool offline — they only exist on the live Candidates during
    a run, so they must be captured here or a costly re-run is needed to recover them."""
    return [
        {
            "paper_id": c.paper_id,
            "rank": i,
            "level": c.level,
            "rerank_score": c.rerank_score,
            "num_snippets": c.num_snippets,
            "year": c.year,
            "cited_by_count": c.cited_by_count,
        }
        for i, c in enumerate(ranked)
    ]


def _make_judge_fn(query_id: str, query_text: str, timer: StageTimer | None = None):
    """Build the broad_search judge_fn: judge a batch in place (set cand.level) via the shared judge.

    `timer` (optional) records the judge LLM-call wall-time into the shared `judge` bucket — the
    SAME StageTimer broad_search threads through its other stages, so all five buckets accumulate
    into one record. Omit it (smoke/tests) and a throwaway timer is used."""
    timer = timer or StageTimer()

    async def judge_fn(batch: list[Candidate]) -> None:
        from core.judge import (
            get_cached_levels,
            judge_papers,
        )  # lazy (pulls backend env)
        from retrieval.enrich import classify_text_basis

        classify_text_basis(
            batch
        )  # set text_basis (abstract vs title_only) before judging, §4.4
        papers = [
            {
                "paper_id": c.paper_id,
                "title": c.title,
                "abstract": c.abstract,
                "text_basis": c.text_basis,
            }
            for c in batch
        ]
        with timer.track(
            "judge"
        ):  # LLM judge call (cache-contaminated; reconstructed later)
            await judge_papers(query_id, query_text, papers)
        levels = get_cached_levels(query_id)
        for c in batch:
            c.level = levels.get(c.paper_id)

    return judge_fn


@dataclass
class ArmBResult:
    query_id: str
    query_text: str
    n_pool: int  # full deduped candidate pool (judged + unjudged)
    n_judged: int
    ranked: list[dict] = field(
        default_factory=list
    )  # [{paper_id, rank, level, +blend features}]
    timings: dict = field(
        default_factory=dict
    )  # _timing.stage_timings (latency instrumentation)
    n_search_failures: (
        int
    ) = 0  # boolean-variant searches skipped after OpenAlex 500/504 (parity w/ prod)


async def run_query(q: Query, *, persist: bool = True, seed: int = 0) -> ArmBResult:
    """Run the Arm B loop for one query (Step 0 → broad_search → persist ranked+judged)."""
    from _backend import get_settings
    from retrieval.openalex_client import OpenAlexSource  # lazy (pulls backend env)

    analysis = analyse_query(q.query_id, q.query_text)
    # Production-default citation floor, held CONSTANT across A/B/C (decided 2026-06-26): keeps the
    # ladder clean (A→B = loop only, B→C = source only, no floor confound) and lets OpenAlex complete
    # the complex multi-AND booleans that 500'd with no floor. See FINDINGS 2026-06-26.
    source = OpenAlexSource(min_citations=get_settings().DEFAULT_MIN_CITATIONS)
    timer = StageTimer()  # one timer shared by broad_search's stages AND the judge_fn
    t0 = time.monotonic()
    result = await broad_search(
        source,
        source.caps,
        analysis,
        judge_fn=_make_judge_fn(q.query_id, q.query_text, timer),
        rerank_fn=functools.partial(cohere_rerank, q.query_id, q.query_text),
        seed=seed,
        timer=timer,
    )
    total_s = time.monotonic() - t0
    res = ArmBResult(
        query_id=q.query_id,
        query_text=q.query_text,
        n_pool=len(result.pool),
        n_judged=result.n_judged,
        ranked=_ranked_records(result.ranked),
        timings=stage_timings(total_s, timer, result.n_judged),
        n_search_failures=source.n_search_failures,
    )
    if persist:
        _persist(res)
    return res


def _persist(result: ArmBResult) -> None:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"{result.query_id}.json"
    out.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    logger.info(
        "Arm B: wrote %s (pool=%d, judged=%d)", out, result.n_pool, result.n_judged
    )


async def run_all() -> list[ArmBResult]:
    """Run Arm B over the whole curated query set (expensive: loop + ~250 judgements/query)."""
    results = []
    for q in load_queries():
        logger.info("Arm B: running %s", q.query_id)
        results.append(await run_query(q))
    return results
