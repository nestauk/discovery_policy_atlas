"""Offline tests for the shared SR/RCT fanout helper (used by Arms A and B)."""

from __future__ import annotations

from retrieval._fanout import fanout


def test_fanout_base_only_when_disabled():
    assert fanout("Q", False, "SR", "RCT") == [("base", "Q")]


def test_fanout_adds_sr_and_rct_when_enabled():
    assert fanout("Q", True, "SR", "RCT") == [
        ("base", "Q"),
        ("systematic_review", "(Q) AND SR"),
        ("rct", "(Q) AND RCT"),
    ]
