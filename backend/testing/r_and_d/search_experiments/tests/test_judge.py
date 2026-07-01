"""Offline tests for the frozen judge's pure logic (no LLM / no backend env).

Covers the non-API surface of judge.py: dynamic output-field construction, weight
normalisation, per-row scoring (cross-checked against metrics.py), and parquet-cache
consolidation from raw JSONL shards. The two LLM calls (criteria extraction, per-paper
judging) are smoke-tested live by the user — see README.

Run:  uv run pytest test_judge.py -v
"""

from __future__ import annotations

import json

import pytest

from judge import (
    RelevanceCriterion,
    _consolidate,
    _format_paper,
    _normalise_weights,
    build_output_fields,
    score_row,
)


def _criteria():
    return [
        RelevanceCriterion(name="Intervention", description="X", weight=0.5),
        RelevanceCriterion(name="Outcome", description="Y", weight=0.5),
    ]


# --------------------------------------------------------------------------- #
# build_output_fields
# --------------------------------------------------------------------------- #
def test_build_output_fields_shape_and_identifiers():
    fields = build_output_fields(_criteria())
    # 2 criteria -> relevance + snippet each + 1 summary = 5 fields.
    assert len(fields) == 2 * 2 + 1
    names = [f["name"] for f in fields]
    assert names == [
        "criterion_1_relevance",
        "criterion_1_snippet",
        "criterion_2_relevance",
        "criterion_2_snippet",
        "relevance_summary",
    ]
    # Field names must be valid python identifiers (create_model requirement).
    assert all(n.isidentifier() for n in names)
    # The label vocabulary is spelled out in the relevance field description.
    rel_desc = fields[0]["description"]
    assert "Perfectly Relevant" in rel_desc and "Not Relevant" in rel_desc


# --------------------------------------------------------------------------- #
# weight normalisation
# --------------------------------------------------------------------------- #
def test_normalise_weights_renormalises_when_off():
    crit = [
        RelevanceCriterion(name="A", description="", weight=0.6),
        RelevanceCriterion(name="B", description="", weight=0.6),
    ]
    out = _normalise_weights(crit)
    assert sum(c.weight for c in out) == pytest.approx(1.0)
    assert out[0].weight == pytest.approx(0.5)


def test_normalise_weights_leaves_good_weights():
    crit = _criteria()
    out = _normalise_weights(crit)
    assert [c.weight for c in out] == [0.5, 0.5]


def test_normalise_weights_rejects_zero_sum():
    with pytest.raises(ValueError):
        _normalise_weights([RelevanceCriterion(name="A", description="", weight=0.0)])


# --------------------------------------------------------------------------- #
# score_row — cross-checks the metrics.py formulas through the judge path
# --------------------------------------------------------------------------- #
def test_score_row_partial_relevance():
    row = {
        "id": "W1",
        "criterion_1_relevance": "Perfectly Relevant",  # code 3
        "criterion_2_relevance": "Not Relevant",  # code 0
    }
    codes, score, level = score_row(row, _criteria())
    assert codes == [3, 0]
    assert score == pytest.approx(0.5)  # 0.5*3/3 + 0.5*0/3
    assert level == 1  # 0.5 <= 0.67


def test_score_row_all_perfect():
    row = {
        "id": "W2",
        "criterion_1_relevance": "Perfectly Relevant",
        "criterion_2_relevance": "Perfectly Relevant",
    }
    codes, score, level = score_row(row, _criteria())
    assert codes == [3, 3]
    assert score == pytest.approx(1.0)
    assert level == 3


def test_score_row_unknown_label_is_not_relevant(caplog):
    row = {
        "id": "W3",
        "criterion_1_relevance": "garbled",
        "criterion_2_relevance": None,
    }
    codes, score, level = score_row(row, _criteria())
    assert codes == [0, 0]
    assert score == 0.0
    assert level == 0


# --------------------------------------------------------------------------- #
# _format_paper — title-only flagging
# --------------------------------------------------------------------------- #
def test_format_paper_flags_title_only():
    assert "TITLE ONLY" in _format_paper({"title": "T", "abstract": ""})
    assert "TITLE ONLY" in _format_paper(
        {"title": "T", "abstract": "A", "text_basis": "title_only"}
    )
    assert "TITLE ONLY" not in _format_paper(
        {"title": "T", "abstract": "A real abstract."}
    )


# --------------------------------------------------------------------------- #
# _consolidate — raw JSONL shards -> scored rows (uses tmp dirs, no module state)
# --------------------------------------------------------------------------- #
def test_consolidate_scores_and_keys_by_query_and_paper(tmp_path):
    raw_dir = tmp_path / "raw"
    crit_dir = tmp_path / "criteria"
    raw_dir.mkdir()
    crit_dir.mkdir()

    # Cached criteria for query q001 (two equal-weight criteria).
    (crit_dir / "q001.json").write_text(
        json.dumps(
            {
                "query_id": "q001",
                "criteria": [
                    {"name": "Intervention", "description": "X", "weight": 0.5},
                    {"name": "Outcome", "description": "Y", "weight": 0.5},
                ],
            }
        )
    )
    # Raw judge output: one Perfect/Perfect paper (level 3), one Perfect/Not (level 1).
    rows = [
        {
            "id": "W1",
            "criterion_1_relevance": "Perfectly Relevant",
            "criterion_2_relevance": "Perfectly Relevant",
            "relevance_summary": "strong match",
            "model": "gpt-5.4-mini",
            "timestamp": "t0",
        },
        {
            "id": "W2",
            "criterion_1_relevance": "Perfectly Relevant",
            "criterion_2_relevance": "Not Relevant",
            "relevance_summary": "partial",
            "model": "gpt-5.4-mini",
            "timestamp": "t1",
        },
    ]
    with open(raw_dir / "q001.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    df = _consolidate(raw_dir, crit_dir)
    assert list(df["query_id"]) == ["q001", "q001"]
    assert dict(zip(df["paper_id"], df["level"])) == {"W1": 3, "W2": 1}
    # Perfect count (level==3) over the shard is 1 — what the normalizer would pool.
    assert (df["level"] == 3).sum() == 1


def test_consolidate_query_filter(tmp_path):
    raw_dir = tmp_path / "raw"
    crit_dir = tmp_path / "criteria"
    raw_dir.mkdir()
    crit_dir.mkdir()
    for qid in ("q001", "q002"):
        (crit_dir / f"{qid}.json").write_text(
            json.dumps({"criteria": [{"name": "A", "description": "", "weight": 1.0}]})
        )
        with open(raw_dir / f"{qid}.jsonl", "w") as f:
            f.write(
                json.dumps({"id": "W1", "criterion_1_relevance": "Not Relevant"}) + "\n"
            )

    df = _consolidate(raw_dir, crit_dir, query_ids=["q002"])
    assert set(df["query_id"]) == {"q002"}
