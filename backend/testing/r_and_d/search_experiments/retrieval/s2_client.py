"""Arm C source client — `S2Source`, the SourceClient for Semantic Scholar (spec §4.3a).

This is the concrete implementation `broad_search` drives for Arm C. Capabilities are all-True,
which lights up the dormant parts of the shared pipeline: the dense leg (`dense_search`), the
forward-influence snowball term (`snowball.py`), and the snippet blend term (`ranking.py`).
Formulation is PER LEG (PF's two-agent split): the KEYWORD leg uses PF's keyword idiom
(`keyword_s2.py`), the DENSE leg uses PF's dense idiom (`dense_s2.py`) — they want different query
shapes (S2 relevance is keyword-ish, dense is NL), so reusing one for both starved the keyword leg
(FINDINGS 2026-06-23). The deliberate B↔C divergence (§4.3a/§7).

Two pieces of S2-specific machinery the OpenAlex client didn't need:

  1. **Global rate throttle.** S2 allows 1 request/second CUMULATIVE across all endpoints
     (confirmed against S2 docs, 2026-06-23). `_RateThrottle` (a module singleton, shared by
     every method and instance) serialises requests to >= CONFIG.s2_min_request_interval_s
     apart, and `_raw_request` backs off + retries on 429. The cache check happens BEFORE the
     throttle, so cache hits cost zero rate budget — which is what makes reruns and the per-seed
     forward snowball affordable. This throttle dominates Arm C wall-time (spec §7, a cost finding).

  2. **Batch hydration of dense hits.** `/snippet/search` returns SPARSE papers (corpusId, title,
     snippet text only — no year/citationCount/abstract), but ranking needs year+cites and the
     judge needs text. So `dense_search` hydrates its corpusIds via `/paper/batch` — PF's exact
     resolution (dcollection lazy-loads the same fields by corpusId via `get_papers`), done
     eagerly here because our single-pass pipeline judges+ranks every candidate anyway.

`paper_id` is the S2 `corpusId` (the id BENCH scores on, §3), normalised to str. Backend `get_llm`
is reached only via dense_s2 / suggest (lazy there); this module itself needs no `app.*` import.

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from retrieval.s2_client import S2Source
    src = S2Source()
    kw = asyncio.run(src.formulate_keyword_queries("effect of free school meals on attainment", 5))
    qs = asyncio.run(src.formulate_dense_queries("effect of free school meals on attainment", 5))
    cands = asyncio.run(src.dense_search(qs[0], 50))
    asyncio.run(src.aclose())
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

from config import CONFIG
from retrieval import _cache
from retrieval.dense_s2 import (
    formulate_dense_queries as _formulate_dense,
    reformulate_dense_queries as _reformulate_dense,
)
from retrieval.keyword_s2 import (
    formulate_keyword_queries as _formulate_keyword,
    reformulate_keyword_queries as _reformulate_keyword,
)
from retrieval.suggest import SuggestedPaper, ground_suggestions, suggest_titles
from source import Candidate, Capabilities

logger = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"

# Status codes worth retrying with back-off: 429 (rate limit) + transient server errors (5xx).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Fields requested per endpoint (S2 field names; the mapper reads these back).
_PAPER_FIELDS = (
    "title,abstract,tldr,externalIds,citationCount,influentialCitationCount,"
    "referenceCount,year,publicationDate"
)
# Citation/reference EDGE fields: `isInfluential` is the per-edge influence flag snowball needs
# (a sibling of citingPaper/citedPaper); the rest populate the connected paper.
_CONNECTION_FIELDS = "isInfluential,title,externalIds,citationCount,influentialCitationCount,referenceCount,year"

_PAPER_SEARCH_PAGE = 100  # /paper/search relevance: max 100/page, offset+limit <= 1000
_CONNECTION_PAGE = 1000  # /citations and /references: up to 1000/page
_BATCH_CHUNK = 500  # /paper/batch: up to 500 ids/request
_GRAPH_FETCH_CAP = CONFIG.budgets.snowball_top_k  # bound per-seed snowball fan-out


# --------------------------------------------------------------------------- #
# Rate throttle (global, shared across instances + endpoints — cumulative 1 req/s)
# --------------------------------------------------------------------------- #
class _RateThrottle:
    """Serialise S2 requests to >= `min_interval` apart (clock/sleep injectable for tests)."""

    def __init__(self, min_interval: float, *, clock=None, sleep=None):
        self._min = min_interval
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._lock = asyncio.Lock()
        self._last: float | None = None

    async def wait(self) -> None:
        async with self._lock:  # one request in flight at a time (cumulative limit)
            if self._last is not None:
                wait_for = self._min - (self._clock() - self._last)
                if wait_for > 0:
                    await self._sleep(wait_for)
            self._last = self._clock()


_THROTTLE = _RateThrottle(CONFIG.s2_min_request_interval_s)


# --------------------------------------------------------------------------- #
# Pure mappers (offline-testable — no network)
# --------------------------------------------------------------------------- #
def _corpus_id(paper: dict) -> str | None:
    """S2 corpusId as str: top-level `corpusId` (batch) or `externalIds.CorpusId` (search/edges)."""
    cid = paper.get("corpusId")
    if cid is None:
        cid = (paper.get("externalIds") or {}).get("CorpusId")
    return str(cid) if cid is not None else None


def _paper_to_candidate(paper: dict) -> Candidate | None:
    """S2 paper dict → Candidate. Abstract = abstract → tldr.text (snippet fallback set by caller)."""
    cid = _corpus_id(paper)
    if cid is None:
        return None
    abstract = paper.get("abstract")
    tldr = (paper.get("tldr") or {}).get("text")
    text = abstract or tldr
    basis = "abstract" if abstract else ("tldr" if tldr else None)
    return Candidate(
        paper_id=cid,
        title=paper.get("title"),
        abstract=text,
        year=paper.get("year"),
        cited_by_count=int(paper.get("citationCount") or 0),
        reference_count=int(paper.get("referenceCount") or 0),
        influential_citation_count=int(paper.get("influentialCitationCount") or 0),
        doi=(paper.get("externalIds") or {}).get("DOI"),
        text_basis=basis,
    )


def _group_snippets(items: list[dict]) -> dict[str, dict]:
    """Group /snippet/search rows by corpusId: {cid: {title, n_snippets, snippet_text}} (pure)."""
    by_cid: dict[str, dict] = {}
    for item in items:
        paper = item.get("paper") or {}
        cid = _corpus_id(paper)
        if not cid:
            continue
        text = (item.get("snippet") or {}).get("text")
        entry = by_cid.setdefault(
            cid, {"title": paper.get("title"), "n": 0, "snippet": None}
        )
        entry["n"] += 1
        if not entry["snippet"] and text:
            entry["snippet"] = text
    return by_cid


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# --------------------------------------------------------------------------- #
# S2Source
# --------------------------------------------------------------------------- #
class S2Source:
    """`SourceClient` for Semantic Scholar (Arm C). Capabilities all-True (the dense corpus)."""

    name = "s2"
    caps = Capabilities(
        has_dense=True,
        has_influential=True,
        has_snippets=True,
        native_abstracts=True,
    )

    def __init__(self, *, min_citations: int | None = None):
        # Citation floor on the PRIMARY legs (keyword + dense), for A/B/C parity: Arm A/B floor
        # OpenAlex at cited_by_count:>min_citations, so C matches with a strict `>` post-filter.
        # Snowball/suggest stay unfloored (mirrors OpenAlexSource, which floors only keyword_search).
        self._min_citations = min_citations
        self._http: httpx.AsyncClient | None = None

    def _floor(self, cands: list[Candidate]) -> list[Candidate]:
        """Drop candidates at/below the citation floor (strict `>`, matching OpenAlex's `cited_by_count:>n`)."""
        if self._min_citations is None:
            return cands
        return [c for c in cands if (c.cited_by_count or 0) > self._min_citations]

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
            if not key:
                raise RuntimeError(
                    "SEMANTIC_SCHOLAR_API_KEY not set (expected in backend/.env)"
                )
            self._http = httpx.AsyncClient(headers={"x-api-key": key}, timeout=40)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # --- request plumbing (throttle + cache + 429 back-off) -------------------------------- #
    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params=None,
        json_body=None,
        max_retries: int = 5,
    ):
        """One throttled S2 request with exponential back-off on retryable errors. Returns JSON.

        Retries on 429 (rate limit) AND transient 5xx (500/502/503/504) — S2 throws those under
        load and they're server-side, not query-side; without retrying them a single transient 500
        aborts a whole arm-query (FINDINGS 2026-06-26). A persistent error still surfaces once
        retries exhaust, so genuine failures aren't masked."""
        client = self._client()
        delay = 2.0
        for attempt in range(max_retries + 1):
            await _THROTTLE.wait()  # cumulative 1 req/s across all endpoints
            resp = await client.request(
                method, f"{S2_BASE}{path}", params=params, json=json_body
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                logger.warning(
                    "S2 %d on %s (attempt %d/%d); backing off %.1fs",
                    resp.status_code,
                    path,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.7, 30)
                continue
            resp.raise_for_status()
            return resp.json()

    async def _cached(
        self, namespace: str, key, path, *, params=None, json_body=None, method="GET"
    ):
        """Cache-before-throttle: a cache hit never spends a request (the 1 req/s budget)."""

        async def _produce():
            return await self._raw_request(
                method, path, params=params, json_body=json_body
            )

        return await _cache.cached(namespace, key, _produce)

    # --- endpoint calls -------------------------------------------------------------------- #
    async def _paper_search(self, query: str, limit: int) -> list[dict]:
        """/paper/search (relevance), paginated by offset to `limit` (<=100/page)."""
        collected: list[dict] = []
        offset = 0
        while len(collected) < limit and offset < 1000:
            page = min(_PAPER_SEARCH_PAGE, limit - len(collected))
            key = {"query": query, "limit": page, "offset": offset}
            data = await self._cached(
                "s2.paper_search",
                key,
                "/paper/search",
                params={
                    "query": query,
                    "fields": _PAPER_FIELDS,
                    "limit": page,
                    "offset": offset,
                },
            )
            rows = data.get("data") or []
            collected += rows
            nxt = data.get("next")
            if not rows or nxt is None:
                break
            offset = nxt
        return collected

    async def _snippet_search(self, query: str, limit: int) -> list[dict]:
        """/snippet/search (dense). Single call — returns the top-k snippet rows."""
        key = {"query": query, "limit": min(limit, 1000)}
        data = await self._cached(
            "s2.snippet_search",
            key,
            "/snippet/search",
            params={"query": query, "limit": min(limit, 1000)},
        )
        return data.get("data") or []

    async def _batch(self, corpus_ids: list[str], fields: str) -> list[dict]:
        """/paper/batch — full metadata by corpusId (the dense-hydration call). Skips nulls."""
        out: list[dict] = []
        for chunk in _chunks(corpus_ids, _BATCH_CHUNK):
            key = {"ids": sorted(chunk), "fields": fields}
            data = await self._cached(
                "s2.batch",
                key,
                "/paper/batch",
                method="POST",
                params={"fields": fields},
                json_body={"ids": [f"CorpusId:{c}" for c in chunk]},
            )
            out += [
                p for p in (data or []) if p
            ]  # batch returns null for not-found ids
        return out

    async def _connections(self, paper_id: str, kind: str, limit: int) -> list[dict]:
        """/paper/CorpusId:{id}/{citations|references}, paginated to `limit` (edge rows)."""
        collected: list[dict] = []
        offset = 0
        while len(collected) < limit:
            page = min(_CONNECTION_PAGE, limit - len(collected))
            key = {"id": paper_id, "kind": kind, "limit": page, "offset": offset}
            data = await self._cached(
                f"s2.{kind}",
                key,
                f"/paper/CorpusId:{paper_id}/{kind}",
                params={"fields": _CONNECTION_FIELDS, "limit": page, "offset": offset},
            )
            rows = data.get("data") or []
            collected += rows
            nxt = data.get("next")
            if not rows or nxt is None:
                break
            offset = nxt
        return collected

    # --- SourceClient: formulation (keyword leg -> keyword_s2; dense leg -> dense_s2) ------- #
    async def formulate_keyword_queries(self, content: str, n: int) -> list[str]:
        return _formulate_keyword(content, n)

    async def reformulate_keyword_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        return _reformulate_keyword(content, exemplars, n)

    async def formulate_dense_queries(self, content: str, n: int) -> list[str]:
        return _formulate_dense(content, n)

    async def reformulate_dense_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        return _reformulate_dense(content, exemplars, n)

    # --- SourceClient: retrieval ----------------------------------------------------------- #
    async def keyword_search(self, query: str, limit: int) -> list[Candidate]:
        """S2 relevance search (/paper/search) — native abstracts/tldr, no enrichment needed."""
        rows = await self._paper_search(query, limit)
        return self._floor(
            [c for c in (_paper_to_candidate(r) for r in rows) if c is not None]
        )

    async def dense_search(self, query: str, limit: int) -> list[Candidate]:
        """S2 dense leg: /snippet/search → group + count snippets → batch-hydrate metadata.

        Sets `num_snippets` (dense-match strength) and uses the real abstract once hydrated,
        falling back to the snippet text (text_basis='snippet') for papers batch can't fill.
        """
        grouped = _group_snippets(await self._snippet_search(query, limit))
        cids = list(grouped)
        hydrated = {
            c: p for p in await self._batch(cids, _PAPER_FIELDS) if (c := _corpus_id(p))
        }

        cands: list[Candidate] = []
        for cid, info in grouped.items():
            paper = hydrated.get(cid)
            cand = (
                _paper_to_candidate(paper)
                if paper
                else Candidate(paper_id=cid, title=info["title"])
            )
            if cand is None:
                continue
            cand.num_snippets = info["n"]
            if not cand.abstract and info["snippet"]:
                cand.abstract = info["snippet"]
                cand.text_basis = "snippet"
            cands.append(cand)
        return self._floor(cands)

    async def suggest(self, content: str, n: int) -> list[Candidate]:
        """Parametric LLM suggestions, grounded against S2 by title (±2yr); similarity recorded."""
        titles = suggest_titles(content, n)
        return await ground_suggestions(titles, self._ground_one, cache_key=content)

    async def _ground_one(self, s: SuggestedPaper) -> Candidate | None:
        """Ground a suggested (title, year) via /paper/search; trust S2's top relevance hit."""
        params = {"query": s.title, "fields": _PAPER_FIELDS, "limit": 5}
        if s.year:
            params["year"] = f"{s.year - 2}-{s.year + 2}"  # S2 server-side year window
        key = {"title": s.title, "year": s.year}
        data = await self._cached("s2.ground", key, "/paper/search", params=params)
        rows = data.get("data") or []
        return _paper_to_candidate(rows[0]) if rows else None

    # --- SourceClient: citation-graph expansion -------------------------------------------- #
    async def fetch_citations(self, paper_id: str) -> list[Candidate]:
        """Forward snowball: papers citing this one. Edge `isInfluential` → Candidate.is_influential
        (the §4.3 diff #2 signal OpenAlex lacks)."""
        edges = await self._connections(paper_id, "citations", _GRAPH_FETCH_CAP)
        cands: list[Candidate] = []
        for e in edges:
            cand = _paper_to_candidate(e.get("citingPaper") or {})
            if cand is None:
                continue
            cand.is_influential = bool(e.get("isInfluential"))
            cands.append(cand)
        return cands

    async def fetch_references(self, paper_id: str) -> list[Candidate]:
        """Backward snowball: this paper's references (PF carries no influence term backward)."""
        edges = await self._connections(paper_id, "references", _GRAPH_FETCH_CAP)
        return [
            c
            for c in (_paper_to_candidate(e.get("citedPaper") or {}) for e in edges)
            if c
        ]
