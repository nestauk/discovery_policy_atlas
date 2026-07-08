"""Phase 4 smoke — the Semantic Scholar source client (Arm C), LIVE end-to-end (real S2 + LLM).

Walks every SourceClient leg `broad_search` will call, printing what each produces. The point of
this script over the Arm B one (phase4_openalex.py) is the two legs OpenAlex structurally CANNOT
do — it exercises them live so you can eyeball that S2's extra capabilities are real:

  - box 3  dense_search  — the §4.3 #1 dense/snippet leg: /snippet/search (sparse) → /paper/batch
    (hydrate). Prints num_snippets (dense-match strength) and the text_basis split, incl. the
    'snippet' fallback for papers batch couldn't fill.
  - box 5  fetch_citations — the §4.3 #2 forward-influence signal: each citing edge's isInfluential
    flag lands on Candidate.is_influential (OpenAlex has no equivalent).

Boxes 1/2/4 mirror Arm B (dense NL formulation, native-abstract keyword search, parametric
suggestion grounding) so the A→B→C ladder reads side by side.

Everything is cached (results/retrieval/) AND throttled to S2's cumulative 1 req/s, so a COLD run
is genuinely slow (the §7 cost finding); a second run is fast and free. Bounded small (2
formulations, limit 25/50, 5 suggestions, 1 snowball seed) to stay cheap. Needs
SEMANTIC_SCHOLAR_API_KEY in backend/.env. Run from the project dir:
    uv run smoke/phase4_s2.py
"""

import asyncio
from collections import Counter

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from retrieval import _cache
from retrieval.enrich import classify_text_basis
from retrieval.s2_client import S2Source
from core.snowball import build_edges, promote_snowball

CONTENT = "effect of free school meals on educational attainment in the UK"


def _short(title: str | None, n: int = 70) -> str:
    t = title or "(no title)"
    return t if len(t) <= n else t[: n - 1] + "…"


def _basis_split(cands) -> str:
    """Compact text_basis distribution, e.g. 'abstract=40 tldr=7 snippet=3'."""
    counts = Counter(c.text_basis or "title_only" for c in cands)
    return " ".join(f"{k}={v}" for k, v in counts.most_common())


async def run_smoke():
    src = S2Source()
    print(
        f"   S2Source caps = {src.caps}"
    )  # all-True (Arm C) — the fully-capable source

    try:
        # ===== 1. FORMULATION — TWO legs, TWO idioms (PF's two-agent split) ==== #
        rule("1. formulate — keyword leg (keyword_s2) vs dense leg (dense_s2), §4.3a")
        print(f"   content = {CONTENT!r}\n")
        kw_queries = await src.formulate_keyword_queries(CONTENT, 2)
        dense_queries = await src.formulate_dense_queries(CONTENT, 2)
        print("   KEYWORD queries (-> /paper/search; short, content-keywords):")
        for i, q in enumerate(kw_queries):
            print(f"     kw {i}: {_short(q, 120)}")
        print("   DENSE queries (-> /snippet/search; verbose natural language):")
        for i, q in enumerate(dense_queries):
            print(f"     dn {i}: {_short(q, 120)}")
        print(
            "   ^ the fix (FINDINGS 2026-06-23): keyword leg no longer gets the dense sentence that"
            " returned 0."
        )

        # ===== 2. KEYWORD SEARCH + abstract coverage (native abstracts) ======= #
        rule("2. keyword_search (limit 25) — keyword query -> /paper/search (§4.3 #4)")
        cands = await src.keyword_search(kw_queries[0], 25)
        print(
            f"   retrieved {len(cands)} candidates for kw query 0 (was 0 on a dense query)"
        )
        stats = classify_text_basis(cands)
        print(
            f"   coverage: {stats.n_abstract} with abstract, {stats.n_title_only} title-only "
            f"({100 * stats.title_only_fraction:.1f}%)  [§4.4 trigger bar: >15%]"
        )
        print(f"   text_basis split: {_basis_split(cands) or '(none)'}")
        for c in cands[:4]:
            print(
                f"     - [{(c.text_basis or 'title_only'):10s}] {c.year} cites={c.cited_by_count:<5} {_short(c.title)}"
            )

        # ===== 3. DENSE SEARCH — §4.3 #1 leg OpenAlex lacks (sparse -> hydrate) = #
        rule(
            "3. dense_search (limit 50) — /snippet/search -> /paper/batch; num_snippets (§4.3 #1)"
        )
        dense = await src.dense_search(dense_queries[0], 50)
        print(f"   retrieved {len(dense)} dense candidates (deduped by corpusId)")
        print(
            f"   text_basis split: {_basis_split(dense)}   <-- 'snippet' = batch couldn't hydrate"
        )
        for c in sorted(dense, key=lambda x: x.num_snippets, reverse=True)[:4]:
            print(
                f"     - n_snippets={c.num_snippets:<3} [{(c.text_basis or 'title_only'):8s}] "
                f"cites={c.cited_by_count:<5} {_short(c.title)}"
            )

        # ===== 4. PARAMETRIC SUGGESTIONS + GROUNDING (similarity recorded) ===== #
        rule("4. suggest -> ground against S2 (title ±2yr); title-similarity per match")
        grounded = await src.suggest(CONTENT, 5)
        print(f"   grounded {len(grounded)} of 5 LLM-named papers\n")
        records = _cache.load("suggest.groundings", {"content": CONTENT}) or []
        print(f"   {'sim':>5}  named -> matched")
        for r in records:
            flag = "" if r["similarity"] >= 0.85 else "   <-- LOW"
            print(f"   {r['similarity']:5.3f}  {_short(r['suggested_title'], 40)}")
            print(f"          -> {_short(r['matched_title'], 60)}{flag}")
        print("   ^ trust S2's top fuzzy title hit; similarity is recorded, not gated.")

        # ===== 5. SNOWBALL — forward w/ isInfluential (§4.3 #2) + backward ===== #
        rule(
            "5. snowball — fetch_citations (isInfluential flag, §4.3 #2) + fetch_references"
        )
        # Prefer a keyword hit; fall back to the dense pool (Arm C's primary leg) so the box
        # still runs when /paper/search came back empty on the dense query (the box-2 finding).
        seed = next((c for c in cands if c.paper_id), None) or next(
            (c for c in dense if c.paper_id), None
        )
        seed.level = 3  # pretend the judge rated it Perfect -> seed_relevance 3.0
        leg = "keyword" if seed in cands else "dense"
        print(
            f"   seed (judged L3, from {leg} leg): {_short(seed.title)}  [corpusId {seed.paper_id}]"
        )

        citing = await src.fetch_citations(seed.paper_id)
        refs = await src.fetch_references(seed.paper_id)
        n_infl = sum(c.is_influential for c in citing)
        print(
            f"   forward (citing the seed): {len(citing)} ({n_infl} flagged influential)   "
            f"backward (references): {len(refs)}"
        )

        fwd = promote_snowball(build_edges(seed, citing), "forward", src.caps)
        bwd = promote_snowball(build_edges(seed, refs), "backward", src.caps)
        print(f"   promoted: {len(fwd)} forward, {len(bwd)} backward (top-k each)")
        for c in fwd[:2]:
            star = " ★infl" if c.is_influential else ""
            print(
                f"     fwd: score={c.seed_relevance:+.4f}  {c.year}  {_short(c.title)}{star}"
            )
        for c in bwd[:2]:
            print(
                f"     bwd: score={c.seed_relevance:+.4f}  {c.year}  {_short(c.title)}"
            )

        rule(
            "DONE — every Arm-C leg exercised live (dense + influential are the B↔C divergence). "
            "Cached + throttled @1 req/s under results/retrieval/."
        )
        return kw_queries, dense_queries, cands, dense, grounded, fwd, bwd
    finally:
        await src.aclose()  # close the httpx client (S2-specific; OpenAlex used PyAlex)


asyncio.run(run_smoke())
