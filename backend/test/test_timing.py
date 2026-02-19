"""Unit tests for the pipeline timing persistence module."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.timing import (
    persist_timing,
    persist_timings_batch,
    get_timings_for_project,
)


@pytest.fixture
def mock_supabase():
    """Return a mock Supabase client with a chainable .table().insert().execute() API."""
    client = MagicMock()
    with patch("app.services.timing._get_supabase", return_value=client):
        yield client


# ── persist_timing ────────────────────────────────────────────────────────


def test_persist_timing_inserts_row(mock_supabase):
    persist_timing("proj-1", "analysis", "references", 12.5, document_count=42)

    mock_supabase.table.assert_called_once_with("pipeline_timings")
    insert_call = mock_supabase.table().insert.call_args
    row = insert_call[0][0]

    assert row["project_id"] == "proj-1"
    assert row["pipeline_type"] == "analysis"
    assert row["stage_name"] == "references"
    assert row["duration_seconds"] == 12.5
    assert row["document_count"] == 42
    assert "id" in row
    assert "created_at" in row


def test_persist_timing_defaults_metadata_to_empty_dict(mock_supabase):
    persist_timing("proj-1", "synthesis", "generate_briefing", 3.0)

    row = mock_supabase.table().insert.call_args[0][0]
    assert row["metadata"] == {}
    assert row["document_count"] is None


def test_persist_timing_swallows_errors(mock_supabase):
    mock_supabase.table().insert().execute.side_effect = RuntimeError("boom")

    # Must not raise
    persist_timing("proj-1", "analysis", "references", 1.0)


# ── persist_timings_batch ─────────────────────────────────────────────────


def test_persist_timings_batch_inserts_multiple_rows(mock_supabase):
    timings = [
        {"stage_name": "references", "duration_seconds": 10.0, "document_count": 50},
        {"stage_name": "extraction", "duration_seconds": 20.0},
    ]

    persist_timings_batch("proj-2", "analysis", timings)

    rows = mock_supabase.table().insert.call_args[0][0]
    assert len(rows) == 2
    assert rows[0]["stage_name"] == "references"
    assert rows[0]["document_count"] == 50
    assert rows[1]["stage_name"] == "extraction"
    assert rows[1]["document_count"] is None


def test_persist_timings_batch_noop_on_empty_list(mock_supabase):
    persist_timings_batch("proj-2", "analysis", [])

    mock_supabase.table.assert_not_called()


def test_persist_timings_batch_swallows_errors(mock_supabase):
    mock_supabase.table().insert().execute.side_effect = RuntimeError("boom")

    persist_timings_batch(
        "proj-2", "analysis", [{"stage_name": "x", "duration_seconds": 1.0}]
    )


# ── get_timings_for_project ──────────────────────────────────────────────


def test_get_timings_for_project_returns_data(mock_supabase):
    expected = [{"stage_name": "references", "duration_seconds": 5.0}]
    mock_supabase.table().select().eq().order().execute.return_value = MagicMock(
        data=expected
    )

    result = get_timings_for_project("proj-3")

    assert result == expected


def test_get_timings_for_project_with_pipeline_filter(mock_supabase):
    mock_supabase.table().select().eq().order().eq().execute.return_value = MagicMock(
        data=[]
    )

    result = get_timings_for_project("proj-3", pipeline_type="synthesis")

    assert result == []
