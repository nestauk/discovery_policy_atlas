"""Per-arm latency instrumentation — a 5-bucket stage timer.

`broad_search` (Arms B/C) makes several LLM calls (query formulation, reformulation, parametric
suggestions, relevance judging) and several API calls (keyword/dense search, snowball
citations/references, Cohere rerank). A binary judge/non-judge split would lump the non-judge LLM
work in with the API work and hide exactly the thing that differs across arms (Arm C's dense +
snowball under the 1 req/s S2 throttle). So we attribute wall-time to five buckets:

  formulate_s  LLM: formulate + reformulate + parametric suggest
  retrieve_s   API: keyword + dense search
  snowball_s   API: citations + references (the B/C volume driver)
  rerank_s     API: Cohere rerank
  judge_s      LLM: relevance judging (shared cache → standalone cost reconstructed from n_judged)

Arm A has no snowball/rerank/dense legs, so it reports those buckets as 0.0 — which is the honest
picture. `other_s` (= total − Σ buckets) absorbs dedupe / BTS sampling / object setup (cheap CPU).

The buckets are timed by wrapping each `await` in `with timer.track("<bucket>"):`. The arms run one
query at a time and `broad_search` awaits sequentially, so the wall-time around an await ≈ that
call's latency (no concurrent coroutine steals the clock). Judging is cross-arm cached, so
`judge_s` is the RAW (cache-contaminated) time — the standalone judge cost is reconstructed later
from `n_judged × a measured per-paper rate` (see plots.standalone_latency).

REPL usage (no main()/argparse — spec conventions):
    from _timing import StageTimer, stage_timings
    timer = StageTimer()
    with timer.track("retrieve"):
        ...                              # an await
    stage_timings(total_s=12.0, timer=timer, n_judged=250)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

BUCKETS = ("formulate", "retrieve", "snowball", "rerank", "judge")


@dataclass
class StageTimer:
    """Accumulates wall-seconds per stage bucket. Pass one through a run; omit it (smoke/tests) and
    a throwaway timer is used at zero cost."""

    seconds: dict = field(default_factory=lambda: {b: 0.0 for b in BUCKETS})

    @contextmanager
    def track(self, bucket: str):
        if bucket not in self.seconds:
            raise KeyError(
                f"unknown timing bucket {bucket!r}; expected one of {BUCKETS}"
            )
        t = time.monotonic()
        try:
            yield
        finally:
            self.seconds[bucket] += time.monotonic() - t


def stage_timings(total_s: float, timer: StageTimer, n_judged: int) -> dict:
    """Per-arm-query timing record persisted alongside results: the five buckets + total + the
    unattributed remainder (`other_s`) + `n_judged` (drives the standalone judge reconstruction)."""
    attributed = sum(timer.seconds.values())
    out = {f"{k}_s": round(v, 3) for k, v in timer.seconds.items()}
    out["total_s"] = round(total_s, 3)
    out["other_s"] = round(max(total_s - attributed, 0.0), 3)
    out["n_judged"] = n_judged
    return out
