"""Offline tests for query_analysis.py — the pure QueryIntent -> weights mapping.

The LLM calls (analyse_query) are exercised live in smoke/phase3a_core.py; here we test only
the pure dataclass logic: presence-vs-direction collapse and the §4.3 Step-5 weight table.
"""

from __future__ import annotations

from config import CONFIG
from query_analysis import QueryAnalysis, QueryIntent


def test_weight_key_all_four_combinations():
    assert QueryIntent().weight_key() == "just_topic"
    assert QueryIntent(recency="recent").weight_key() == "recent"
    assert QueryIntent(recency="early").weight_key() == "recent"  # direction-agnostic
    assert QueryIntent(centrality="central").weight_key() == "influential"
    assert QueryIntent(centrality="less").weight_key() == "influential"
    assert (
        QueryIntent(recency="recent", centrality="central").weight_key()
        == "recent_and_influential"
    )
    assert (
        QueryIntent(recency="early", centrality="less").weight_key()
        == "recent_and_influential"
    )


def test_weights_match_config_table():
    # The weights() helper must read straight from the frozen config table (single source).
    assert QueryIntent().weights() == CONFIG.blend.intent_weights["just_topic"]
    assert (
        QueryIntent(recency="recent").weights() == CONFIG.blend.intent_weights["recent"]
    )
    assert (
        QueryIntent(centrality="central").weights()
        == CONFIG.blend.intent_weights["influential"]
    )
    assert (
        QueryIntent(recency="recent", centrality="central").weights()
        == CONFIG.blend.intent_weights["recent_and_influential"]
    )


def test_weights_sum_to_one_for_every_intent():
    # Every blend-weight vector must sum to 1 so content/recency/centrality stay a convex mix.
    for combo in (
        QueryIntent(),
        QueryIntent(recency="recent"),
        QueryIntent(centrality="central"),
        QueryIntent(recency="recent", centrality="central"),
    ):
        assert abs(sum(combo.weights()) - 1.0) < 1e-9


def test_default_intent_is_just_topic_and_content_heavy():
    # The default (no intent) should put ~all weight on content (0.95) — recency/centrality
    # are tiny tie-breakers, never the driver, unless the query asks for them.
    w_content, w_recent, w_central = QueryIntent().weights()
    assert w_content > w_recent and w_content > w_central


def test_query_analysis_is_a_plain_container():
    a = QueryAnalysis(
        raw_query="latest X", content="X", intent=QueryIntent(recency="recent")
    )
    assert a.raw_query == "latest X"
    assert a.content == "X"
    assert a.intent.weight_key() == "recent"
