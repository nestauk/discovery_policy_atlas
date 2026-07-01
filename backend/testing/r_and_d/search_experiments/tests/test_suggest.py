"""Offline tests for retrieval.suggest — title-similarity + record-not-drop grounding.

The naming call (`suggest_titles`) is live/LLM so it's exercised in the smoke; here we pin the
pure title-similarity metric and the grounding bookkeeping: every source-confirmed match is KEPT
(no threshold drop — we measure first, cf. §4.4), its similarity is recorded, and titles the
source can't confirm are dropped (the source returns None).
"""

from __future__ import annotations

from retrieval import _cache
from retrieval.suggest import SuggestedPaper, ground_suggestions, title_similarity
from source import Candidate


def test_title_similarity_exact_is_one_ignoring_case_punctuation():
    assert (
        title_similarity(
            "Free School Meals & Attainment!", "free school meals  attainment"
        )
        == 1.0
    )


def test_title_similarity_substring_is_strong():
    # LLM recalled the title without its subtitle — still a strong match.
    s = title_similarity(
        "Universal basic income", "Universal basic income: evidence from a Kenyan RCT"
    )
    assert s >= 0.95


def test_title_similarity_empty_and_disjoint():
    assert title_similarity("", "anything") == 0.0
    assert title_similarity("a b c", None) == 0.0
    assert (
        title_similarity("cats and dogs in cities", "quantum chromodynamics lattice")
        < 0.5
    )


async def test_ground_suggestions_keeps_matches_drops_unconfirmed_and_records(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)
    suggestions = [
        SuggestedPaper(title="Real Paper A", year=2020),
        SuggestedPaper(title="A Hallucinated Title", year=None),
    ]

    async def ground_fn(s: SuggestedPaper) -> Candidate | None:
        if s.title == "Real Paper A":
            return Candidate(
                "W1", title="Real Paper A: a longitudinal study", year=2020
            )
        return None  # source confirmed nothing -> dropped

    out = await ground_suggestions(suggestions, ground_fn, cache_key="some topic")
    assert [c.paper_id for c in out] == ["W1"]  # unconfirmed suggestion dropped

    records = _cache.load("suggest.groundings", {"content": "some topic"})
    assert len(records) == 1
    assert records[0]["matched_id"] == "W1"
    assert records[0]["similarity"] >= 0.95  # recorded, NOT used to gate


async def test_ground_suggestions_no_cache_write_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)

    async def ground_fn(s: SuggestedPaper) -> Candidate | None:
        return Candidate("W9", title=s.title)

    out = await ground_suggestions([SuggestedPaper(title="X", year=None)], ground_fn)
    assert [c.paper_id for c in out] == ["W9"]
    # no cache_key -> nothing persisted under suggest.groundings
    assert not (tmp_path / "suggest.groundings").exists()
