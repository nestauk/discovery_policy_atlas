"""Offline tests for the OpenAlex heavy-query rate limit (`retrieval/_openalex_throttle.py`).

No network, no pyalex import for the pure bits: we pin
  - `_operator_count` — counts OR/AND/NOT the way OpenAlex does (the >5 metric the gate keys on),
  - `_SyncRateThrottle` — the sync 1-req/s serialiser, asserted with an injected fake clock/sleep so
    the wait math is checked without sleeping a real second (mirrors test_s2_client's throttle tests),
  - `install_rate_limit` — idempotent patch that gates ONLY heavy URLs (simple calls pass through).
"""

from __future__ import annotations

from retrieval._openalex_throttle import (
    _HEAVY_OPERATOR_THRESHOLD,
    _operator_count,
    _SyncRateThrottle,
    install_rate_limit,
)


# --------------------------------------------------------------------------- #
# _operator_count — OpenAlex's OR/AND/NOT metric, on the decoded URL
# --------------------------------------------------------------------------- #
def test_operator_count_zero_for_simple_id_or_filter_calls():
    # snowball's bread-and-butter calls carry no boolean operators -> never gated.
    assert _operator_count("https://api.openalex.org/works/W123") == 0
    assert _operator_count("https://api.openalex.org/works?filter=cited_by:W123") == 0


def test_operator_count_counts_or_and_not_tokens():
    url = 'https://api.openalex.org/works?filter=title_and_abstract.search:("a" OR "b" AND "c")'
    assert _operator_count(url) == 2


def test_operator_count_decodes_percent_encoding():
    # The real failing URLs are percent/plus-encoded; the count must work post-decode.
    enc = "https://api.openalex.org/works?filter= taa.search:(%22a%22+OR+%22b%22+OR+%22c%22)"
    assert _operator_count(enc) == 2


def test_operator_count_ignores_operators_inside_words():
    # "AND"/"OR" embedded in a term must not be miscounted (word-boundary match).
    assert _operator_count('search:("OREGON" "ANDROID" "NORTH")') == 0


def test_heavy_query_clears_the_threshold():
    # A 3-group AND-of-ORs like the q02 Arm B boolean is comfortably over 5 operators.
    url = 'search:(("a" OR "b" OR "c") AND ("d" OR "e") AND ("f" OR "g"))'
    assert _operator_count(url) > _HEAVY_OPERATOR_THRESHOLD


# --------------------------------------------------------------------------- #
# _SyncRateThrottle — 1 req/s serialiser, asserted with an injected fake clock/sleep
# --------------------------------------------------------------------------- #
def _fake_clock_and_sleep(start: float = 0.0):
    clock = {"t": start}
    slept: list[float] = []

    def sleep(d):  # records the wait; advances the fake clock as a real sleep would
        slept.append(d)
        clock["t"] += d

    return clock, slept, (lambda: clock["t"]), sleep


def test_throttle_first_call_does_not_wait():
    _clock, slept, clock, sleep = _fake_clock_and_sleep(100.0)
    th = _SyncRateThrottle(1.1, clock=clock, sleep=sleep)
    th.wait()
    assert slept == []  # nothing in flight yet -> no throttle


def test_throttle_back_to_back_call_waits_min_interval():
    _clock, slept, clock, sleep = _fake_clock_and_sleep(0.0)
    th = _SyncRateThrottle(1.1, clock=clock, sleep=sleep)
    th.wait()  # t=0, sets _last
    th.wait()  # immediately again, no time passed -> must wait the full interval
    assert len(slept) == 1
    assert abs(slept[0] - 1.1) < 1e-9


def test_throttle_no_wait_when_interval_already_elapsed():
    clock_d, slept, clock, sleep = _fake_clock_and_sleep(0.0)
    th = _SyncRateThrottle(1.1, clock=clock, sleep=sleep)
    th.wait()  # t=0
    clock_d["t"] += 2.0  # 2s of real work happened between requests (> 1.1 interval)
    th.wait()
    assert slept == []  # already spaced far enough apart -> no throttle needed


# --------------------------------------------------------------------------- #
# install_rate_limit — gates heavy URLs only, idempotent
# --------------------------------------------------------------------------- #
class _FakeBase:
    """Stand-in for pyalex's BaseOpenAlex: records the URLs its _get_from_url receives."""

    calls: list[str] = []

    def _get_from_url(self, url, session=None):
        type(self).calls.append(url)
        return {"url": url}


def test_install_gates_heavy_passes_simple_and_is_idempotent(monkeypatch):
    import pyalex.api as api

    monkeypatch.setattr(api, "BaseOpenAlex", _FakeBase, raising=True)
    _FakeBase.calls = []

    # Only the FIRST heavy call is made below, and a throttle's first call never sleeps (nothing in
    # flight yet) — so this exercises the gate's routing (heavy vs simple) without any real wait.
    install_rate_limit(0.5)
    # Idempotent: a second install must NOT double-wrap.
    first = api.BaseOpenAlex._get_from_url
    install_rate_limit(0.5)
    assert api.BaseOpenAlex._get_from_url is first

    inst = api.BaseOpenAlex()
    simple = "https://api.openalex.org/works/W1"  # 0 operators
    heavy = (
        'search:(("a" OR "b" OR "c") AND ("d" OR "e") AND ("f" OR "g"))'
    )  # >5 operators
    inst._get_from_url(simple)
    inst._get_from_url(heavy)
    # Both reach the underlying call; the gate only changes timing, never drops/alters the request.
    assert _FakeBase.calls == [simple, heavy]
    # The wrapper is marked so re-install is a no-op.
    assert getattr(api.BaseOpenAlex._get_from_url, "_rate_limited", False) is True
