"""Offline tests for the pure dict→Candidate mappers in retrieval.openalex_client.

The network/PyAlex methods are exercised live in smoke/phase4_openalex.py; here we pin the
pure mapping logic that both retrieval paths funnel through — especially the "No abstract
available" sentinel becoming None (so the judge flags title-only, not a fake abstract) and the
two row schemas (PyAlex Work dict vs OpenAlexService search DataFrame) producing the same shape.

These import cleanly because the client lazy-imports `app.*`/`pyalex` inside __init__/methods,
so importing the module pulls no backend env (the convention judge.py/ranking.py also follow).
"""

from __future__ import annotations

import pandas as pd

from retrieval import _cache
from retrieval.openalex_client import (
    OpenAlexSource,
    _clean_abstract,
    _clean_title_for_filter,
    _df_to_rows,
    _row_to_candidate,
    _work_to_row,
    strip_openalex_wildcards,
)


# --------------------------------------------------------------------------- #
# keyword_search resilience — a failed boolean variant is SKIPPED, not fatal
# (production parity: references.py gather(return_exceptions=True)). Built offline via __new__ +
# a passthrough cache + a stub _svc, so no backend env / disk is touched (module convention above).
# --------------------------------------------------------------------------- #
def _bare_source(svc, *, fanout=True):
    """An OpenAlexSource with only the attributes keyword_search reads (skips backend-coupled __init__)."""
    src = OpenAlexSource.__new__(OpenAlexSource)
    src._fanout_enabled = fanout
    src._sr_clause, src._rct_clause = "SRCLAUSE", "RCTCLAUSE"
    src._sanitize = lambda q: q
    src._min_citations = 5
    src._svc = svc
    src.n_search_failures = 0
    return src


async def test_keyword_search_skips_all_failed_variants_without_raising(monkeypatch):
    monkeypatch.setattr(
        _cache, "cached", lambda _ns, _key, producer: producer()
    )  # bypass disk

    class BoomSvc:
        async def search(self, *a, **k):
            raise RuntimeError("simulated OpenAlex RetryError (500/504)")

    src = _bare_source(BoomSvc())
    rows = await src.keyword_search(
        '("a" OR "b")', limit=10
    )  # fanout -> base + SR + RCT
    assert rows == []  # graceful empty result, NOT an exception
    assert src.n_search_failures == 3  # all three variants skipped + counted


async def test_keyword_search_counts_only_failed_variants(monkeypatch):
    monkeypatch.setattr(_cache, "cached", lambda _ns, _key, producer: producer())

    class PartialSvc:
        async def search(self, query, *a, **k):
            if "SRCLAUSE" in query or "RCTCLAUSE" in query:  # SR/RCT variants fail
                raise RuntimeError("simulated 500")
            return (
                pd.DataFrame()
            )  # base variant succeeds (empty df -> no rows, but no failure)

    src = _bare_source(PartialSvc())
    rows = await src.keyword_search('("a" OR "b")', limit=10)
    assert rows == []
    assert (
        src.n_search_failures == 2
    )  # only SR + RCT skipped; the successful base did NOT increment


def test_strip_openalex_wildcards_removes_star_and_question_only():
    # gpt-4.1 sometimes emits a wildcard despite the prompt forbidding it; OpenAlex's stemmed
    # field 400s on it. Dropping the char leaves the stem (matched fine by the stemmed field).
    assert (
        strip_openalex_wildcards('("crop yield" OR agricultur* OR harvest?)')
        == '("crop yield" OR agricultur OR harvest)'
    )
    assert strip_openalex_wildcards("no wildcards here") == "no wildcards here"


def test_clean_title_for_filter_strips_filter_breaking_punctuation():
    # Commas/colons delimit OpenAlex filters; parens/dashes 400 the title.search request.
    raw = "VenUS IV (Venous leg Ulcer Study IV) – compression hosiery: an RCT, mixed-model"
    cleaned = _clean_title_for_filter(raw)
    assert not any(ch in cleaned for ch in ",:()–")
    assert "VenUS IV" in cleaned and "compression hosiery" in cleaned  # words preserved
    assert "  " not in cleaned  # whitespace collapsed
    assert _clean_title_for_filter(None) == ""


def test_clean_abstract_maps_sentinel_and_blank_to_none():
    assert _clean_abstract(None) is None
    assert _clean_abstract("   ") is None
    assert _clean_abstract("No abstract available") is None
    assert _clean_abstract("A genuine abstract.") == "A genuine abstract."


def test_row_to_candidate_cleans_sentinel_and_carries_fields():
    c = _row_to_candidate(
        {
            "id": "https://openalex.org/W1",
            "title": "T",
            "abstract": "No abstract available",
            "year": 2019,
            "cited_by_count": 5,
            "reference_count": 12,
            "doi": "https://doi.org/10.x",
        }
    )
    assert c.paper_id == "https://openalex.org/W1"
    assert c.abstract is None  # sentinel -> None
    assert (c.year, c.cited_by_count, c.reference_count) == (2019, 5, 12)
    assert c.doi == "https://doi.org/10.x"


def test_work_to_row_reads_abstract_via_item_access_and_counts_refs():
    work = {
        "id": "W1",
        "title": "T",
        "abstract": "Some abstract",  # item access returns it (PyAlex reinverts here live)
        "publication_year": 2021,
        "cited_by_count": 3,
        "referenced_works": ["W2", "W3", "W4"],
    }
    row = _work_to_row(work)
    assert row["abstract"] == "Some abstract"
    assert row["year"] == 2021
    assert row["reference_count"] == 3  # this work's OWN bibliography size


def test_work_to_row_missing_abstract_key_is_none():
    row = _work_to_row({"id": "W1"})  # no "abstract" key -> KeyError caught -> None
    assert row["abstract"] is None
    assert row["reference_count"] == 0


def test_df_to_rows_maps_columns_and_handles_empty():
    df = pd.DataFrame(
        [
            {
                "id": "W1",
                "title": "T",
                "abstract": "A",
                "publication_year": 2020,
                "cited_by_count": 7,
                "doi": "10.x",
            }
        ]
    )
    rows = _df_to_rows(df)
    assert rows[0]["year"] == 2020 and rows[0]["cited_by_count"] == 7
    assert rows[0]["reference_count"] == 0  # search() doesn't return referenced_works
    assert _df_to_rows(pd.DataFrame()) == []
