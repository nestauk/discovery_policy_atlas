"""Phase 9 PILOT — run all three arms over a few stratified queries, then print the headline.

A cheap, directional end-to-end of the A→B→C ladder: pick ~4 queries spanning density, run each
through Arm A / B / C (persisting results/arms/{arm}/{qid}.json), then collect_results over what
landed. Validates the full pipeline + gives preliminary signal BEFORE the full 26-query spend.

This is LIVE and not free: OpenAI (formulation/judge) + OpenAlex + S2 (Arm C, throttled 1 req/s, so
the slow part) + Cohere. Budget ~20–40 min cold; cached + resumable, so a rerun is fast. Each
arm-query is wrapped so one failure doesn't sink the run. Run from the experiment dir:
    uv run smoke/phase9_pilot.py

NOTE this is a PILOT: n=4 (noisy, directional) and the normalizer is arms-only (no §4.6 padding →
absolute recall reads optimistically high; the A/B/C *ordering* is the robust signal).
"""

import asyncio
import logging

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from arms import arm_a, arm_b, arm_c
from reporting.collect_results import run_collect
from queries.loader import load_queries

# 4 queries spanning literature density (dense → sparse). Edit freely.
PILOT_QIDS = ["q11", "q05", "q12", "q19"]
_ARMS = [("A", arm_a), ("B", arm_b), ("C", arm_c)]


async def run_pilot():
    by_id = {q.query_id: q for q in load_queries()}
    for qid in PILOT_QIDS:
        q = by_id[qid]
        rule(f"PILOT {qid} — use_case={q.use_case}, density={q.literature_density}")
        print(f"   {q.query_text[:110]}")
        for name, mod in _ARMS:
            try:
                res = await mod.run_query(
                    q
                )  # persists results/arms/arm_{a,b,c}/{qid}.json
                print(
                    f"   Arm {name}: judged={res.n_judged}, ranked={len(res.ranked)}  ✓"
                )
            except Exception as e:  # keep the pilot going if one arm-query fails
                logging.exception("Arm %s failed on %s", name, qid)
                print(f"   Arm {name}: FAILED ({type(e).__name__}: {e})")

    rule("PILOT HEADLINE — collect_results over the persisted pilot queries")
    return run_collect()


asyncio.run(run_pilot())
