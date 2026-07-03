"""Offline tests for the curated query set + its loader (Phase 5, spec §4.1).

Two halves: (1) pin the real committed `queries.jsonl` against the curation invariants (count in the
~20-30 band, unique ids, non-empty arm input, valid densities, stratification coverage); (2) the
loader's validation rejects malformed records (built in-memory via tmp files — no real-file coupling).
"""

from __future__ import annotations

import json

import pytest

from queries.loader import DEFAULT_PATH, DENSITIES, EXCLUDED_QUERY_IDS, load_queries

# --------------------------------------------------------------------------- #
# The real artefact (queries/queries.jsonl)
# --------------------------------------------------------------------------- #
# queries.jsonl is gitignored (prod-derived data), so a fresh clone doesn't have it.
requires_query_set = pytest.mark.skipif(
    not DEFAULT_PATH.exists(),
    reason="queries/queries.jsonl not built yet — run ONBOARDING.md §4.1 steps 1-2",
)


@requires_query_set
def test_query_set_loads_and_is_in_spec_band():
    qs = load_queries()
    assert 20 <= len(qs) <= 30  # spec §4.1: ~20-30 curated queries


@requires_query_set
def test_excluded_queries_are_dropped():
    # q01/q23 (over-folded → OpenAlex 500s, 2026-06-26) live in queries.jsonl for provenance but
    # load_queries skips them, so arms/metrics never see them.
    loaded = {q.query_id for q in load_queries()}
    assert EXCLUDED_QUERY_IDS  # guard against an accidentally-emptied set
    assert not (loaded & EXCLUDED_QUERY_IDS)


@requires_query_set
def test_ids_unique_and_arm_input_nonempty():
    qs = load_queries()
    ids = [q.query_id for q in qs]
    assert len(ids) == len(set(ids))  # unique query_id
    assert all(
        q.query_text.strip() for q in qs
    )  # query_text is the arm input — never empty


@requires_query_set
def test_densities_valid_and_all_strata_present():
    qs = load_queries()
    present = {q.literature_density for q in qs}
    assert present <= DENSITIES
    assert (
        present == DENSITIES
    )  # stratification intent: dense + medium + sparse all represented


@requires_query_set
def test_use_case_diversity_and_context_retained():
    qs = load_queries()
    distinct_uc = {q.use_case for q in qs if q.use_case}
    assert len(distinct_uc) >= 4  # stratified across several use cases, not one bucket
    assert all(
        isinstance(q.original_search_context, dict) and q.original_search_context
        for q in qs
    )


# --------------------------------------------------------------------------- #
# Loader validation (in-memory malformed records)
# --------------------------------------------------------------------------- #
def _write(tmp_path, *records):
    p = tmp_path / "q.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records))
    return p


def _rec(**over):
    base = {
        "query_id": "q99",  # not in loader.EXCLUDED_QUERY_IDS — exercise the validation path
        "query_text": "a question",
        "use_case": "rapid_brief",
        "literature_density": "dense",
        "original_search_context": {"research_question": "a question"},
    }
    base.update(over)
    return base


def test_loader_rejects_duplicate_ids(tmp_path):
    p = _write(tmp_path, _rec(query_id="q01"), _rec(query_id="q01"))
    with pytest.raises(ValueError, match="duplicate query_id"):
        load_queries(p)


def test_loader_rejects_bad_density(tmp_path):
    p = _write(tmp_path, _rec(literature_density="huge"))
    with pytest.raises(ValueError, match="literature_density"):
        load_queries(p)


def test_loader_rejects_empty_query_text(tmp_path):
    p = _write(tmp_path, _rec(query_text="   "))
    with pytest.raises(ValueError, match="empty query_text"):
        load_queries(p)


def test_loader_rejects_missing_field(tmp_path):
    rec = _rec()
    del rec["literature_density"]
    p = _write(tmp_path, rec)
    with pytest.raises(ValueError, match="missing required field"):
        load_queries(p)


def test_loader_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_queries(tmp_path / "nope.jsonl")
