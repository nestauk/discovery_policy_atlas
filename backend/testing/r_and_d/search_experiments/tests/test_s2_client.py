"""Offline tests for the pure parts of retrieval.s2_client (Arm C / Semantic Scholar).

The network methods (`dense_search`, `keyword_search`, the snowball legs) are exercised LIVE in
smoke/phase4_s2.py — they need `SEMANTIC_SCHOLAR_API_KEY` and the 1 req/s throttle. Here we pin
the bits that have no network and so are cheap, deterministic, and key-free:

  - the dict→Candidate mappers (`_corpus_id`, `_paper_to_candidate`, `_group_snippets`) — the
    funnel every S2 endpoint shape passes through, including the two different corpusId placements
    (top-level `corpusId` from /paper/batch vs nested `externalIds.CorpusId` from search/edges) and
    the abstract→tldr→snippet text precedence that `text_basis` records;
  - `_RateThrottle` — the cumulative 1 req/s serialiser. It takes injectable clock/sleep precisely
    so this can assert the wait math without sleeping a real second.

These import cleanly because the client lazy-imports `app.*` inside its methods (same convention as
openalex_client / judge / ranking), so importing the module pulls no backend env.
"""

from __future__ import annotations

from retrieval.s2_client import (
    S2Source,
    _RateThrottle,
    _chunks,
    _corpus_id,
    _group_snippets,
    _paper_to_candidate,
)
from core.source import Candidate


# --------------------------------------------------------------------------- #
# S2Source._floor — citation floor on the primary legs (A/B/C parity, 2026-06-26)
# --------------------------------------------------------------------------- #
def _cands(*counts):
    return [
        Candidate(paper_id=str(i), title="t", cited_by_count=c)
        for i, c in enumerate(counts)
    ]


def test_floor_none_is_a_passthrough():
    src = S2Source()  # default: no floor
    cands = _cands(0, 3, 100)
    assert src._floor(cands) == cands


def test_floor_is_strict_greater_matching_openalex():
    # OpenAlex filters cited_by_count:>n (strict), so the S2 post-filter must drop ==n too.
    src = S2Source(min_citations=5)
    kept = src._floor(_cands(0, 5, 6, 200))
    assert [c.cited_by_count for c in kept] == [6, 200]


def test_floor_treats_missing_count_as_zero():
    src = S2Source(min_citations=5)
    c = Candidate(paper_id="x", title="t", cited_by_count=None)
    assert src._floor([c]) == []


# --------------------------------------------------------------------------- #
# _corpus_id — the one identity, two JSON shapes
# --------------------------------------------------------------------------- #
def test_corpus_id_reads_top_level_and_nested_and_normalises_to_str():
    assert _corpus_id({"corpusId": 12345}) == "12345"  # /paper/batch shape, int -> str
    assert _corpus_id({"externalIds": {"CorpusId": 678}}) == "678"  # search/edge shape
    assert (
        _corpus_id({"corpusId": 9, "externalIds": {"CorpusId": 99}}) == "9"
    )  # top-level wins
    assert _corpus_id({}) is None
    assert _corpus_id({"externalIds": {}}) is None


# --------------------------------------------------------------------------- #
# _paper_to_candidate — text precedence + field carry + corpusId guard
# --------------------------------------------------------------------------- #
def test_paper_to_candidate_prefers_abstract_and_carries_fields():
    c = _paper_to_candidate(
        {
            "corpusId": 1,
            "title": "T",
            "abstract": "A real abstract.",
            "tldr": {"text": "a tldr"},
            "year": 2020,
            "citationCount": 42,
            "referenceCount": 13,
            "influentialCitationCount": 7,
            "externalIds": {"DOI": "10.x/y"},
        }
    )
    assert c.paper_id == "1"
    assert c.abstract == "A real abstract."  # abstract beats tldr
    assert c.text_basis == "abstract"
    assert (c.year, c.cited_by_count, c.reference_count) == (2020, 42, 13)
    assert c.influential_citation_count == 7
    assert c.doi == "10.x/y"


def test_paper_to_candidate_falls_back_to_tldr_when_no_abstract():
    c = _paper_to_candidate({"corpusId": 2, "title": "T", "tldr": {"text": "a tldr"}})
    assert c.abstract == "a tldr"
    assert c.text_basis == "tldr"


def test_paper_to_candidate_no_text_leaves_basis_none_and_counts_default_zero():
    c = _paper_to_candidate({"corpusId": 3, "title": "T"})
    assert c.abstract is None
    assert c.text_basis is None
    assert (c.cited_by_count, c.reference_count, c.influential_citation_count) == (
        0,
        0,
        0,
    )


def test_paper_to_candidate_none_without_corpus_id():
    # No id => nothing to score against (corpusId is the BENCH id), so it must be dropped.
    assert _paper_to_candidate({"title": "no id", "abstract": "x"}) is None


# --------------------------------------------------------------------------- #
# _group_snippets — collapse passages to papers, COUNT them (-> num_snippets)
# --------------------------------------------------------------------------- #
def test_group_snippets_counts_passages_and_keeps_first_nonempty_snippet():
    items = [
        {
            "paper": {"externalIds": {"CorpusId": 5}, "title": "P5"},
            "snippet": {"text": ""},
        },
        {
            "paper": {"externalIds": {"CorpusId": 5}, "title": "P5"},
            "snippet": {"text": "first real"},
        },
        {
            "paper": {"externalIds": {"CorpusId": 5}, "title": "P5"},
            "snippet": {"text": "second"},
        },
        {
            "paper": {"externalIds": {"CorpusId": 6}, "title": "P6"},
            "snippet": {"text": "only"},
        },
    ]
    grouped = _group_snippets(items)
    assert set(grouped) == {"5", "6"}
    assert grouped["5"]["n"] == 3  # passage count = dense-match strength
    assert (
        grouped["5"]["snippet"] == "first real"
    )  # first NON-EMPTY snippet kept, blank skipped
    assert grouped["6"]["n"] == 1


def test_group_snippets_skips_rows_without_corpus_id():
    items = [{"paper": {"title": "no id"}, "snippet": {"text": "x"}}]
    assert _group_snippets(items) == {}


def test_chunks_splits_to_size_and_handles_remainder():
    assert list(_chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(_chunks([], 500)) == []


# --------------------------------------------------------------------------- #
# _RateThrottle — cumulative 1 req/s, asserted with an injected fake clock/sleep
# --------------------------------------------------------------------------- #
async def test_throttle_first_call_does_not_wait():
    clock = {"t": 100.0}
    slept: list[float] = []

    async def fake_sleep(
        d,
    ):  # records the wait; advances the fake clock as a real sleep would
        slept.append(d)
        clock["t"] += d

    th = _RateThrottle(1.1, clock=lambda: clock["t"], sleep=fake_sleep)
    await th.wait()
    assert slept == []  # nothing in flight yet -> no throttle


async def test_throttle_back_to_back_call_waits_min_interval():
    clock = {"t": 0.0}
    slept: list[float] = []

    async def fake_sleep(d):
        slept.append(d)
        clock["t"] += d

    th = _RateThrottle(1.1, clock=lambda: clock["t"], sleep=fake_sleep)
    await th.wait()  # t=0, sets _last
    await th.wait()  # immediately again, no time passed -> must wait the full interval
    assert len(slept) == 1
    assert abs(slept[0] - 1.1) < 1e-9


async def test_throttle_no_wait_when_interval_already_elapsed():
    clock = {"t": 0.0}
    slept: list[float] = []

    async def fake_sleep(d):
        slept.append(d)
        clock["t"] += d

    th = _RateThrottle(1.1, clock=lambda: clock["t"], sleep=fake_sleep)
    await th.wait()  # t=0
    clock["t"] += 2.0  # 2s of real work happened between requests (> 1.1 interval)
    await th.wait()
    assert slept == []  # already spaced far enough apart -> no throttle needed
