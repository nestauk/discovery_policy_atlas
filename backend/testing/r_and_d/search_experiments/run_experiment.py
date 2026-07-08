"""Run the full experiment: all three arms over the whole curated query set → collect_results.

This is the experiment-EXECUTION entry point (not a smoke — smokes are small per-phase demos; this
produces the real dataset). It runs every query through Arm A / B / C, per-query interleaved so a
query's judgements are written once and reused across its arms via the shared cache, persisting
results/arms/{arm}/{qid}.json, then prints the headline metrics over all of it.

Expensive: 26 queries × 3 arms, mostly cache-cold, hours of wall-time (Arm C's 1.2s S2 throttle +
judging). Resilient per arm-query (try/except) so one failure doesn't sink the run; idempotent +
cache-warm, so re-running after a partial/interrupted run resumes cheaply. Run unbuffered for a
live log (and in the background for a long run):
    PYTHONUNBUFFERED=1 uv run run_experiment.py
"""

import asyncio
import logging
import time

import config  # noqa: F401  -- triggers backend/.env bootstrap (must precede app.* via arms)
from arms import arm_a, arm_b, arm_c
from reporting.collect_results import run_collect
from queries.loader import load_queries

logger = logging.getLogger(__name__)

_ARMS = [("A", arm_a), ("B", arm_b), ("C", arm_c)]


def _rule(title: str) -> None:
    print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)


async def run_experiment():
    queries = load_queries()
    n = len(queries)
    failures = []
    for i, q in enumerate(queries, 1):
        _rule(
            f"[{i}/{n}] {q.query_id} — use_case={q.use_case}, density={q.literature_density}"
        )
        for name, mod in _ARMS:
            try:
                res = await mod.run_query(q)
                print(
                    f"   Arm {name}: judged={res.n_judged}, ranked={len(res.ranked)}  ✓"
                )
            except Exception as e:
                logging.exception("Arm %s failed on %s", name, q.query_id)
                print(f"   Arm {name}: FAILED ({type(e).__name__}: {e})")
                failures.append((q.query_id, name, f"{type(e).__name__}: {e}"))

    _rule(f"RUN DONE — {len(failures)} arm-query failure(s)")
    for qid, name, err in failures:
        print(f"   FAILED {qid} Arm {name}: {err[:160]}")
    _rule("HEADLINE — collect_results over all persisted results")
    return run_collect()


# Guarded so `import run_experiment` (REPL, tooling) can't start a multi-hour run.
if __name__ == "__main__":
    _t0 = time.monotonic()
    asyncio.run(run_experiment())
    print(f"\n[full run wall-time: {(time.monotonic() - _t0) / 60:.1f} min]")
