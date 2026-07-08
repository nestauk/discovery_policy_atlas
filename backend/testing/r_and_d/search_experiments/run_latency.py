"""Quick latency probe — run all three arms over a SMALL query subset to get a representative
per-stage latency figure, without the hours-long full run.

Everything in the experiment is cached (retrieval search/snowball, judging, rerank), so simply
re-running already-run queries measures CACHE HITS, not latency. This probe therefore runs COLD: it
redirects every cache root to a throwaway temp dir for the duration (restored on exit), so the calls
actually re-pay their cost AND your real caches under results/ are never touched or polluted. Runs
with persist=False, so results/arms/ is not clobbered either — timings are collected in memory and
plotted straight away.

Cost knob = `n` (number of queries). You can't measure cold latency without incurring it once, and
judging is the heaviest stage, so a cold probe at n=3 re-pays ~15% of the full 20-query run. For a
FAST retrieval-only picture (the A/B/C differentiator) pass `cold_judge=False` + a `judge_rate`: the
search/snowball legs run cold while the judge bar is reconstructed from the supplied per-paper rate.

Run it directly (mirrors run_experiment.py — __main__-guarded asyncio.run, no argparse):
    uv run run_latency.py                                  # default: n=3, fully cold
    LATENCY_N=2 uv run run_latency.py                      # fewer queries (faster)
    LATENCY_COLD_JUDGE=0 LATENCY_JUDGE_RATE=0.04 uv run run_latency.py   # fast retrieval-only

Or call the helper from a REPL:
    import asyncio
    from run_latency import run_latency_probe
    by_arm, png = asyncio.run(run_latency_probe(n=3))      # fully-cold, all stages
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import config  # noqa: F401  -- triggers backend/.env bootstrap before app.* (via arms)
from core import judge as _judge_mod
from core import ranking as _ranking_mod
from reporting.plots import plot_latency
from queries.loader import load_queries
from retrieval import _cache as _cache_mod

logger = logging.getLogger(__name__)
_PROBE_PLOT = (
    Path(__file__).resolve().parent / "results" / "plots" / "latency_probe.png"
)


@contextmanager
def _redirected_caches(*, cold_judge: bool):
    """Point the experiment's disk caches at a throwaway temp dir so the probe runs COLD, then
    restore the originals (and delete the temp dir) on exit. Retrieval + rerank are always
    redirected (the differentiator); the judge cache only when `cold_judge` (else it stays warm and
    the judge bar is reconstructed from a supplied rate). `query_analysis` is left warm — it runs
    before the timed buckets, so re-paying it would add cost without measurement."""
    tmp = Path(tempfile.mkdtemp(prefix="latency_probe_"))
    saved: dict = {}

    def patch(mod, attr, val):
        saved[(mod, attr)] = getattr(mod, attr)
        setattr(mod, attr, val)

    patch(
        _cache_mod, "CACHE_ROOT", tmp / "retrieval"
    )  # search/snowball/formulate/suggest
    patch(_ranking_mod, "RERANK_DIR", tmp / "rerank")  # cohere
    if cold_judge:
        patch(_judge_mod, "JUDGE_DIR", tmp / "judgements")
        patch(_judge_mod, "CRITERIA_DIR", tmp / "judgements" / "criteria")
        patch(_judge_mod, "RAW_DIR", tmp / "judgements" / "raw")
        patch(
            _judge_mod, "JUDGEMENTS_PARQUET", tmp / "judgements" / "judgements.parquet"
        )
    try:
        yield
    finally:
        for (mod, attr), val in saved.items():
            setattr(mod, attr, val)
        shutil.rmtree(tmp, ignore_errors=True)


async def run_latency_probe(
    n: int = 3,
    *,
    cold_judge: bool = True,
    judge_rate: float | None = None,
    cooldown_s: float = 10.0,
    queries=None,
    persist: bool = False,
    out: Path | None = None,
):
    """Run arms A/B/C over the first `n` queries COLD, collect per-stage timings, plot latency.

    Returns (by_arm, png_path). `by_arm` is the in-memory {arm: {qid: {"timings": ...}}} the plot
    consumes — nothing is written under results/arms/ (persist=False). With `cold_judge=False` the
    judge stage stays cached (fast); pass `judge_rate` (cold s/paper) so its bar is reconstructed.

    Resilient per arm-query (try/except, like run_experiment.py) so one arm's failure doesn't sink
    the probe. `cooldown_s` pauses between arms — the cold re-fetch bursts OpenAlex, and Arm B's
    search right after Arm A's heavy pagination otherwise lands in the transient 500 throttle window
    (FINDINGS 2026-06-26); the pause lets it clear. The cooldown is BETWEEN run_query calls, so it
    never enters any arm's measured total_s.
    """
    from arms import arm_a, arm_b, arm_c  # lazy: arm import pulls backend env

    arms = (("arm_a", arm_a), ("arm_b", arm_b), ("arm_c", arm_c))
    qs = list(queries or load_queries())[:n]
    by_arm: dict[str, dict[str, dict]] = {name: {} for name, _ in arms}
    failures: list[tuple[str, str, str]] = []

    print(
        f"latency probe: {len(qs)} queries × 3 arms, cold_judge={cold_judge}, persist={persist}, "
        f"cooldown={cooldown_s}s (real caches + results/arms untouched)"
    )
    with _redirected_caches(cold_judge=cold_judge):
        for i, q in enumerate(qs, 1):
            print(f"[{i}/{len(qs)}] {q.query_id}")
            for ai, (name, mod) in enumerate(arms):
                if ai > 0 and cooldown_s > 0:
                    await asyncio.sleep(
                        cooldown_s
                    )  # let the OpenAlex throttle window clear
                try:
                    res = await mod.run_query(q, persist=persist)
                except Exception as e:  # transient 500s etc. — log + continue (run_experiment.py pattern)
                    logging.exception("%s failed on %s", name, q.query_id)
                    print(f"   {name}: FAILED ({type(e).__name__}: {e})")
                    failures.append((q.query_id, name, f"{type(e).__name__}: {e}"))
                    continue
                by_arm[name][q.query_id] = {"timings": res.timings}
                t = res.timings
                print(
                    f"   {name}: total={t['total_s']}s "
                    f"(formulate={t['formulate_s']} retrieve={t['retrieve_s']} "
                    f"snowball={t['snowball_s']} rerank={t['rerank_s']} judge={t['judge_s']})"
                )

    print(f"\nPROBE DONE — {len(failures)} arm-query failure(s)")
    for qid, name, err in failures:
        print(f"   FAILED {qid} {name}: {err[:160]}")
    if not any(by_arm.values()):
        print("no successful arm runs — nothing to plot.")
        return by_arm, None

    path = plot_latency(by_arm=by_arm, judge_rate=judge_rate, out=out or _PROBE_PLOT)
    print(f"latency plot -> {path}")
    return by_arm, path


# Direct-run entry (`uv run run_latency.py`), same pattern as run_experiment.py. Knobs come from env
# vars so one file serves every case without argparse (spec conventions): LATENCY_N (int),
# LATENCY_COLD_JUDGE (0/1), LATENCY_JUDGE_RATE (float, used when cold_judge=0).
# Guarded so importing this module can't start a live probe.
if __name__ == "__main__":
    _rate_env = os.environ.get("LATENCY_JUDGE_RATE")
    asyncio.run(
        run_latency_probe(
            n=int(os.environ.get("LATENCY_N", "3")),
            cold_judge=os.environ.get("LATENCY_COLD_JUDGE", "1") != "0",
            judge_rate=float(_rate_env) if _rate_env else None,
        )
    )
