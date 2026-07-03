"""Phase 4 smoke — the OpenAlex source client (Arm B), LIVE end-to-end (real OpenAlex + LLM).

Walks every SourceClient leg `broad_search` will call, printing what each produces, so you can
eyeball that the v2 boolean formulation, keyword retrieval, abstract coverage, parametric
suggestion GROUNDING (with title-similarity per match — the thing to verify), and the
citation-graph snowball legs all behave on a real policy query. Everything is cached
(results/retrieval/), so a second run is fast and free.

Bounded small (2 formulations, limit 25, 5 suggestions, 1 snowball seed) to stay cheap and
under OpenAlex's polite-pool rate. Run from the project dir:
    uv run smoke/phase4_openalex.py
"""

import asyncio

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from retrieval import _cache
from retrieval.enrich import classify_text_basis
from retrieval.openalex_client import OpenAlexSource
from core.snowball import build_edges, promote_snowball

CONTENT = "effect of free school meals on educational attainment in the UK"


def _short(title: str | None, n: int = 70) -> str:
    t = title or "(no title)"
    return t if len(t) <= n else t[: n - 1] + "…"


async def run_smoke():
    src = OpenAlexSource()
    src.caps  # all-False (Arm B) — printed for the record
    print(f"   OpenAlexSource caps = {src.caps}")

    # ===== 1. FORMULATION — v2 boolean generator (same as Arm A) =========== #
    rule(
        "1. formulate_keyword_queries — v2 production boolean generator (§4.3 query-formulation)"
    )
    print(f"   content = {CONTENT!r}\n")
    queries = await src.formulate_keyword_queries(CONTENT, 2)
    for i, q in enumerate(queries):
        print(f"   query {i}: {_short(q, 140)}")

    # ===== 2. KEYWORD SEARCH + abstract coverage =========================== #
    rule("2. keyword_search (limit 25) + abstract-coverage classification (§4.4)")
    cands = await src.keyword_search(queries[0], 25)
    print(f"   retrieved {len(cands)} candidates for query 0")
    stats = classify_text_basis(cands)
    print(
        f"   coverage: {stats.n_abstract} with abstract, {stats.n_title_only} title-only "
        f"({100 * stats.title_only_fraction:.1f}%)  [§4.4 trigger bar: >15%]"
    )
    for c in cands[:4]:
        print(
            f"     - [{c.text_basis:10s}] {c.year} cites={c.cited_by_count:<5} {_short(c.title)}"
        )

    # ===== 3. PARAMETRIC SUGGESTIONS + GROUNDING (similarity recorded) ===== #
    rule(
        "3. suggest -> ground against OpenAlex (title ±2yr); title-similarity per match"
    )
    grounded = await src.suggest(CONTENT, 5)
    print(f"   grounded {len(grounded)} of 5 LLM-named papers\n")
    records = _cache.load("suggest.groundings", {"content": CONTENT}) or []
    print(f"   {'sim':>5}  named -> matched")
    for r in records:
        flag = "" if r["similarity"] >= 0.85 else "   <-- LOW"
        print(f"   {r['similarity']:5.3f}  {_short(r['suggested_title'], 40)}")
        print(f"          -> {_short(r['matched_title'], 60)}{flag}")
    print(
        "   ^ trust OpenAlex's top fuzzy title hit; similarity is recorded, not gated."
    )

    # ===== 4. SNOWBALL fetch legs (forward cites: + backward referenced_works) #
    rule(
        "4. snowball — fetch_citations (cites:) + fetch_references, then promote (§4.3 Step 3)"
    )
    seed = next((c for c in cands if c.paper_id), None)
    # pretend the judge rated it Perfect, so seed_relevance = 3.0 (raw level, not /3)
    seed.level = 3
    print(f"   seed (judged L3): {_short(seed.title)}  [{seed.paper_id}]")

    citing = await src.fetch_citations(seed.paper_id)
    refs = await src.fetch_references(seed.paper_id)
    print(
        f"   forward (citing the seed): {len(citing)}   backward (seed's references): {len(refs)}"
    )

    fwd = promote_snowball(build_edges(seed, citing), "forward", src.caps)
    bwd = promote_snowball(build_edges(seed, refs), "backward", src.caps)
    print(f"   promoted: {len(fwd)} forward, {len(bwd)} backward (top-k each)")
    for label, group in (("fwd", fwd), ("bwd", bwd)):
        for c in group[:2]:
            print(
                f"     {label}: score={c.seed_relevance:+.4f}  {c.year}  {_short(c.title)}"
            )

    rule(
        "DONE — every Arm-B SourceClient leg exercised live (all cached under results/retrieval/)"
    )
    return queries, cands, grounded, fwd, bwd


asyncio.run(run_smoke())
