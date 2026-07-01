"""Client-side rate limit for OpenAlex's heavy-query governor (>5 boolean operators → 1 req/s).

OpenAlex hard-caps any query with **more than 5 boolean operators (OR/AND/NOT)** to **1 request/second
per client**, and intermittently 500s very heavy booleans (FINDINGS 2026-06-30: q02's exact Arm B query —
a 7-facet nested AND, 71 operators — alternates 500 ⇄ 429 from an idle network; the 429 body states the
rule verbatim). A ≤5-operator control returns 200 in ~150ms. So we gate ONLY heavy queries to ≤1 req/s.

**Why heavy-only, not blanket.** The cap is specific to >5-operator queries; simple calls aren't governed.
Arm B's snowball fires ~400 mostly-simple `Works` calls/query-iteration (single-id lookups,
cited_by/referenced_works filters — 0-few operators). Pacing *those* to 1 req/s would add ~7 min/iteration
for nothing. The transient burst-500s those bursts *can* cause are already handled by the hardened pyalex
retry (`_backend.get_openalex_service`); this gate is only for the documented heavy-query limit.

**Why patch pyalex.** Every OpenAlex call in the experiment — Arm A's `OpenAlexService.search` pagination
AND Arm B's raw `Works` snowball — funnels through one method, `pyalex.api.BaseOpenAlex._get_from_url`
(→ `session.get`). Gating there (conditioned on the URL's operator count) covers every call path from a
single seam. Result caches sit ABOVE pyalex, so cache hits never reach it → they cost zero rate budget
(the same property the S2 client relies on). This is the synchronous twin of `s2_client._RateThrottle`:
pyalex issues requests synchronously, so it uses `threading.Lock` + `time.sleep` rather than asyncio.

Experiment-only: patches the pyalex global in-process; production (a separate deployment) is untouched.

REPL usage:
    from retrieval._openalex_throttle import _operator_count
    _operator_count('https://api.openalex.org/works?filter=...search:("a" OR "b")')  # -> 1
"""

from __future__ import annotations

import re
import threading
import time
from urllib.parse import unquote

# OpenAlex's own threshold: queries with MORE THAN 5 boolean operators are limited to 1 req/s.
_HEAVY_OPERATOR_THRESHOLD = 5
# Boolean operators are uppercase, space-delimited tokens in the query DSL (search terms are quoted),
# so a word-boundary match on the decoded URL counts them the way OpenAlex does. Over-counting only
# costs a needless wait; under-counting only risks a 429 the retry absorbs — both fail safe.
_OPERATOR_RE = re.compile(r"(?<![A-Za-z])(?:OR|AND|NOT)(?![A-Za-z])")


def _operator_count(url: str) -> int:
    """Count OR/AND/NOT boolean operators in an OpenAlex request URL (decoded), OpenAlex's own metric."""
    return len(_OPERATOR_RE.findall(unquote(url)))


class _SyncRateThrottle:
    """Serialise calls to >= `min_interval` apart (clock/sleep injectable for tests).

    Synchronous twin of `s2_client._RateThrottle` — pyalex issues requests synchronously, so this uses a
    `threading.Lock` + `time.sleep` instead of asyncio. The lock also serialises concurrent callers (Arm B
    may issue OpenAlex requests from executor threads), so the limit holds CUMULATIVELY, not per-thread.
    """

    def __init__(self, min_interval: float, *, clock=None, sleep=None):
        self._min = min_interval
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._last: float | None = None

    def wait(self) -> None:
        with self._lock:  # one heavy request in flight at a time (cumulative limit)
            if self._last is not None:
                wait_for = self._min - (self._clock() - self._last)
                if wait_for > 0:
                    self._sleep(wait_for)
            self._last = self._clock()


def install_rate_limit(min_interval: float) -> None:
    """Idempotently wrap `pyalex.api.BaseOpenAlex._get_from_url` to gate HEAVY (>5-operator) requests.

    Safe to call repeatedly (every `get_openalex_service`/`get_works_cls` does): the wrapper installs once,
    guarded by a sentinel on the patched function. Simple (≤5-operator) requests pass straight through, so
    snowball's many lightweight calls run at full speed. Lazy `pyalex` import keeps this module import-clean
    for the offline tests.
    """
    import pyalex.api as _api

    orig = _api.BaseOpenAlex._get_from_url
    if getattr(orig, "_rate_limited", False):
        return  # already installed (idempotent)

    throttle = _SyncRateThrottle(min_interval)

    def _throttled(self, url, session=None):
        if _operator_count(url) > _HEAVY_OPERATOR_THRESHOLD:
            throttle.wait()  # only heavy queries are governed; simple calls pass straight through
        return orig(self, url, session=session)

    _throttled._rate_limited = True
    _api.BaseOpenAlex._get_from_url = _throttled
