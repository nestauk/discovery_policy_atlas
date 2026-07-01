"""Offline tests for retrieval._cache — the content-addressed disk cache (resumability seam).

Guards the property the whole Phase-4 retrieval layer relies on: a call wrapped in `cached(...)`
hits the network exactly once, key lookup is order-independent, and a miss is a clean None.
`CACHE_ROOT` is monkeypatched to a tmp dir so tests never touch results/.
"""

from __future__ import annotations

from retrieval import _cache


def test_roundtrip_and_key_order_independence(tmp_path, monkeypatch):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)
    _cache.save("ns", {"a": 1, "b": 2}, [{"x": 1}])
    # same key parts in a different dict order resolve to the same entry (canonical sort_keys).
    assert _cache.load("ns", {"b": 2, "a": 1}) == [{"x": 1}]


def test_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)
    assert _cache.load("ns", {"a": 1}) is None


def test_namespaces_do_not_collide(tmp_path, monkeypatch):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)
    _cache.save("openalex.search", {"k": 1}, "A")
    _cache.save("openalex.cites", {"k": 1}, "B")  # same key, different namespace
    assert _cache.load("openalex.search", {"k": 1}) == "A"
    assert _cache.load("openalex.cites", {"k": 1}) == "B"


async def test_cached_runs_producer_once_then_serves_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)
    calls: list[int] = []

    async def producer():
        calls.append(1)
        return {"v": 42}

    r1 = await _cache.cached("ns", {"k": 1}, producer)
    r2 = await _cache.cached("ns", {"k": 1}, producer)
    assert r1 == r2 == {"v": 42}
    assert len(calls) == 1  # second call served from disk, producer not re-run


async def test_cached_force_reruns_producer(tmp_path, monkeypatch):
    monkeypatch.setattr(_cache, "CACHE_ROOT", tmp_path)
    calls: list[int] = []

    async def producer():
        calls.append(1)
        return len(calls)

    await _cache.cached("ns", {"k": 1}, producer)
    again = await _cache.cached("ns", {"k": 1}, producer, force=True)
    assert again == 2 and len(calls) == 2
