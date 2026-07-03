"""The shared, source-agnostic broad-search loop (spec §4.3 Steps 1-5; PF `broad_search.py`).

This is the "machinery built once" that makes Arms B and C mechanism-identical (the A→B→C
ladder, spec §6). It depends ONLY on the `SourceClient` + `Capabilities` abstractions
(source.py); Arms B (OpenAlex) and C (S2) are thin wrappers that pass a different client and
caps. Everything source-forced (§4.3) is read from `caps` in ONE place here — there are no two
near-duplicate pipelines to drift apart.

The loop, per search iteration (diligent = 2, `CONFIG.budgets.n_search_iterations`):

  1. RETRIEVE (primary)   iter 0: keyword search over N formulated queries
                                  + dense search (Arm C only, `caps.has_dense`)
                                  + LLM parametric suggestions
                          iter≥1: the same legs over *reformulated* queries (judge-relevant
                                  exemplars feed the reformulation — closed loop)
  2. EXPAND (followup)    snowball forward+backward from seeds judged ≥2 so far (empty in iter 0
                          — nothing judged yet — exactly as PF, which snowballs on the previous
                          iteration's judged docs). Forward influence term is Arm-C-only.
  3. JUDGE (adaptive)     dedupe, then `adaptive_load` (Batched Thompson Sampling) over the new
                          candidates, steering a per-iteration budget (~150) toward high-reward
                          origins, with a FRESH `HighlyRelevantShortcircuit` (PF refreshes it
                          each iteration). Global stop = total judging quota (250).
  5. RANK (once, at end)  optional Cohere rerank (`rerank_fn`) then the §4.3 Step-5 blend
                          (ranking.py). Kept out of the loop so the loop is API-free + offline
                          testable; the arm wrapper supplies `rerank_fn=cohere_rerank`.

`judge_fn` and `rerank_fn` are injected closures (they capture `query_id` for caching), so this
module needs no judge/LLM/network imports — the FakeSource smoke + tests drive it fully offline.

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from core.broad_search import broad_search
    async def judge(batch):           # sets cand.level (FakeSource: deterministic stub)
        for c in batch: c.level = ...
    result = asyncio.run(broad_search(FakeSource(), Capabilities(), analysis, judge_fn=judge))
    result.ranked      # final ranked list (capped 250)
    result.iterations  # per-iteration stats (counts, stop reason) for inspection/tests
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from _timing import StageTimer
from core.adaptive import HighlyRelevantShortcircuit, JudgeFn, StopReason, adaptive_load
from config import CONFIG
from query_analysis import QueryAnalysis
from core.ranking import rank_candidates
from core.snowball import build_edges, promote_snowball
from core.source import Candidate, Capabilities, SourceClient, dedupe

logger = logging.getLogger(__name__)

# A rerank function sets cand.rerank_score in place (e.g. functools.partial(cohere_rerank,
# query_id, content)). None -> skip (blend degrades to judge + recency/centrality, §4.3 Step 5).
RerankFn = Callable[[list[Candidate]], Awaitable[None]]


@dataclass
class IterationStat:
    """What one search iteration produced — for the smoke's stage printing + test assertions."""

    iteration: int
    n_seeds: int  # candidates judged >=2 available BEFORE this iteration's snowball
    n_retrieved: int  # new candidates from primary retrieval this iteration
    n_snowball_fwd: int  # promoted forward-snowball candidates
    n_snowball_bwd: int  # promoted backward-snowball candidates
    n_judged: int  # candidates actually judged this iteration
    stop_reason: StopReason  # why this iteration's adaptive_load stopped


@dataclass
class BroadSearchResult:
    ranked: list[Candidate]  # final §4.3 Step-5 ordering, capped at final_result_cap
    pool: list[Candidate]  # the full deduped candidate pool (judged + unjudged)
    iterations: list[IterationStat] = field(default_factory=list)

    @property
    def n_judged(self) -> int:
        return sum(c.level is not None for c in self.pool)


def _tag(cands: list[Candidate], origin: str) -> list[Candidate]:
    """Stamp the bandit-arm origin on freshly-retrieved candidates (mechanism + query)."""
    for c in cands:
        c.origins = {origin}
    return cands


def _seeds(pool: list[Candidate]) -> list[Candidate]:
    """Snowball seeds = papers judged Highly/Perfect (level >= 2), spec §4.3 Step 3."""
    return [c for c in pool if (c.level or 0) >= 2]


def _exemplars(pool: list[Candidate], k: int = 5) -> list[Candidate]:
    """Top judged-relevant papers, highest level first — the reformulation exemplars (§4.3 Step 3)."""
    judged = [c for c in pool if c.level is not None and c.level >= 2]
    judged.sort(key=lambda c: c.level or 0, reverse=True)
    return judged[:k]


async def _retrieve_primary(
    source: SourceClient,
    caps: Capabilities,
    keyword_queries: list[str],
    dense_queries: list[str],
    iteration: int,
    *,
    with_suggestions: bool,
    content: str,
    timer: StageTimer,
) -> list[Candidate]:
    """Run the primary retrieval legs for one iteration, tagging each with its bandit origin.

    Keyword always (over `keyword_queries`); dense only when `caps.has_dense` (Arm C, source-forced
    §4.3 diff #1), over its OWN `dense_queries` — the two legs are formulated separately because
    they want different query idioms (PF's two-agent split; FINDINGS 2026-06-23). Parametric
    suggestions once (iteration 0). Each (mechanism, query) is a distinct bandit arm.

    Timing: keyword/dense search → `retrieve` (API); `suggest` → `formulate` (it is an LLM
    generation call, grouped with the other non-judge LLM work).
    """
    out: list[Candidate] = []
    for qi, q in enumerate(keyword_queries):
        with timer.track("retrieve"):
            kw = await source.keyword_search(q, CONFIG.budgets.s2_relevance_top_k)
        out += _tag(kw, f"keyword:i{iteration}q{qi}")
    if caps.has_dense:
        for qi, q in enumerate(dense_queries):
            with timer.track("retrieve"):
                dense = await source.dense_search(q, CONFIG.budgets.dense_top_k)
            out += _tag(dense, f"dense:i{iteration}q{qi}")
    if with_suggestions:
        with timer.track("formulate"):
            sug = await source.suggest(content, CONFIG.budgets.n_parametric_suggestions)
        out += _tag(sug, "suggest")
    return out


async def _snowball(
    source: SourceClient,
    caps: Capabilities,
    seeds: list[Candidate],
    iteration: int,
    timer: StageTimer,
) -> tuple[list[Candidate], list[Candidate]]:
    """Forward + backward snowball from seeds, scored + promoted top-k each (snowball.py).

    Timing: the citations/references API calls → `snowball`; the (pure) promote/scoring stays in
    `other_s`."""
    fwd_edges, bwd_edges = [], []
    for seed in seeds:
        with timer.track("snowball"):
            citing = await source.fetch_citations(
                seed.paper_id
            )  # forward: papers citing the seed
            refs = await source.fetch_references(
                seed.paper_id
            )  # backward: the seed's references
        fwd_edges += build_edges(seed, citing)
        bwd_edges += build_edges(seed, refs)
    fwd = _tag(
        promote_snowball(fwd_edges, "forward", caps), f"snowball_fwd:i{iteration}"
    )
    bwd = _tag(
        promote_snowball(bwd_edges, "backward", caps), f"snowball_bwd:i{iteration}"
    )
    return fwd, bwd


async def broad_search(
    source: SourceClient,
    caps: Capabilities,
    analysis: QueryAnalysis,
    *,
    judge_fn: JudgeFn,
    rerank_fn: RerankFn | None = None,
    seed: int = 0,
    timer: StageTimer | None = None,
) -> BroadSearchResult:
    """Run the shared broad-search loop for one query and return the ranked result + stats.

    `analysis` is the Step-0 query analysis (query_analysis.py): `analysis.content` drives
    retrieval, `analysis.intent` drives the Step-5 ranking weights. `judge_fn` judges a batch in
    place (sets cand.level); `rerank_fn` (optional) sets cand.rerank_score before ranking.
    `timer` (optional) accumulates per-stage wall-time; the injected `judge_fn` shares the SAME
    timer to record the `judge` bucket (omit → a throwaway timer, zero cost).
    """
    timer = timer or StageTimer()
    pool: list[Candidate] = []
    stats: list[IterationStat] = []
    judged_total = 0

    # Each leg is formulated in its own idiom (PF's two-agent split): keyword always; dense only
    # when the source has a dense leg. The source decides the idiom (boolean/keyword vs dense NL).
    n_q = CONFIG.budgets.n_initial_queries
    with timer.track("formulate"):
        kw_queries = await source.formulate_keyword_queries(analysis.content, n_q)
        dense_queries = (
            await source.formulate_dense_queries(analysis.content, n_q)
            if caps.has_dense
            else []
        )

    for it in range(CONFIG.budgets.n_search_iterations):
        # --- 1. RETRIEVE (primary) ----------------------------------------- #
        if it == 0:
            retrieved = await _retrieve_primary(
                source,
                caps,
                kw_queries,
                dense_queries,
                it,
                with_suggestions=True,
                content=analysis.content,
                timer=timer,
            )
        else:
            # Closed loop: reformulate each leg from the best judged-relevant papers as exemplars.
            exemplars = _exemplars(pool)
            with timer.track("formulate"):
                ref_kw = await source.reformulate_keyword_queries(
                    analysis.content, exemplars, n_q
                )
                ref_dense = (
                    await source.reformulate_dense_queries(
                        analysis.content, exemplars, n_q
                    )
                    if caps.has_dense
                    else []
                )
            retrieved = await _retrieve_primary(
                source,
                caps,
                ref_kw,
                ref_dense,
                it,
                with_suggestions=False,
                content=analysis.content,
                timer=timer,
            )

        # --- 2. EXPAND (snowball followup) --------------------------------- #
        seeds = _seeds(pool)  # judged in earlier iterations (empty on iter 0)
        fwd, bwd = await _snowball(source, caps, seeds, it, timer)

        # --- 3. JUDGE (adaptive, fresh short-circuit per iteration) -------- #
        pool = dedupe(pool + retrieved + fwd + bwd)
        unjudged = [c for c in pool if c.level is None]
        remaining = CONFIG.budgets.judge_quota - judged_total
        iter_quota = min(CONFIG.budgets.per_iteration_judge_budget, remaining)

        if unjudged and iter_quota > 0:
            judged, reason = await adaptive_load(
                unjudged,
                judge_fn,
                quota=iter_quota,
                shortcircuit=HighlyRelevantShortcircuit(),
                seed=seed + it,  # vary the RNG per iteration but stay reproducible
            )
            judged_total += len(judged)
        else:
            judged, reason = [], "quota"

        stats.append(
            IterationStat(
                iteration=it,
                n_seeds=len(seeds),
                n_retrieved=len(retrieved),
                n_snowball_fwd=len(fwd),
                n_snowball_bwd=len(bwd),
                n_judged=len(judged),
                stop_reason=reason,
            )
        )
        logger.info(
            "Iter %d: retrieved=%d snowball(fwd=%d,bwd=%d) judged=%d (%s); total judged=%d",
            it,
            len(retrieved),
            len(fwd),
            len(bwd),
            len(judged),
            reason,
            judged_total,
        )
        if judged_total >= CONFIG.budgets.judge_quota:
            logger.info(
                "Total judging quota (%d) reached; stopping iterations.",
                CONFIG.budgets.judge_quota,
            )
            break

    # --- 5. RANK (once) ---------------------------------------------------- #
    if rerank_fn is not None:
        with timer.track("rerank"):
            await rerank_fn(pool)
    ranked = rank_candidates(pool, analysis, caps)
    return BroadSearchResult(ranked=ranked, pool=pool, iterations=stats)
