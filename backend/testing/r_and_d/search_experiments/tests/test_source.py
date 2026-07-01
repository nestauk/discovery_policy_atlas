"""Offline tests for source.py — Candidate.merge_from + dedupe (the origin-union contract).

These guard the seam the whole pipeline relies on: a paper found by several mechanisms must
end up with ALL its origins (the bandit's arms, Phase 3b) and its richest metadata.
"""

from __future__ import annotations

from source import Candidate, Capabilities, FakeSource, dedupe


def _cand(pid: str, **kw) -> Candidate:
    return Candidate(paper_id=pid, **kw)


def test_merge_from_unions_origins():
    a = _cand("W1", origins={"keyword:q1"})
    b = _cand("W1", origins={"dense:q2", "snowball_fwd:S"})
    a.merge_from(b)
    assert a.origins == {"keyword:q1", "dense:q2", "snowball_fwd:S"}


def test_merge_from_keeps_max_monotone_signals():
    a = _cand("W1", cited_by_count=10, influential_citation_count=1, num_snippets=2)
    b = _cand("W1", cited_by_count=99, influential_citation_count=5, num_snippets=0)
    a.merge_from(b)
    assert a.cited_by_count == 99
    assert a.influential_citation_count == 5
    assert a.num_snippets == 2  # max, not overwrite


def test_merge_from_fills_missing_text_without_clobbering():
    a = _cand("W1", title="Real title", abstract=None, year=None, doi=None)
    b = _cand("W1", title="other", abstract="An abstract.", year=2020, doi="10.x/y")
    a.merge_from(b)
    assert a.title == "Real title"  # present value wins
    assert a.abstract == "An abstract."  # missing value filled
    assert a.year == 2020
    assert a.doi == "10.x/y"


def test_merge_from_is_influential_is_sticky_or():
    a = _cand("W1", is_influential=False)
    b = _cand("W1", is_influential=True)
    a.merge_from(b)
    assert a.is_influential is True


def test_merge_from_fills_level_only_if_unjudged():
    a = _cand("W1", level=None)
    a.merge_from(_cand("W1", level=2))
    assert a.level == 2
    # already-judged level is NOT overwritten by a duplicate
    a.merge_from(_cand("W1", level=3))
    assert a.level == 2


def test_merge_from_fills_relevance_score_only_if_unset():
    a = _cand("W1", relevance_score=None)
    a.merge_from(_cand("W1", relevance_score=0.8))
    assert a.relevance_score == 0.8
    # already-set continuous score is NOT overwritten by a duplicate
    a.merge_from(_cand("W1", relevance_score=0.2))
    assert a.relevance_score == 0.8


def test_dedupe_merges_and_preserves_first_position():
    cands = [
        _cand("W1", title="first", origins={"keyword:q1"}),
        _cand("W2", origins={"dense:q1"}),
        _cand("W1", abstract="late abstract", origins={"snowball_bwd:S"}),
    ]
    out = dedupe(cands)
    assert [c.paper_id for c in out] == ["W1", "W2"]  # first occurrence holds position
    w1 = out[0]
    assert w1.origins == {"keyword:q1", "snowball_bwd:S"}
    assert w1.title == "first"
    assert w1.abstract == "late abstract"


def test_capabilities_default_is_arm_b_shape():
    caps = Capabilities()
    assert not caps.has_dense
    assert not caps.has_influential
    assert not caps.has_snippets
    assert not caps.native_abstracts


async def test_fakesource_influential_flag_only_with_capability():
    arm_b = FakeSource()  # no influential
    cites_b = await arm_b.fetch_citations("W1")
    assert all(not c.is_influential for c in cites_b)

    arm_c = FakeSource(caps=Capabilities(has_influential=True))
    cites_c = await arm_c.fetch_citations("W1")
    assert any(c.is_influential for c in cites_c)


async def test_fakesource_dense_guarded_by_capability():
    import pytest

    with pytest.raises(NotImplementedError):
        await FakeSource().dense_search("q", 5)
