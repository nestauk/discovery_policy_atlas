"""Phase 6 smoke — Arm A (production v2 baseline), LIVE end-to-end (real boolean gen + OpenAlex + judge).

Walks one curated query through Arm A so you can eyeball the production-composed pipeline: the
multi-query booleans, the SR/RCT fanout, native-ordered retrieval (relevance_score + variant), abstract
coverage (§4.4), and the frozen judge. To stay cheap this judges only a TOP SLICE (the real run,
arms.arm_a.run_all, judges the top-250 per query). Everything LLM/OpenAlex is cached. Run from project dir:
    uv run smoke/phase6_arm_a.py
"""

import asyncio
from collections import Counter

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from arms.arm_a import ArmA
from queries.loader import load_queries
from retrieval.enrich import classify_text_basis

QUERY_ID = "q11"  # venous leg ulcer — rich PICO, folded into query_text
JUDGE_SAMPLE = (
    15
)  # smoke only; arms.arm_a.run_query judges top CONFIG.budgets.judge_quota (250)


def _short(t: str | None, n: int = 72) -> str:
    t = (t or "(no title)").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


async def run_smoke():
    q = next(x for x in load_queries() if x.query_id == QUERY_ID)
    arm = ArmA()

    # ===== 1. FORMULATION — current-prod multi-query (cached) ============== #
    rule(
        "1. formulate_queries — current-prod MULTI-query booleans (cached), §4.2 baseline"
    )
    print(
        f"   query_id = {q.query_id}   use_case = {q.use_case}   density = {q.literature_density}"
    )
    print(f"   query_text = {_short(q.query_text, 100)!r}\n")
    retr = await arm.retrieve(q.query_text)
    print(
        f"   generated {len(retr.booleans)} boolean queries; fanout_enabled = {arm._fanout_enabled}"
    )
    for i, b in enumerate(retr.booleans):
        print(f"     bool {i}: {_short(b, 100)}")

    # ===== 2. RETRIEVAL — fanout + native order (relevance_score + variant) = #
    rule("2. retrieve — SR/RCT fanout, OpenAlex search, dedupe(paper_id) + native sort")
    cands = retr.candidates
    stats = classify_text_basis(
        cands
    )  # sets text_basis in place (abstract vs title_only, §4.4)
    print(f"   retrieved {len(cands)} candidates (deduped, production-ordered)")
    print(
        f"   abstract coverage: {stats.n_abstract} abstract, {stats.n_title_only} title-only "
        f"({100 * stats.title_only_fraction:.1f}%)  [§4.4 bar: >15%]"
    )
    for c in cands[:5]:
        print(
            f"     - [{(c.text_basis or 'title_only'):10s}] {c.year} cites={c.cited_by_count:<5} {_short(c.title)}"
        )

    # ===== 3. JUDGE — frozen experiment judge (top slice for the smoke) ===== #
    rule(
        f"3. judge — frozen criteria-based judge on top {JUDGE_SAMPLE} (real run: top-250)"
    )
    from core.judge import get_cached_levels, judge_papers

    sample = cands[:JUDGE_SAMPLE]
    papers = [
        {
            "paper_id": c.paper_id,
            "title": c.title,
            "abstract": c.abstract,
            "text_basis": c.text_basis,
        }
        for c in sample
    ]
    await judge_papers(q.query_id, q.query_text, papers)
    levels = get_cached_levels(q.query_id)

    dist = Counter(levels.get(c.paper_id) for c in sample)
    label = {
        3: "Perfect",
        2: "Highly",
        1: "Somewhat",
        0: "Irrelevant",
        None: "unjudged",
    }
    print(
        f"   judged {sum(c.paper_id in levels for c in sample)}/{len(sample)}; level distribution:"
    )
    for lvl in (3, 2, 1, 0, None):
        if dist.get(lvl):
            print(f"     {label[lvl]:<10} {dist[lvl]}")
    print("   top of ranking with levels:")
    for c in sample[:5]:
        print(f"     L{levels.get(c.paper_id)}  {_short(c.title)}")

    rule(
        "DONE — Arm A baseline exercised live (compose prod: boolean→fanout→search→judge). Cached."
    )
    return retr, levels


asyncio.run(run_smoke())
