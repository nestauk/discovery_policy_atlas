"""Phase 2 smoke test — end-to-end retrieve (OpenAlex) -> judge -> levels.

Prints the output of each stage so you can eyeball what the pipeline produces. This is
Arm A in miniature (Phase 6 wraps exactly this path). Run from the project dir:

    uv run smoke/phase2_judge.py
"""

import asyncio

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from app.services.openalex import OpenAlexService
from judge import extract_criteria, judge_papers

QUERY_ID = "smoke01"
QUERY = "What is the effect of free school meals on attainment in the UK?"
SEARCH = "free school meals pupil attainment United Kingdom"


def _rule(title: str) -> None:
    print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)


async def run_smoke(max_results: int = 8):
    # 1) Criteria extraction (gpt-5.5, once per query, cached) ------------------
    _rule("1. extract_criteria(query)  ->  weighted, content-only criteria")
    criteria = extract_criteria(QUERY_ID, QUERY)
    for c in criteria:
        print(f"   [{c.weight:.2f}]  {c.name}\n          {c.description}")
    print(f"   weights sum = {sum(c.weight for c in criteria):.3f}")

    # 2) Retrieval (OpenAlex) — what Arm A will wrap ---------------------------
    _rule(
        f"2. OpenAlexService.search(query, max_results={max_results})  ->  candidates"
    )
    df = await OpenAlexService().search(SEARCH, max_results=max_results)
    print(f"   retrieved {len(df)} candidate papers:")
    for r in df.to_dict("records"):
        title = (r["title"] or "")[:78]
        print(f"     - {title}  ({r['cited_by_count']} cites, {r['publication_year']})")
    papers = [
        {"paper_id": r["id"], "title": r["title"], "abstract": r["abstract"]}
        for r in df.to_dict("records")
    ]

    # 3) Judging (gpt-5.4-mini, batched) ---------------------------------------
    _rule("3. judge_papers(query, papers)  ->  per-paper 0-3 level + score + summary")
    judged = await judge_papers(QUERY_ID, QUERY, papers, criteria=criteria)
    for r in judged.sort_values("level", ascending=False).to_dict("records"):
        pid = r["paper_id"].split("/")[-1]
        print(
            f"   L{r['level']}  score={r['score']:.2f}  codes={r['codes']}  {pid}\n"
            f"        {(r['summary'] or '(not relevant)')[:90]}"
        )

    # 4) What the metric will see ----------------------------------------------
    _rule("4. level distribution  (recall@k_est counts ONLY L3 / Perfect)")
    dist = judged["level"].value_counts().sort_index()
    for level, count in dist.items():
        print(f"   L{level}: {count}")
    n_perfect = int((judged["level"] == 3).sum())
    print(f"\n   Perfect (L3) count = {n_perfect}  -> the numerator recall is built on")
    return judged


asyncio.run(run_smoke())
