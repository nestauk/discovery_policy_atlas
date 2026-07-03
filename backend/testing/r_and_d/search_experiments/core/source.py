"""The source-agnostic contract: Candidate, Capabilities, SourceClient, FakeSource.

This is the seam that makes the agentic core (Phase 3b `broad_search`) source-agnostic
(spec §4.3, §6 "machinery built once"). The core depends only on these abstractions; the
concrete OpenAlex/S2 clients (Phase 4) implement `SourceClient`, and Arms B/C differ ONLY
where `Capabilities` say the source can't follow — the four source-forced differences (§4.3):

    has_dense          Arm C only — S2 snippet/dense search leg (Arm B has none, §4.3 #1)
    has_influential    Arm C only — influentialCitationCount in forward snowball (§4.3 #2)
    has_snippets       Arm C only — the +0.025 snippet term in the content blend (§4.3 #3)
    native_abstracts   Arm C natively; Arm A/B enrich via Crossref (§4.4, §4.3 #4)

Encoding the differences as capability flags read in ONE shared loop is what keeps B and C
mechanism-identical (the whole point of the A→B→C ladder) instead of two near-duplicate
pipelines.

`Candidate` is a mutable dataclass that accretes fields as it flows through the pipeline:
retrieval sets id/title/abstract/origins; the judge sets `level`; ranking sets `rerank_score`.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Capabilities:
    """What a source can do — drives the four source-forced differences (§4.3)."""

    has_dense: bool = False
    has_influential: bool = False
    has_snippets: bool = False
    native_abstracts: bool = False


@dataclass
class Candidate:
    """A retrieved paper, accreting fields as it moves through retrieve → judge → rank.

    `paper_id` is the source's stable id (OpenAlex work id / S2 corpusId) and the cache key.
    `origins` is the set of mechanism+query tags that surfaced it (e.g. "keyword:q3",
    "snowball_fwd:W123", "dense:q1") — these are the bandit's arms (Phase 3b) and the
    origin-attribution signal (§4.7). On dedupe, origins are unioned.
    """

    paper_id: str
    title: str | None = None
    abstract: str | None = None
    year: int | None = None
    cited_by_count: int = 0
    reference_count: int = 0  # size of this paper's bibliography; PF penalises FORWARD
    # snowball candidates by their reference count (snowball.py), backward by cited_by_count
    influential_citation_count: int = 0  # Arm C (S2); 0 for OpenAlex
    num_snippets: int = 0  # Arm C dense leg; 0 otherwise
    doi: str | None = None
    text_basis: str | None = None  # "abstract" | "title_only" | "tldr" | "snippet"
    origins: set[str] = field(default_factory=set)

    # set during expansion (snowball): the seed's relevance carried to the candidate
    seed_relevance: float = 0.0
    is_influential: bool = False  # forward-snowball influential-citation flag (Arm C)

    # set by the judge (Phase 2): 0–3 relevance level, None until judged
    level: int | None = None
    # set by the judge: the CONTINUOUS weighted-criteria score in [0,1]
    # (metrics.relevance_criteria_score), BEFORE bucketing to `level`. PF's ranking content
    # blend prefers this over level/3 (sorting.py:512), so the §4.3 Step-5 ordering keeps the
    # within-tier granularity two same-level papers would otherwise lose. None until judged.
    relevance_score: float | None = None

    # set during ranking (Phase 3a)
    rerank_score: float = 0.0

    def merge_from(self, other: Candidate) -> None:
        """Merge a duplicate (same paper_id) into this one: union origins, keep best signals.

        Mirrors PF's DocumentCollection origin-merge on dedupe. Keeps the max of the
        monotone count/flag fields and fills any missing text, so a paper found by several
        mechanisms ends up with all its origins and its richest metadata.
        """
        self.origins |= other.origins
        self.cited_by_count = max(self.cited_by_count, other.cited_by_count)
        self.reference_count = max(self.reference_count, other.reference_count)
        self.influential_citation_count = max(
            self.influential_citation_count, other.influential_citation_count
        )
        self.num_snippets = max(self.num_snippets, other.num_snippets)
        self.seed_relevance = max(self.seed_relevance, other.seed_relevance)
        self.is_influential = self.is_influential or other.is_influential
        self.title = self.title or other.title
        self.abstract = self.abstract or other.abstract
        self.year = self.year or other.year
        self.doi = self.doi or other.doi
        if self.level is None:
            self.level = other.level
        if self.relevance_score is None:
            self.relevance_score = other.relevance_score


def dedupe(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Dedupe by paper_id, merging origins/signals (first occurrence wins position)."""
    by_id: dict[str, Candidate] = {}
    for c in candidates:
        existing = by_id.get(c.paper_id)
        if existing is None:
            by_id[c.paper_id] = c
        else:
            existing.merge_from(c)
    return list(by_id.values())


class SourceClient(Protocol):
    """The primitive operations the shared core calls. Arms B/C implement this (Phase 4).

    The core sequences these primitives identically for both arms; only the *implementations*
    (boolean vs dense formulation, OpenAlex vs S2 endpoints) and `caps` differ. Methods a
    source can't do (e.g. dense_search when not caps.has_dense) are simply never called by
    the core — they may raise NotImplementedError.
    """

    name: str
    caps: Capabilities

    async def formulate_keyword_queries(self, content: str, n: int) -> list[str]:
        """N diverse query formulations for the KEYWORD leg (-> keyword_search).

        Idiom is per-source: OpenAlex (Arm B) MUST delegate to v2's production boolean generator
        (`backend/app/services/openalex.py::search_multi_query`), i.e. the *same* generator
        Arm A uses — NOT a fresh PF-keyword-prompt-adapted-to-OpenAlex, NOT a single static
        query. Sharing the formulation idiom with Arm A is what makes A→B isolate the agentic
        loop rather than the formulation idiom (spec §4.3 "query-formulation decision 2026-06-21").
        S2 (Arm C) uses PF's keyword-bag formulation (`_broad_search_prompt_tmpl`, keyword_s2.py)
        — S2's relevance endpoint is keyword-ish and returns ~nothing for a dense NL query, so the
        keyword and dense legs are formulated SEPARATELY (PF's two-agent split; FINDINGS 2026-06-23).
        """
        ...

    async def formulate_dense_queries(self, content: str, n: int) -> list[str]:
        """N diverse natural-language formulations for the DENSE leg (-> dense_search).

        Arm C only — the shared loop calls this solely when `caps.has_dense`. S2 delegates to PF's
        dense formulation (`dense_s2.py`). Sources without a dense leg (OpenAlex) need not implement
        it; it may raise NotImplementedError (it is never called for them).
        """
        ...

    async def keyword_search(self, query: str, limit: int) -> list[Candidate]:
        ...

    async def dense_search(self, query: str, limit: int) -> list[Candidate]:
        """S2 snippet/dense search (Arm C only — guarded by caps.has_dense)."""
        ...

    async def suggest(self, content: str, n: int) -> list[Candidate]:
        """Parametric LLM suggestions, grounded against the source; ungrounded dropped."""
        ...

    async def reformulate_keyword_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        """Keyword-leg reformulation using top judged-relevant papers as exemplars.

        Idiom matches `formulate_keyword_queries`: OpenAlex (Arm B) re-invokes v2's boolean
        generator with exemplars as context (spec §4.3 query-formulation decision); S2 (Arm C) uses
        PF's keyword reformulation. The PF *strategy* (reformulate from judged exemplars) is shared;
        only the backend idiom differs by source.
        """
        ...

    async def reformulate_dense_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        """Dense-leg reformulation from judged-relevant exemplars (Arm C only; `caps.has_dense`)."""
        ...

    async def fetch_references(self, paper_id: str) -> list[Candidate]:
        """Backward snowball: the paper's reference list."""
        ...

    async def fetch_citations(self, paper_id: str) -> list[Candidate]:
        """Forward snowball: papers citing this one (carries influential flag for S2)."""
        ...


class FakeSource:
    """In-memory SourceClient for offline tests + the Phase 3b loop smoke (no API, no LLM).

    Deterministic AND query-distinct: each query string yields its own candidate ids (via a
    slug of the query), so the broad_search loop accumulates a real pool instead of dedupe
    collapsing every query to the same five papers. Counts are plentiful enough to give the
    bandit something to allocate and snowball something to promote. Capabilities default to the
    Arm-B shape (no dense/influential/snippets); pass a different `caps` to mimic Arm C.

    It does NOT assign relevance levels — that's the injected `judge_fn`'s job (the smoke uses a
    fake judge that grades by origin so the BTS allocation is visible).
    """

    def __init__(self, name: str = "fake", caps: Capabilities | None = None):
        self.name = name
        self.caps = caps or Capabilities()

    @staticmethod
    def _slug(text: str) -> str:
        # Readable prefix + a stable hash of the FULL text, so queries that differ only in a
        # suffix (e.g. "...(formulation 0/1/2)") still get distinct candidate ids (otherwise
        # dedupe would collapse all formulations to one set of papers).
        base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:16] or "q"
        return f"{base}-{zlib.crc32(text.encode()) & 0xFFFF:04x}"

    @classmethod
    def _mk(
        cls,
        prefix: str,
        n: int,
        *,
        year: int = 2020,
        cites: int = 10,
        snippets: int = 0,
        refs: int = 15,
    ) -> list[Candidate]:
        return [
            Candidate(
                paper_id=f"{prefix}-{i}",
                title=f"{prefix} paper {i}",
                abstract=f"Abstract for {prefix} paper {i}.",
                year=year,
                cited_by_count=cites + i,
                reference_count=refs,
                num_snippets=snippets,
                origins={prefix},
            )
            for i in range(n)
        ]

    async def formulate_keyword_queries(self, content: str, n: int) -> list[str]:
        return [f"{content} (keyword {i})" for i in range(n)]

    async def formulate_dense_queries(self, content: str, n: int) -> list[str]:
        if not self.caps.has_dense:
            raise NotImplementedError("source has no dense leg")
        return [f"{content} (dense {i})" for i in range(n)]

    async def keyword_search(self, query: str, limit: int) -> list[Candidate]:
        return self._mk(f"kw-{self._slug(query)}", min(limit, 8), year=2018, cites=20)

    async def dense_search(self, query: str, limit: int) -> list[Candidate]:
        if not self.caps.has_dense:
            raise NotImplementedError("source has no dense leg")
        return self._mk(
            f"dense-{self._slug(query)}", min(limit, 8), year=2022, cites=10, snippets=4
        )

    async def suggest(self, content: str, n: int) -> list[Candidate]:
        return self._mk(f"sug-{self._slug(content)}", min(n, 5), year=2020, cites=5)

    async def reformulate_keyword_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        return [f"{content} (keyword reformulated {i})" for i in range(n)]

    async def reformulate_dense_queries(
        self, content: str, exemplars: list[Candidate], n: int
    ) -> list[str]:
        if not self.caps.has_dense:
            raise NotImplementedError("source has no dense leg")
        return [f"{content} (dense reformulated {i})" for i in range(n)]

    async def fetch_references(self, paper_id: str) -> list[Candidate]:
        return self._mk(f"ref-{paper_id}", 3, year=2010, cites=120)

    async def fetch_citations(self, paper_id: str) -> list[Candidate]:
        cites = self._mk(f"cite-{paper_id}", 3, year=2023, cites=8)
        if self.caps.has_influential:
            cites[0].is_influential = True
            cites[0].influential_citation_count = 3
        return cites
