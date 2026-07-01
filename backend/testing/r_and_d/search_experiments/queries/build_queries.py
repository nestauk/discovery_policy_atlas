"""Phase 5 assembly — select the curated ~26, fold PICO into query_text, write queries.jsonl (§4.1).

Reads the gitignored _candidates.jsonl (the prod export), picks the curated idxs (stratified by
use_case x literature density — approved 2026-06-24), runs the faithful PICO fold on each, and
writes queries/queries.jsonl in the spec schema:
    {query_id, query_text, use_case, literature_density, notes, source_idx, original_search_context}
(query_text/use_case/notes/original_search_context are the §4.1 schema; literature_density is the
stratification axis for §3 stratified-recall; source_idx traces back to the export.)

Prints a review table (original research_question -> folded query_text) so the fold can be eyeballed
before the file is trusted. Folds make live gpt-5.5 calls (cached). Run from the experiment dir:
    uv run queries/build_queries.py
"""

import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402, F401  -- triggers backend/.env bootstrap (OPENAI_API_KEY for get_llm)
from queries.fold_query import fold_query  # noqa: E402

CANDIDATES = _ROOT / "queries" / "_candidates.jsonl"
OUT = _ROOT / "queries" / "queries.jsonl"

# Curated selection (idx, literature_density, notes) — grouped by use_case, rare ones over-sampled.
SELECTED = [
    # policy_blueprint (6 -> 3)
    (6, "medium", ""),
    (101, "dense", ""),
    (77, "sparse", ""),
    # horizon_scan (10 -> 3)
    (46, "dense", ""),
    (97, "medium", ""),
    (109, "sparse", ""),
    # policy_note (8 -> 3)
    (55, "dense", ""),
    (124, "medium", ""),
    (71, "sparse", ""),
    # not_sure (22 -> 4)
    (33, "dense", ""),
    (17, "dense", ""),
    (68, "sparse", ""),
    (128, "sparse", ""),
    # rapid_brief (35 -> 6)
    (12, "dense", ""),
    (105, "dense", ""),
    (136, "medium", ""),
    (90, "medium", ""),
    (48, "sparse", "heat-pump supply-chain cluster representative"),
    (86, "sparse", ""),
    # rapid_evidence_review (63 -> 6)
    (2, "dense", ""),
    (7, "dense", ""),
    (21, "medium", ""),
    (29, "medium", "nature-based wildfire cluster representative"),
    (0, "sparse", ""),
    (39, "medium", "housing-supply cluster representative"),
    # (none) (1 -> 1)
    (5, "dense", ""),
]


def _short(s: str, n: int = 88) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def run_build():
    by_idx = {r["idx"]: r for r in (json.loads(ln) for ln in CANDIDATES.open())}

    records = []
    for i, (idx, density, notes) in enumerate(SELECTED, start=1):
        cand = by_idx[idx]
        rq = cand["research_question"]
        query_text = fold_query(rq, cand["content_pico"])
        records.append(
            {
                "query_id": f"q{i:02d}",
                "query_text": query_text,
                "use_case": cand["use_case"],
                "literature_density": density,
                "notes": notes,
                "source_idx": idx,
                "original_search_context": cand["original_search_context"],
            }
        )

    with OUT.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # --- review table: original research_question -> folded query_text ----------------------- #
    print(f"wrote {len(records)} queries -> {OUT}\n")
    for rec, (idx, density, notes) in zip(records, SELECTED):
        rq = by_idx[idx]["research_question"]
        changed = "FOLD" if rec["query_text"].strip() != rq.strip() else "  = "
        print(
            f"{rec['query_id']}  {(rec['use_case'] or '(none)'):<22} {density:<6} [{changed}]"
        )
        print(f"     rq : {_short(rq)}")
        if changed == "FOLD":
            print(f"     qt : {_short(rec['query_text'])}")


run_build()
