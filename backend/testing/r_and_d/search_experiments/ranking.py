"""Step 5 — final ranking blend + Cohere rerank + §4.7 sensitivity sweep (Arms B & C).

Ports PF `agents/.../common/sorting.py` (the sigmoids + `content_relevance_score`) and
`agents/.../external_api/rerank/cohere.py` (the reranker client). The blend is:

    content = 0.9·judge + 0.075·cohere_rerank [+ 0.025·sigmoid(num_snippets)]   (snippet: Arm C only)
    score   = w_content·content + w_recent·recency + w_central·centrality

where (w_content, w_recent, w_central) come from the Step-0 intent (query_analysis.py) via
the §4.3 weight table. The recency/centrality terms are DIRECTION-aware: the intent's
"recent"/"early" (and "central"/"less") selects PF's first/last sigmoid — see
`recency_score`/`centrality_score`.

> ★ Spec shorthand vs PF mechanism. Spec §4.3 Step 5 writes the recency/centrality terms as
> `sigmoid(year − baseline_year)` / `sigmoid(log(cited+1))`, but that is illustrative
> shorthand and is mis-calibrated (the newest paper would score only 0.5, and the citation
> sigmoid is ≥0.5 for every paper). "This spec wins" (§4.3a) is scoped to the OPERATING POINT
> (budgets, top-k, model names) — the sigmoid SHAPE is mechanism, and the spec tags
> `common/sorting.py` as the ranking source of truth. So we port PF's `recent_first/last` and
> `central_first/last` sigmoids verbatim (constants and all): recency half-life ~7 years
> (`center_shift=7.0, steepness=0.7`), centrality centred at 50 cites. The one adaptation:
> `year_max` defaults to the pool's newest year (self-relative + offline-deterministic),
> where PF uses `datetime.now().year`. (Spec wording to be corrected — flagged, like the BTS
> short-circuit discrepancy, so it's a deliberate port, not a silent divergence.)

> ★ Two seams, one pure. The ONLY networked piece here is `cohere_rerank` (async, cached by
> (query_id, paper_id) per spec §7 — so reruns are free and the experiment is resumable).
> Everything else — `score`, `rank_candidates`, `rerank_sweep` — is a pure function over
> fields already on the Candidate (`relevance_score` or `level`, `rerank_score`, `num_snippets`,
> `year`, `cited_by_count`). That mirrors judge.py (pure `score_row` vs the LLM call) and is what
> keeps the blend offline-testable and usable with `rerank_score=0` when no Cohere key is set.

The four source-forced B/C differences (§4.3) that touch ranking are read from `Capabilities`:
only `caps.has_snippets` matters here — Arm C adds the +0.025 snippet term, Arm B drops it
(no re-normalisation, PF `weighted_average_sort`; spec §4.3 diff #3).

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from ranking import cohere_rerank, rank_candidates, rerank_sweep
    from query_analysis import analyse_query
    a = analyse_query("q001", "latest evidence on free school meals and attainment")
    await cohere_rerank("q001", a.content, candidates)   # sets cand.rerank_score (cached)
    ranked = rank_candidates(candidates, a, caps)         # pure: blended order, capped at 250
    variants = rerank_sweep(candidates, a, caps)          # {variant_name: [paper_id, ...]}
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from config import CONFIG

if TYPE_CHECKING:  # avoid import cost / cycles at runtime; only for type hints
    from query_analysis import QueryAnalysis
    from source import Candidate, Capabilities

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"
RERANK_DIR = RESULTS_DIR / "rerank"


# --------------------------------------------------------------------------- #
# Sigmoids (ported verbatim from PF sorting.py:393-398, 469-472)
# --------------------------------------------------------------------------- #
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def sigmoid(x: float, center_shift: float = 0.0, steepness: float = 1.0) -> float:
    """PF `sigmoid`: logistic of (x + center_shift)·steepness."""
    return _sigmoid((x + center_shift) * steepness)


def num_snippets_score_sigmoid(num_snippets: int) -> float:
    """PF `num_snippets_score_sigmoid`: 0 if no snippets, else a saturating count score."""
    if num_snippets <= 0:
        return 0.0
    return sigmoid(math.log(num_snippets**2 + 0.1))


# --------------------------------------------------------------------------- #
# Direction-aware recency / centrality (ported verbatim from PF sorting.py)
# --------------------------------------------------------------------------- #
# PF sorting.py:434-447. center_shift=7.0 -> half-way point ~7 years before year_max;
# returns 1.0 for the newest (year >= year_max), 0.0 for unknown/non-positive years.
def recent_first_score_sigmoid(
    year: int | None,
    year_max: int | None,
    center_shift: float = 7.0,
    steepness: float = 0.7,
) -> float:
    if year_max is None or not year or year <= 0:
        return 0.0
    if year >= year_max:
        return 1.0
    return sigmoid(year, center_shift=-(year_max - center_shift), steepness=steepness)


# PF sorting.py:450-466. NOTE: NOT 1 - recent_first — PF gives "early" its own gentler shape
# (center_shift=20.0, steepness=0.15). Returns 0.0 for the newest, 1.0 for year<=0.
def recent_last_score_sigmoid(
    year: int | None,
    year_max: int | None,
    center_shift: float = 20.0,
    steepness: float = 0.15,
) -> float:
    if year_max is None:
        return 0.0
    if year is None or year >= year_max:
        return 0.0
    if year <= 0:
        return 1.0
    return 1 - sigmoid(
        year, center_shift=-(year_max - center_shift), steepness=steepness
    )


# PF sorting.py:401-416. Citation sigmoid centred at 50 cites (center_shift=-log(51)).
def central_first_score_sigmoid(
    citation_count: int | None,
    center_citation_count: int = 50,
    steepness: float = 1.8,
) -> float:
    if not citation_count or citation_count <= 0 or center_citation_count <= 0:
        return 0.0
    return sigmoid(
        math.log(citation_count + 1),
        center_shift=-math.log(center_citation_count + 1),
        steepness=steepness,
    )


# PF sorting.py:419-431. 1 - central_first, but returns 1.0 for the uncited (PF behaviour).
def central_last_score_sigmoid(
    citation_count: int | None,
    center_citation_count: int = 50,
    steepness: float = 1.8,
) -> float:
    if not citation_count or citation_count <= 0 or center_citation_count <= 0:
        return 1.0
    return 1 - central_first_score_sigmoid(
        citation_count, center_citation_count, steepness
    )


def recency_score(
    year: int | None,
    baseline_year: int | None,
    direction: Literal["recent", "early"] | None,
) -> float:
    """Direction-aware recency (PF `recency_score_func` selection): "early" -> recent_last,
    otherwise (recent / no preference) -> recent_first. `baseline_year` is PF's `year_max`."""
    if direction == "early":
        return recent_last_score_sigmoid(year, baseline_year)
    return recent_first_score_sigmoid(year, baseline_year)


def centrality_score(
    cited_by_count: int,
    direction: Literal["central", "less"] | None,
) -> float:
    """Direction-aware centrality (PF `centrality_score_func` selection): "less" ->
    central_last, otherwise (central / no preference) -> central_first."""
    if direction == "less":
        return central_last_score_sigmoid(cited_by_count)
    return central_first_score_sigmoid(cited_by_count)


# --------------------------------------------------------------------------- #
# Content blend (PF sorting.py:482-505 content_relevance_score)
# --------------------------------------------------------------------------- #
def content_relevance_score(
    relevance_judgement_score: float,
    rerank_score: float,
    num_snippets: int,
    *,
    include_snippet: bool,
) -> float:
    """`0.9·judge + 0.075·cohere [+ 0.025·sigmoid(num_snippets)]`.

    The snippet term is added only when `include_snippet` (Arm C, `caps.has_snippets`); Arm B
    simply drops it — no re-normalisation (spec §4.3 diff #3, PF `weighted_average_sort`).
    Inputs are clamped to ≥0 exactly as PF does.
    """
    rj = max(relevance_judgement_score, 0.0)
    rerank = max(rerank_score, 0.0)
    b = CONFIG.blend
    score = b.rj_weight * rj + b.rerank_weight * rerank
    if include_snippet:
        score += b.snippet_weight * num_snippets_score_sigmoid(max(num_snippets, 0))
    return score


# --------------------------------------------------------------------------- #
# Per-candidate blended score (pure)
# --------------------------------------------------------------------------- #
def _relevance_judgement_score(cand: Candidate) -> float:
    """The `rj` term for the content blend (PF `_relevance_judgement_score`, sorting.py:512).

    PREFER the continuous weighted-criteria score (`metrics.relevance_criteria_score`, ∈ [0,1]),
    falling back to the bucketed `level/3` only when it's unset. This is what keeps two same-tier
    papers (e.g. continuous 0.70 vs 0.98, both bucketed to level 2) from collapsing to an
    identical `rj` in the §4.3 Step-5 ordering — the granularity PF's ranking deliberately keeps.
    Clamped to ≥0 as PF does.
    """
    if cand.relevance_score is not None:
        return max(cand.relevance_score, 0.0)
    return max((cand.level or 0) / 3.0, 0.0)


def _blended_score(
    cand: Candidate,
    weights: tuple[float, float, float],
    recency_dir: Literal["recent", "early"] | None,
    centrality_dir: Literal["central", "less"] | None,
    caps: Capabilities,
    baseline_year: int | None,
    *,
    include_rerank: bool = True,
    include_snippet: bool | None = None,
) -> float:
    """The Step-5 blend for one candidate. `include_rerank`/`include_snippet` let the §4.7
    sweep toggle the Cohere and snippet sub-terms off; `include_snippet=None` defers to caps."""
    if include_snippet is None:
        include_snippet = caps.has_snippets
    w_content, w_recent, w_central = weights
    rj = _relevance_judgement_score(
        cand
    )  # continuous score, else level/3 (PF sorting.py:512)
    rerank = cand.rerank_score if include_rerank else 0.0
    content = content_relevance_score(
        rj, rerank, cand.num_snippets, include_snippet=include_snippet
    )
    rec = recency_score(cand.year, baseline_year, recency_dir)
    cen = centrality_score(cand.cited_by_count, centrality_dir)
    return w_content * content + w_recent * rec + w_central * cen


def score(
    cand: Candidate,
    analysis: QueryAnalysis,
    caps: Capabilities,
    baseline_year: int | None,
) -> float:
    """Final blended score for one candidate under the query's live intent (pure)."""
    return _blended_score(
        cand,
        analysis.intent.weights(),
        analysis.intent.recency,
        analysis.intent.centrality,
        caps,
        baseline_year,
    )


def _default_baseline_year(cands: list[Candidate]) -> int | None:
    """Recency baseline = the pool's newest year (PF defaults year_max to 'now'; the pool's
    own max keeps the score self-relative and offline-deterministic)."""
    years = [c.year for c in cands if c.year]
    return max(years) if years else None


def rank_candidates(
    cands: list[Candidate],
    analysis: QueryAnalysis,
    caps: Capabilities,
    baseline_year: int | None = None,
) -> list[Candidate]:
    """Sort candidates by the Step-5 blend (desc), capped at `final_result_cap` (250).

    Pure: reads `cand.rerank_score` (set earlier by `cohere_rerank`, or 0 if no key) and the
    judge `level`. Run `cohere_rerank` first to populate the Cohere term; the blend is still
    valid without it (just `0.9·judge` + recency/centrality), so a missing key degrades
    gracefully rather than erroring.
    """
    if baseline_year is None:
        baseline_year = _default_baseline_year(cands)
    ranked = sorted(
        cands, key=lambda c: score(c, analysis, caps, baseline_year), reverse=True
    )
    return ranked[: CONFIG.budgets.final_result_cap]


# --------------------------------------------------------------------------- #
# §4.7 ranking-weight / rerank-term sensitivity sweep (pure, no API)
# --------------------------------------------------------------------------- #
def rerank_sweep(
    cands: list[Candidate],
    analysis: QueryAnalysis,
    caps: Capabilities,
    baseline_year: int | None = None,
) -> dict[str, list[str]]:
    """Re-rank the ALREADY-judged-and-reranked pool under weight-vector variants × the
    Cohere/snippet sub-terms toggled on/off (spec §4.7). Pure — re-rank only, no re-retrieval
    and no API: it reuses the `rerank_score` already on each Candidate.

    Returns {variant_name: [paper_id ranked desc, capped at 250]}. Variant names look like
    "recent|rerank=on|snippet=off". The snippet axis only varies for sources that have it
    (`caps.has_snippets`) — for Arm B it is pinned off, so the sweep is weights × {rerank}.
    Recency/centrality DIRECTIONS stay at the query's live intent; only the WEIGHTS sweep.
    """
    if baseline_year is None:
        baseline_year = _default_baseline_year(cands)
    snippet_options = [True, False] if caps.has_snippets else [False]
    cap = CONFIG.budgets.final_result_cap

    out: dict[str, list[str]] = {}
    for wkey, weights in CONFIG.blend.intent_weights.items():
        for include_rerank in (True, False):
            for include_snippet in snippet_options:
                name = (
                    f"{wkey}|rerank={'on' if include_rerank else 'off'}"
                    f"|snippet={'on' if include_snippet else 'off'}"
                )
                ranked = sorted(
                    cands,
                    key=lambda c: _blended_score(
                        c,
                        weights,
                        analysis.intent.recency,
                        analysis.intent.centrality,
                        caps,
                        baseline_year,
                        include_rerank=include_rerank,
                        include_snippet=include_snippet,
                    ),
                    reverse=True,
                )
                out[name] = [c.paper_id for c in ranked[:cap]]
    return out


# --------------------------------------------------------------------------- #
# Cohere rerank — the only networked piece (async, cached by (query_id, paper_id))
# --------------------------------------------------------------------------- #
def _rerank_doc_text(cand: Candidate) -> str:
    """Document text for the reranker: title + abstract (PF reranks (query, title+abstract))."""
    title = cand.title or ""
    body = cand.abstract or ""
    return f"{title}\n\n{body}".strip() or cand.paper_id


def _rerank_cache_path(query_id: str) -> Path:
    return RERANK_DIR / f"{query_id}.json"


def load_rerank_cache(query_id: str) -> dict[str, float]:
    """{paper_id: cohere_score} cached for a query (empty if none yet)."""
    path = _rerank_cache_path(query_id)
    if not path.exists():
        return {}
    return {str(k): float(v) for k, v in json.loads(path.read_text()).items()}


def _save_rerank_cache(query_id: str, scores: dict[str, float]) -> None:
    RERANK_DIR.mkdir(parents=True, exist_ok=True)
    _rerank_cache_path(query_id).write_text(json.dumps(scores, indent=2))


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def cohere_rerank(
    query_id: str,
    query_text: str,
    cands: list[Candidate],
    *,
    force: bool = False,
) -> None:
    """Set `cand.rerank_score` for every candidate from Cohere `rerank-english-v3.0`, in place.

    Cached by (query_id, paper_id) at results/rerank/{query_id}.json (spec §7) — only papers
    not already cached are sent, so reruns and cross-arm pooling cost nothing. Batched ≤500
    docs/request (PF cohere.py). If COHERE_API_KEY is unset, logs a warning and leaves every
    `rerank_score` at 0 — the blend still works (graceful degradation), it just loses the
    0.075 term. Query text is the Step-0 `content` (metadata-stripped), matching what the
    blend ranks against.
    """
    cache = {} if force else load_rerank_cache(query_id)
    todo = [c for c in cands if c.paper_id not in cache]

    api_key = os.environ.get("COHERE_API_KEY")
    if todo and not api_key:
        logger.warning(
            "COHERE_API_KEY unset; skipping rerank for query %s (rerank_score stays 0 for "
            "%d candidate(s) — blend degrades to judge + recency/centrality)",
            query_id,
            len(todo),
        )
    elif todo:
        import cohere  # lazy: keep the module importable without the dep installed

        client = cohere.AsyncClient(api_key, timeout=60)
        try:
            for batch in _chunked(todo, CONFIG.rerank_batch_size):
                docs = [_rerank_doc_text(c) for c in batch]
                resp = await client.rerank(
                    query=query_text,
                    documents=docs,
                    model=CONFIG.models.rerank_model,
                    return_documents=False,
                    request_options={"max_retries": 3},
                )
                for r in resp.results:
                    cache[batch[r.index].paper_id] = float(r.relevance_score)
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                await close()
        _save_rerank_cache(query_id, cache)
        logger.info(
            "Reranked %d new candidate(s) for query %s (%d cached total)",
            len(todo),
            query_id,
            len(cache),
        )

    for c in cands:
        c.rerank_score = cache.get(c.paper_id, 0.0)
