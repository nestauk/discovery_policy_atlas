"""Arm A — the production v2 baseline (spec §4.2, Phase 6).

Arm A is NOT the shared broad_search loop; it reproduces production's single-pass retrieval by
COMPOSING the same production pieces Arm B wraps (parity — so A→B isolates the agentic loop, not
"orchestrator vs composed"; see FINDINGS 2026-06-25). Pipeline per curated query_text:

  1. Formulate — `ReferencesService.generate_boolean_queries_multi` (n=5, prod temperature): current
     production is MULTI-query (BOOLEAN_QUERY_GENERATION_MODE="multi"), so Arm A is the LIVE baseline,
     not the legacy single-query one (deliberate §4.2 deviation, decided 2026-06-25). temp>0 is
     non-deterministic → the formulation is CACHED per query so a run is reproducible.
  2. Fan out each boolean into base / systematic_review / RCT variants per OPENALEX_ENABLE_RCT_SYSREV_FANOUT.
  3. Search each variant via `OpenAlexService.search` (max_results=200, min_citations=DEFAULT_MIN_CITATIONS;
     no date filter — time was excluded from query_text → recency intent, all arms skip it).
  4. Combine, dedup on paper_id (OpenAlex id — the key the whole harness uses; DOI-hash dedup is a
     logged finding, not built), then sort by production's native order: relevance_score desc,
     variant_priority asc (SR>RCT>base on ties). relevance_score = OpenAlex lexical score, NOT the LLM judge.
  5. NO relevance screen (v2's screen is OFF, §4.2) — the frozen experiment judge scores the candidates.

Judging: top-`judge_quota` (250) in ranked order via the shared `judge.judge_papers` (criteria are
arm-independent; the cross-arm cache judges each paper once). Per-query ranked+judged results persist to
results/arms/arm_a/{query_id}.json for Phase 9 to pool (recall@k_est needs the cross-arm normalizer).

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from arms.arm_a import run_query
    from queries.loader import load_queries
    res = asyncio.run(run_query(load_queries()[0]))   # retrieves + judges + persists
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from _backend import (
    get_boolean_clauses,
    get_openalex_service,
    get_references_service,
    get_settings,
)
from _timing import StageTimer, stage_timings
from config import CONFIG
from queries.loader import Query, load_queries
from retrieval import _cache
from retrieval._fanout import fanout  # shared SR/RCT expansion (Arms A + B)
from retrieval.openalex_client import (  # canonical row→Candidate + shared wildcard strip
    _row_to_candidate,
    strip_openalex_wildcards,
)
from source import Candidate

logger = logging.getLogger(__name__)

ARM_A_MAX_RESULTS = 200  # spec §4.2 (overrides prod config default of 50)
_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "arms" / "arm_a"


# --------------------------------------------------------------------------- #
# Pure helpers (offline-testable — no network, no app.* import)
# --------------------------------------------------------------------------- #
def _dedupe_and_sort(rows: list[dict], variant_priority: dict[str, int]) -> list[dict]:
    """Production's native ordering: sort by relevance_score desc, variant_priority asc, then
    drop duplicate paper ids keeping the first (= the highest-relevance / best-variant copy).

    Each row needs `id`, `relevance_score`, `variant`. Stable sort, so equal keys keep input order.
    """
    ordered = sorted(
        rows,
        key=lambda r: (
            -float(r.get("relevance_score") or 0),
            variant_priority.get(r.get("variant"), 99),
        ),
    )
    seen: set[str] = set()
    out: list[dict] = []
    for r in ordered:
        rid = str(r.get("id") or "")
        if rid and rid not in seen:
            seen.add(rid)
            out.append(r)
    return out


def _rows_from_df(df, variant: str) -> list[dict]:
    """OpenAlexService.search DataFrame → row dicts, KEEPING relevance_score + variant (the ordering
    signals the shared `_df_to_rows` discards). `reference_count` is unavailable from search → 0."""
    if df is None or df.empty:
        return []
    return [
        {
            "id": r.get("id", ""),
            "title": r.get("title"),
            "abstract": r.get("abstract"),
            "year": r.get("publication_year"),
            "cited_by_count": r.get("cited_by_count", 0),
            "reference_count": 0,
            "doi": r.get("doi"),
            "relevance_score": r.get("relevance_score", 0) or 0,
            "variant": variant,
        }
        for r in df.to_dict("records")
    ]


# --------------------------------------------------------------------------- #
# Arm A
# --------------------------------------------------------------------------- #
@dataclass
class ArmARetrieval:
    booleans: list[str]  # the multi-query booleans (pre-fanout), cached per query
    candidates: list[Candidate]  # deduped + production-ordered (ranking for recall@k)


class ArmA:
    """Production v2 baseline retriever (Arm A). Lazy-imports app.* so the pure helpers above stay
    import-clean (same convention as openalex_client)."""

    name = "arm_a"

    def __init__(self):
        settings = get_settings()
        (
            self._sr_clause,
            self._rct_clause,
            self._variant_priority,
        ) = get_boolean_clauses()
        self._fanout_enabled = settings.OPENALEX_ENABLE_RCT_SYSREV_FANOUT
        self._n_runs = settings.BOOLEAN_QUERY_N_RUNS
        self._temperature = settings.BOOLEAN_QUERY_TEMPERATURE
        self._model = settings.BOOLEAN_QUERY_MODEL
        self._min_citations = settings.DEFAULT_MIN_CITATIONS
        self._svc = (
            get_openalex_service()
        )  # configures PyAlex global (polite-pool email + key)
        # ReferencesService.__init__ mkdir's an export dir; point it at results/ (never touched here).
        self._refs = get_references_service(str(_RESULTS_DIR / "_refs_export"))
        # Count variant searches skipped after OpenAlex 500/504s an over-broad boolean. Production
        # tolerates these via gather(return_exceptions=True) (references.py:643); Arm A composes the
        # pieces but had dropped that resilience — mirror it so a monster boolean doesn't sink the query.
        self.n_search_failures = 0

    async def formulate(self, query_text: str) -> list[str]:
        """N multi-query booleans (current prod), cached per query so temp>0 stays reproducible."""
        key = {
            "q": query_text,
            "n": self._n_runs,
            "temp": self._temperature,
            "model": self._model,
        }
        hit = _cache.load("arm_a.boolean", key)
        if hit is not None:
            logger.info("Arm A boolean cache hit for %r", query_text[:60])
            return hit
        booleans = await self._refs.generate_boolean_queries_multi(
            query_text, n_runs=self._n_runs, temperature=self._temperature
        )
        _cache.save("arm_a.boolean", key, booleans)
        return booleans

    async def retrieve(
        self, query_text: str, timer: StageTimer | None = None
    ) -> ArmARetrieval:
        """Timing: the boolean formulation LLM call → `formulate`; each OpenAlex search → `retrieve`.
        Arm A has no snowball/dense/rerank legs, so those buckets stay 0 (the honest picture)."""
        timer = timer or StageTimer()
        with timer.track("formulate"):
            booleans = await self.formulate(query_text)
        rows: list[dict] = []
        seen_queries: set[
            str
        ] = (
            set()
        )  # don't search the same variant string twice (prod parity, refs.py:502)
        for base in booleans:
            for variant, q in fanout(
                base, self._fanout_enabled, self._sr_clause, self._rct_clause
            ):
                if q in seen_queries:
                    continue
                seen_queries.add(q)
                with timer.track("retrieve"):
                    try:
                        df = await self._svc.search(
                            query=strip_openalex_wildcards(
                                q
                            ),  # drop wildcards the prompt forbids but gpt-4.1 emits
                            max_results=ARM_A_MAX_RESULTS,
                            min_citations=self._min_citations,
                        )
                    except Exception as e:
                        # Skip an un-servable variant (OpenAlex 500/504s an over-broad boolean even
                        # after retries) rather than sink the query — production parity (references.py:643).
                        self.n_search_failures += 1
                        logger.error(
                            "Arm A OpenAlex search failed for %s variant (skipping): %s",
                            variant,
                            e,
                        )
                        continue
                rows += _rows_from_df(df, variant)
        ranked_rows = _dedupe_and_sort(rows, self._variant_priority)
        candidates = [_row_to_candidate(r) for r in ranked_rows]
        return ArmARetrieval(booleans=booleans, candidates=candidates)


# --------------------------------------------------------------------------- #
# Run + persist (retrieve → judge top-250 → store ranked+judged for Phase 9)
# --------------------------------------------------------------------------- #
@dataclass
class ArmAResult:
    query_id: str
    query_text: str
    booleans: list[str]
    n_retrieved: int
    n_judged: int
    ranked: list[dict] = field(
        default_factory=list
    )  # [{paper_id, rank, level}], native order
    timings: dict = field(
        default_factory=dict
    )  # _timing.stage_timings (latency instrumentation)
    n_search_failures: (
        int
    ) = 0  # variant searches skipped after OpenAlex 500/504 (parity w/ prod)


async def run_query(q: Query, *, persist: bool = True, seed: int = 0) -> ArmAResult:
    """Retrieve for one query, judge the top-`judge_quota` in ranked order, persist the result.

    Signature matches arm_b/arm_c.run_query(q, …) so callers (the pilot, run_all) treat all three
    arms uniformly; `seed` is accepted for that uniformity but unused (Arm A has no RNG/loop).
    """
    from retrieval.enrich import (
        classify_text_basis,
    )  # sets text_basis (abstract vs title_only, §4.4)

    timer = (
        StageTimer()
    )  # formulate/retrieve from arm.retrieve; judge below; no snowball/rerank
    t0 = time.monotonic()
    arm = ArmA()
    retr = await arm.retrieve(q.query_text, timer)
    classify_text_basis(retr.candidates)

    quota = CONFIG.budgets.judge_quota
    to_judge = retr.candidates[:quota]
    papers = [
        {
            "paper_id": c.paper_id,
            "title": c.title,
            "abstract": c.abstract,
            "text_basis": c.text_basis,
        }
        for c in to_judge
    ]

    from judge import get_cached_levels, judge_papers  # lazy (pulls backend env)

    with timer.track("judge"):
        await judge_papers(q.query_id, q.query_text, papers)
    levels = get_cached_levels(q.query_id)
    total_s = time.monotonic() - t0

    result = ArmAResult(
        query_id=q.query_id,
        query_text=q.query_text,
        booleans=retr.booleans,
        n_retrieved=len(retr.candidates),
        n_judged=len(to_judge),
        ranked=[
            {"paper_id": c.paper_id, "rank": i, "level": levels.get(c.paper_id)}
            for i, c in enumerate(retr.candidates)
        ],
        timings=stage_timings(total_s, timer, len(to_judge)),
        n_search_failures=arm.n_search_failures,
    )
    if persist:
        _persist(result)
    return result


def _persist(result: ArmAResult) -> None:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"{result.query_id}.json"
    out.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    logger.info(
        "Arm A: wrote %s (%d retrieved, %d judged)",
        out,
        result.n_retrieved,
        result.n_judged,
    )


async def run_all() -> list[ArmAResult]:
    """Run Arm A over the whole curated query set (expensive: live OpenAlex + ~250 judgements/query)."""
    results = []
    for q in load_queries():
        logger.info("Arm A: running %s", q.query_id)
        results.append(await run_query(q))
    return results
