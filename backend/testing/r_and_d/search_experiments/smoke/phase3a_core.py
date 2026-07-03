"""Phase 3a smoke test — LIVE Step-0 query analysis + Step-5 ranking blend.

Prints what each stage produces so you can eyeball the shared core's stateless mechanisms
before Phase 3b wires the agentic loop around them. Two live legs:

  1. analyse_query (gpt-5.5 x2) on three queries chosen to exercise each intent branch:
     a plain topic, a "latest X" (recency), and a "seminal X" (centrality).
  2. cohere_rerank (rerank-english-v3.0) over a small hand-built candidate pool, then the
     blended ranking + one §4.7 sweep variant.

Run from the project dir (needs OPENAI + COHERE keys in backend/.env — both set):
    uv run smoke/phase3a_core.py
"""

import asyncio

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from query_analysis import analyse_query
from core.ranking import (
    _default_baseline_year,
    cohere_rerank,
    rank_candidates,
    rerank_sweep,
)
from core.source import Candidate, Capabilities

# Three queries, one per intent branch (ids prefixed so the cache doesn't collide with real runs).
QUERIES = [
    (
        "smoke3a_topic",
        "What is the effect of free school meals on attainment in the UK?",
    ),
    ("smoke3a_recent", "latest evidence on the minimum wage and employment"),
    ("smoke3a_central", "the most seminal evaluations of universal basic income"),
]

# A small pool standing in for a JUDGED candidate set for the minimum-wage/employment query
# (level set as if the frozen judge had already run). Real, recognisable papers from that
# literature, with realistic years/citations so the "recent" intent visibly reorders them:
# the three level-3 papers are content-equal, so recency (weight 0.175) + Cohere + centrality
# decide their order — Card & Krueger (seminal, 1994, heavily cited) should fall behind the
# newer perfects under "latest evidence". Arm C caps so the snippet term is live in the blend.
ARM_C = Capabilities(has_dense=True, has_influential=True, has_snippets=True)
POOL = [
    Candidate(
        paper_id="card_krueger_1994",
        title="Minimum Wages and Employment: A Case Study of the Fast-Food Industry "
        "in New Jersey and Pennsylvania",
        abstract="Comparing fast-food employment across the NJ-PA border after NJ raised its "
        "minimum wage, we find no evidence that the increase reduced employment.",
        level=3,
        num_snippets=4,
        year=1994,
        cited_by_count=6100,
    ),
    Candidate(
        paper_id="cengiz_etal_2019",
        title="The Effect of Minimum Wages on Low-Wage Jobs",
        abstract="Using a bunching estimator across 138 state-level minimum wage increases, "
        "we find the number of low-wage jobs lost is close to zero; employment effects are "
        "concentrated in wages, not job counts.",
        level=3,
        num_snippets=6,
        year=2019,
        cited_by_count=1300,
    ),
    Candidate(
        paper_id="neumark_shirley_2022",
        title="Myth or Measurement: What Does the New Minimum Wage Research Say About "
        "Minimum Wages and Job Loss in the United States?",
        abstract="Reviewing the post-2010 US literature, the preponderance of estimates "
        "points to negative employment effects of minimum wages, especially for less-skilled "
        "workers.",
        level=3,
        num_snippets=5,
        year=2022,
        cited_by_count=240,
    ),
    Candidate(
        paper_id="dube_2019_family_incomes",
        title="Minimum Wages and the Distribution of Family Incomes",
        abstract="Higher minimum wages raise incomes at the bottom of the distribution and "
        "reduce poverty; employment effects are discussed but are not the primary focus.",
        level=1,
        num_snippets=1,
        year=2019,
        cited_by_count=520,
    ),
    Candidate(
        paper_id="oecd_collective_bargaining_2021",
        title="Trade Union Density and Collective Bargaining Coverage Across OECD Countries",
        abstract="Documents long-run declines in union membership and bargaining coverage "
        "across the OECD; does not study minimum wages or their employment effects.",
        level=0,
        num_snippets=0,
        year=2021,
        cited_by_count=70,
    ),
]


async def run_smoke():
    # 1) LIVE query analysis — content + intent + resolved weights ----------------
    rule(
        "1. analyse_query(...)  ->  content (metadata stripped) + intent + Step-5 weights"
    )
    analyses = {}
    for qid, text in QUERIES:
        a = analyse_query(qid, text, force=True)  # force: always show a live call here
        analyses[qid] = a
        w = a.intent.weights()
        print(f"\n   query: {text!r}")
        print(f"     content   : {a.content!r}")
        print(
            f"     intent    : recency={a.intent.recency}  centrality={a.intent.centrality}"
        )
        print(f"     weight_key: {a.intent.weight_key()}")
        print(f"     weights   : w_content={w[0]}  w_recent={w[1]}  w_central={w[2]}")

    # Use the recency query's analysis to rank (so the recency term is actually weighted).
    analysis = analyses["smoke3a_recent"]

    # 2) LIVE Cohere rerank — sets cand.rerank_score (cached) ---------------------
    rule(
        "2. cohere_rerank(...)  ->  rerank_score per candidate (LIVE, cached by query_id)"
    )
    await cohere_rerank("smoke3a_recent", analysis.content, POOL, force=True)
    for c in sorted(POOL, key=lambda c: c.rerank_score, reverse=True):
        print(
            f"   rerank={c.rerank_score:.4f}  L{c.level}  {c.paper_id}  ({c.year}, {c.cited_by_count} cites)"
        )

    # 3) Blended ranking under the live intent ------------------------------------
    baseline = _default_baseline_year(POOL)
    rule(
        f"3. rank_candidates(...)  ->  blended order  (ARM C, baseline_year={baseline})"
    )
    from core.ranking import (
        score,
    )  # local import: only needed to print the per-candidate value

    ranked = rank_candidates(POOL, analysis, ARM_C, baseline_year=baseline)
    for rank, c in enumerate(ranked, 1):
        s = score(c, analysis, ARM_C, baseline)
        print(
            f"   #{rank}  score={s:.4f}  L{c.level}  rerank={c.rerank_score:.3f}  "
            f"snip={c.num_snippets}  {c.paper_id}"
        )

    # 4) One §4.7 sweep variant ---------------------------------------------------
    rule(
        "4. rerank_sweep(...)  ->  variant orderings on the SAME judged pool (pure, no API)"
    )
    sweep = rerank_sweep(POOL, analysis, ARM_C, baseline_year=baseline)
    print(
        f"   produced {len(sweep)} variants (4 weight keys x rerank on/off x snippet on/off)"
    )
    for name in ("recent|rerank=on|snippet=on", "influential|rerank=on|snippet=on"):
        print(f"     {name:34s} -> {sweep[name]}")
    print(
        "   ^ same judged pool, different intent weights -> the TOP swaps: 'recent' puts the"
    )
    print(
        "     newest perfect (neumark 2022) #1; 'influential' puts the most-cited recent one"
    )
    print(
        "     (cengiz, 1300 cites) #1. Note card_krueger stays #3: centrality SATURATES (all"
    )
    print(
        "     three perfects are cited enough to sit ~1.0), so recency is the discriminating"
    )
    print("     axis here, not centrality.")
    return ranked


asyncio.run(run_smoke())
