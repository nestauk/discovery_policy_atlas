"""Arm B source client — `OpenAlexSource`, the SourceClient for the OpenAlex corpus (spec §4.3).

This is the concrete implementation the Phase-3b `broad_search` loop drives for Arm B. It is a
*thin extension* of the production `OpenAlexService` (spec §5): keyword retrieval reuses
`OpenAlexService.search` verbatim (so Arm B searches OpenAlex exactly as production does), and
the two things production doesn't expose — forward citations (`cites:` filter) and backward
references (`referenced_works`, batch-resolved) — are added here via raw PyAlex `Works`.

`Capabilities` are all-False — the four source-forced differences (§4.3) fall out of that:
  - `has_dense=False`        → the core never calls `dense_search` (no S2 snippet leg).
  - `has_influential=False`  → snowball.py drops the +0.1·is_influential forward term.
  - `has_snippets=False`     → ranking.py drops the +0.025 snippet term.
  - `native_abstracts=False` → abstracts come from OpenAlex reinversion; the tail is flagged
                               title-only (enrich.classify_text_basis, §4.4 — no resolver).

Formulation is the **query-formulation decision (spec §4.3, 2026-06-21)**: `formulate_keyword_queries`
and `reformulate_keyword_queries` delegate to v2's PRODUCTION boolean generator
(`ReferencesService.generate_boolean_queries_multi`) — the *same* generator Arm A uses — so A→B
isolates the agentic loop, not the formulation idiom. `reformulate_keyword_queries` keeps PF's strategy
(reformulate from judged exemplars) by folding the top exemplar titles into the question text.
OpenAlex has no dense leg, so the dense formulation methods raise NotImplementedError (never called).

> Sync-PyAlex-in-async note: like the production `OpenAlexService.search` (an `async def` whose
> body calls blocking PyAlex `paginate`), the graph-walk methods here call PyAlex synchronously
> inside `async def`. That briefly blocks the event loop — acceptable for a single-query research
> harness, and every call is cached (`retrieval._cache`) so reruns don't pay it again.

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from retrieval.openalex_client import OpenAlexSource
    src = OpenAlexSource()
    qs = asyncio.run(src.formulate_keyword_queries("effect of free school meals on attainment", 5))
    cands = asyncio.run(src.keyword_search(qs[0], 200))
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from _backend import (
    get_boolean_clauses,
    get_openalex_service,
    get_references_service,
    get_sanitize_query,
    get_settings,
    get_works_cls,
)
from config import CONFIG
from retrieval import _cache
from retrieval._fanout import fanout  # shared SR/RCT expansion (Arms A + B)
from retrieval.suggest import SuggestedPaper, ground_suggestions, suggest_titles
from core.source import Candidate, Capabilities

# NB: `app.*` and `pyalex` are LAZY-imported inside __init__ / methods (same convention as
# judge.py / ranking.py / query_analysis.py) so the pure dict→Candidate mappers below stay
# importable and unit-testable without backend env vars or a configured PyAlex.

logger = logging.getLogger(__name__)

# Bound the per-seed citation-graph fan-out. Snowball promotes only the top ~200 each direction
# (CONFIG.budgets.snowball_top_k), so fetching beyond that is wasted API calls / rate budget.
_GRAPH_FETCH_CAP = CONFIG.budgets.snowball_top_k
_REFERENCES_RESOLVE_CHUNK = 50  # OpenAlex |-OR id filter cap per request

# Single JSON row schema both retrieval paths emit, so dict→Candidate has one mapper:
#   {id, title, abstract, year, cited_by_count, reference_count, doi}
_NO_ABSTRACT = (
    "no abstract available"  # OpenAlexService.search sentinel (lower-cased compare)
)


def _clean_abstract(abstract: str | None) -> str | None:
    """Map OpenAlex's missing-abstract sentinel / blanks to None so the judge flags title-only."""
    a = (abstract or "").strip()
    return None if not a or a.lower() == _NO_ABSTRACT else a


def strip_openalex_wildcards(query: str) -> str:
    """Remove `*`/`?` wildcards from a boolean before it hits OpenAlex (used by Arms A + B).

    The v2 boolean-gen prompt forbids wildcards (app/services/analysis/prompts.py: "DO NOT use
    wildcards"), but gpt-4.1 occasionally emits one anyway (e.g. "agricultur*"), and OpenAlex's
    stemmed `title_and_abstract.search` field 400s on wildcards (FINDINGS 2026-06-26). Dropping the
    wildcard char leaves the stem ("agricultur"), which the stemmed field still matches — so it's
    semantically equivalent for that field, not a lossy hack."""
    return query.replace("*", "").replace("?", "")


def _clean_title_for_filter(title: str | None) -> str:
    """Strip punctuation that breaks OpenAlex's `title.search` filter value (commas/colons delimit
    filters in the URL; parens/dashes/colons in a suggested title 400 the request). OpenAlex title
    search is fuzzy, so reducing to words is safe and still matches the right paper."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title or "")).strip()


def _row_to_candidate(row: dict) -> Candidate:
    """Build a Candidate from the common row schema (origins/level/rank set later by the core)."""
    return Candidate(
        paper_id=str(row["id"]),
        title=row.get("title"),
        abstract=_clean_abstract(row.get("abstract")),
        year=row.get("year"),
        cited_by_count=int(row.get("cited_by_count") or 0),
        reference_count=int(row.get("reference_count") or 0),
        doi=row.get("doi") or None,
    )


def _work_to_row(work: dict) -> dict:
    """Raw PyAlex Work dict → the common row schema. `work["abstract"]` triggers reinversion
    (PyAlex reconstructs from `abstract_inverted_index` on item access — as production search does)."""
    try:
        abstract = work["abstract"]
    except (KeyError, TypeError):
        abstract = None
    refs = work.get("referenced_works") or []
    return {
        "id": work.get("id", ""),
        "title": work.get("title"),
        "abstract": abstract,
        "year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count", 0),
        "reference_count": len(
            refs
        ),  # this work's OWN bibliography size (forward-snowball penalty)
        "doi": work.get("doi"),
    }


def _df_to_rows(df) -> list[dict]:
    """OpenAlexService.search DataFrame → the common row schema (reference_count unavailable → 0;
    backward snowball re-fetches the seed by id, where referenced_works IS present)."""
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
        }
        for r in df.to_dict("records")
    ]


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class OpenAlexSource:
    """`SourceClient` for OpenAlex (Arm B). Capabilities all-False (the four source-forced diffs)."""

    name = "openalex"
    caps = Capabilities(
        has_dense=False,
        has_influential=False,
        has_snippets=False,
        native_abstracts=False,
    )

    def __init__(self, *, min_citations: int | None = None):
        # Backend/PyAlex access via the _backend seam (each accessor lazy-imports app.*/pyalex, so
        # this module stays import-clean for the pure mappers + their offline tests).
        settings = get_settings()
        self._Works = get_works_cls()
        self._sanitize = get_sanitize_query()
        self._boolean_temperature = settings.BOOLEAN_QUERY_TEMPERATURE
        self._boolean_model = (
            settings.BOOLEAN_QUERY_MODEL
        )  # for the formulation cache key
        # SR/RCT fanout (same as Arm A) so A→B doesn't differ on this retrieval feature (FINDINGS 2026-06-25).
        (
            self._sr_clause,
            self._rct_clause,
            _,
        ) = get_boolean_clauses()  # VARIANT_PRIORITY unused here
        self._fanout_enabled = settings.OPENALEX_ENABLE_RCT_SYSREV_FANOUT
        # Instantiating OpenAlexService configures the PyAlex global `config` (polite-pool email
        # + api key from backend settings), which our raw `Works()` graph calls then inherit.
        self._svc = get_openalex_service()
        # ReferencesService.__init__ mkdir's an export dir — point it at our results/ so it never
        # touches the production export path.
        self._refs = get_references_service(
            str(Path(__file__).resolve().parent.parent / "results" / "openalex_export")
        )
        # Citation floor (keyword_search only — snowball/suggest stay unfloored). Defaults to None
        # here; Arm B passes production's DEFAULT_MIN_CITATIONS so the floor is held CONSTANT across
        # A/B/C (2026-06-26). Originally no-floor (recall-oriented) — dropped because the unfloored
        # complex booleans 500'd OpenAlex and the floor difference confounded the ladder. See FINDINGS.
        self._min_citations = min_citations
        # Count boolean-variant searches skipped after exhausting retries (un-servable/over-broad
        # booleans that OpenAlex 500/504s). Production tolerates these via gather(return_exceptions=True)
        # (references.py:643); we mirror that below and surface the count for the persisted result.
        self.n_search_failures = 0

    # --- formulation (v2 boolean generator — the §4.3 query-formulation decision) ---------- #
    async def formulate_keyword_queries(self, content: str, n: int) -> list[str]:
        """N diverse boolean formulations via v2's production generator (same as Arm A).

        OpenAlex has only the keyword leg (no dense), so this is its sole formulation idiom.
        Cached (the generator is temperature>0 → non-deterministic) so a run is reproducible —
        parity with Arm A / Arm C, which also cache their formulations.
        """
        key = {
            "content": content,
            "n": n,
            "temp": self._boolean_temperature,
            "model": self._boolean_model,
        }
        hit = _cache.load("openalex.formulate", key)
        if hit is not None:
            logger.info("OpenAlex formulation cache hit for content=%r", content[:60])
            return hit
        queries = await self._refs.generate_boolean_queries_multi(
            content, n_runs=n, temperature=self._boolean_temperature
        )
        _cache.save("openalex.formulate", key, queries)
        logger.info(
            "Formulated %d boolean queries for content=%r", len(queries), content
        )
        return queries

    async def reformulate_keyword_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        """Reformulate via the SAME v2 generator, folding the best judged exemplars into the
        question text (PF's reformulate-from-exemplars strategy, v2's boolean idiom)."""
        titles = [e.title for e in exemplars if e.title]
        augmented = content
        if titles:
            bullet = "\n".join(f"- {t}" for t in titles)
            augmented = (
                f"{content}\n\nExamples of relevant papers found so far:\n{bullet}"
            )
        return await self.formulate_keyword_queries(augmented, n)

    # No dense leg (caps.has_dense=False) -> the shared loop never calls these; present so the
    # SourceClient contract is satisfied explicitly rather than by a missing attribute.
    async def formulate_dense_queries(self, content: str, n: int) -> list[str]:
        raise NotImplementedError("OpenAlex (Arm B) has no dense leg")

    async def reformulate_dense_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        raise NotImplementedError("OpenAlex (Arm B) has no dense leg")

    # --- retrieval ------------------------------------------------------------------------- #
    async def keyword_search(self, query: str, limit: int) -> list[Candidate]:
        """Fan out one boolean into base/SR/RCT variants (§4.3, same as Arm A), search each
        (reuses production `OpenAlexService.search`, cached per variant), combine + dedup by id.

        Order is base→SR→RCT (dedup keep-first); it doesn't matter — the §4.3 blend reranks the
        pool. Fanout here is for retrieval breadth (surface SR/RCT evidence), not ordering.
        """
        out: list[Candidate] = []
        seen: set[str] = set()
        for _variant, vq in fanout(
            query, self._fanout_enabled, self._sr_clause, self._rct_clause
        ):
            q = strip_openalex_wildcards(
                self._sanitize(vq)
            )  # prod sanitize (commas) + drop wildcards
            key = {"q": q, "limit": limit, "min_citations": self._min_citations}

            async def _fetch(
                _q=q,
            ) -> list[dict]:  # _q=q binds the loop var (no late-binding bug)
                df = await self._svc.search(
                    _q, max_results=limit, min_citations=self._min_citations
                )
                return _df_to_rows(df)

            try:
                rows = await _cache.cached("openalex.search", key, _fetch)
            except Exception as e:
                # One un-servable variant (OpenAlex 500/504s an over-broad boolean even after retries)
                # must not sink the whole query — skip it and continue, exactly as production does with
                # gather(return_exceptions=True) (references.py:643-649). Recorded as a measured quantity.
                self.n_search_failures += 1
                logger.error(
                    "OpenAlex search failed for %s variant (skipping): %s", _variant, e
                )
                continue
            for r in rows:
                rid = str(r.get("id") or "")
                if rid and rid not in seen:
                    seen.add(rid)
                    out.append(_row_to_candidate(r))
        return out

    async def dense_search(self, query: str, limit: int) -> list[Candidate]:
        """No dense leg on OpenAlex (source-forced §4.3 diff #1; caps.has_dense gates this off)."""
        raise NotImplementedError(
            "OpenAlex has no dense/snippet search (Arm C / S2 only)"
        )

    async def suggest(self, content: str, n: int) -> list[Candidate]:
        """Parametric LLM suggestions, grounded against OpenAlex by title (±2yr).

        Titles that match no real record are dropped (the source returns nothing); the
        title-similarity of those that DO match is recorded by `ground_suggestions` (keyed by
        `content`) for after-the-fact inspection — not gated (spec §4.3 Step 1, §7)."""
        titles = suggest_titles(content, n)
        return await ground_suggestions(titles, self._ground_one, cache_key=content)

    async def _ground_one(self, s: SuggestedPaper) -> Candidate | None:
        """Ground one suggested (title, year) against OpenAlex by title search (±2-year window).

        We request the top 5 title matches and trust OpenAlex's own fuzzy title ranking, taking
        its rank-1 hit (rather than re-ranking with our own metric). `ground_suggestions` still
        records the chosen match's title-similarity so a wrong grounding is visible after the run.
        """
        key = {"title": s.title, "year": s.year}

        async def _fetch() -> list[dict]:
            q = self._Works().search_filter(title=_clean_title_for_filter(s.title))
            if s.year:
                q = q.filter(
                    from_publication_date=f"{s.year - 2}-01-01",
                    to_publication_date=f"{s.year + 2}-12-31",
                )
            works = q.get(per_page=5)  # top 5 relevance-ranked title matches
            return [_work_to_row(w) for w in works]

        rows = await _cache.cached("openalex.ground", key, _fetch)
        if not rows:
            return None
        return _row_to_candidate(rows[0])  # trust OpenAlex's top fuzzy title match

    # --- citation-graph expansion (snowball fetch legs) ------------------------------------ #
    async def fetch_citations(self, paper_id: str) -> list[Candidate]:
        """Forward snowball: papers citing `paper_id` (`cites:` filter). No influence flag on
        OpenAlex, so `is_influential` stays False (source-forced §4.3 diff #2)."""
        key = {"cites": paper_id, "cap": _GRAPH_FETCH_CAP}

        async def _fetch() -> list[dict]:
            works = (
                self._Works()
                .filter(cites=paper_id)
                .get(per_page=min(200, _GRAPH_FETCH_CAP))
            )
            return [_work_to_row(w) for w in works[:_GRAPH_FETCH_CAP]]

        rows = await _cache.cached("openalex.cites", key, _fetch)
        return [_row_to_candidate(r) for r in rows]

    async def fetch_references(self, paper_id: str) -> list[Candidate]:
        """Backward snowball: the seed's `referenced_works` (free on the record), batch-resolved
        to full records (|-OR id filter, ≤50/request) so the candidates carry title/abstract."""
        key = {"refs_of": paper_id, "cap": _GRAPH_FETCH_CAP}

        async def _fetch() -> list[dict]:
            seed = self._Works()[paper_id]
            ref_ids = (seed.get("referenced_works") or [])[:_GRAPH_FETCH_CAP]
            rows: list[dict] = []
            for chunk in _chunks(ref_ids, _REFERENCES_RESOLVE_CHUNK):
                works = (
                    self._Works()
                    .filter(openalex_id="|".join(chunk))
                    .get(per_page=_REFERENCES_RESOLVE_CHUNK)
                )
                rows += [_work_to_row(w) for w in works]
            return rows

        rows = await _cache.cached("openalex.refs", key, _fetch)
        return [_row_to_candidate(r) for r in rows]
