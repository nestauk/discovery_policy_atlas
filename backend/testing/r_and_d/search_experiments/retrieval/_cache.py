"""A tiny content-addressed disk cache for retrieval calls (spec §5/§7 "everything cached").

Every retrieval call (OpenAlex search, a `cites:` page, a Crossref lookup; later every S2
endpoint) is keyed by a stable hash of its (namespace, params) and persisted as JSON. Reruns
and cross-arm pooling then cost nothing, and the experiment is resumable after an interruption.
This is the same discipline judge.py / ranking.py / query_analysis.py already follow, factored
into one helper because Phase 4 has many more call sites.

Why hash-addressed rather than a human-readable filename: retrieval keys are arbitrary boolean
queries / paper ids that aren't filesystem-safe and can be long, so we hash a canonical JSON of
the key parts. The `namespace` (e.g. "openalex.search") keeps related calls in one subdir and
prevents collisions between, say, a keyword query and a paper id that stringify the same.

Crucially this caches JSON-SERIALISABLE payloads (lists of plain dicts), NOT `Candidate`
objects — the client maps dict→Candidate after the cache, so the cache stays small, stable,
and decoupled from the dataclass shape.

REPL usage (no main()/argparse — spec conventions):
    from retrieval._cache import cached
    async def fetch():            # the real network call, run only on a miss
        return [{"id": "W1", "title": "..."}]
    rows = await cached("openalex.search", {"q": query, "limit": 200}, fetch)
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# results/retrieval/<namespace>/<hash>.json — sits beside results/judgements, results/rerank.
CACHE_ROOT = Path(__file__).resolve().parent.parent / "results" / "retrieval"


def _key_hash(key: Any) -> str:
    """Stable sha1 of a canonical JSON of the key parts (sorted keys → order-independent)."""
    canonical = json.dumps(key, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:20]


def cache_path(namespace: str, key: Any) -> Path:
    return CACHE_ROOT / namespace / f"{_key_hash(key)}.json"


def load(namespace: str, key: Any) -> Any | None:
    """Return the cached payload for (namespace, key), or None on a miss."""
    path = cache_path(namespace, key)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save(namespace: str, key: Any, payload: Any) -> None:
    """Persist `payload` (must be JSON-serialisable) for (namespace, key)."""
    path = cache_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str))


async def cached(
    namespace: str,
    key: Any,
    producer: Callable[[], Awaitable[Any]],
    *,
    force: bool = False,
) -> Any:
    """Return the cached payload for (namespace, key), else run `producer()` and cache it.

    `producer` is an async thunk doing the actual network call — it is invoked ONLY on a miss
    (or `force=True`), so wrapping a call in `cached(...)` makes it a no-op on reruns. The
    payload it returns must be JSON-serialisable (lists/dicts of primitives).
    """
    if not force:
        hit = load(namespace, key)
        if hit is not None:
            logger.debug("cache hit %s/%s", namespace, _key_hash(key))
            return hit
    payload = await producer()
    save(namespace, key, payload)
    logger.debug("cache miss %s/%s -> stored", namespace, _key_hash(key))
    return payload
