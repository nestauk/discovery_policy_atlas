"""Phase 5 export — pull the candidate query pool from prod (spec §4.1), for curation.

Reads `analysis_projects.search_query` (JSONB) from Supabase, excludes internal-team projects, and
writes every candidate to the gitignored `_candidates.jsonl` next to this file. `created_by_name`
is used ONLY for the internal-team exclusion and is NEVER written out (the only field the user
flagged as sensitive; research questions themselves are fine to keep).

Per candidate we store: the research_question (the arm input before PICO-folding), semantic_query,
use_case, the CONTENT-PICO fields (geography/population/outcome/inner_setting/implementation_
constraints — the bits we will fold into query_text, §4.1), the time fields (metadata → recency
intent, NOT folded into text), and the full original search_query blob as original_search_context.

Network note: the agent sandbox blocks outbound connections, so RUN THIS FROM YOUR OWN SHELL:
    uv run --directory /…/backend python …/search_experiments/queries/export_search_contexts.py
The JSONL lands on disk; the curation steps then read it locally (no network).
"""

import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

_REPO = Path("/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas")
load_dotenv(_REPO / "backend" / ".env")

EXCLUDED_USERS = {"Aidan Kelly", "Karlis Kanders", "Genna Barnett"}
USE_CASE_DEPLOY_DATE = "2026-04-15T00:00:00"
OUT_PATH = Path(__file__).resolve().parent / "_candidates.jsonl"

# Fields whose content describes the information need → folded into query_text later (§4.1).
CONTENT_PICO = (
    "geography",
    "population",
    "outcome",
    "inner_setting",
    "implementation_constraints",
)
# Retained as metadata only (recency intent / config) — NOT folded into the NL query.
TIME_FIELDS = ("time_from", "time_to", "time_preset")


def _nonempty(v) -> bool:
    """A PICO field 'has content' if it's a non-empty list/str and not the 'All'/None placeholder."""
    if v in (None, "", [], ["All"], "None"):
        return False
    return True


def run_export():
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    resp = (
        client.table("analysis_projects")
        .select("search_query, created_at, created_by_name")
        .not_.is_("search_query", "null")
        .gte("created_at", USE_CASE_DEPLOY_DATE)
        .execute()
    )
    rows = resp.data or []
    kept = [
        r for r in rows if r.get("created_by_name") not in EXCLUDED_USERS
    ]  # name used here only

    records = []
    for i, r in enumerate(kept):
        sq = r.get("search_query")
        if not isinstance(sq, dict):
            continue
        records.append(
            {
                "idx": i,
                "use_case": sq.get("use_case"),
                "research_question": (sq.get("research_question") or "").strip(),
                "semantic_query": (sq.get("semantic_query") or "").strip(),
                "content_pico": {k: sq.get(k) for k in CONTENT_PICO},
                "time": {k: sq.get(k) for k in TIME_FIELDS},
                "original_search_context": sq,  # full blob (no created_by_name — separate column)
            }
        )

    with OUT_PATH.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # --- summary to terminal (no raw names; safe to paste back) ------------------------------ #
    use_cases = Counter(rec["use_case"] or "(none)" for rec in records)
    rq_lens = [len(rec["research_question"]) for rec in records]
    terse = sum(
        n < 60 for n in rq_lens
    )  # very short questions most likely to need PICO folding
    pico_rich = sum(
        any(_nonempty(rec["content_pico"][k]) for k in CONTENT_PICO) for rec in records
    )
    empty_rq = sum(n == 0 for n in rq_lens)

    print(f"wrote {len(records)} candidates -> {OUT_PATH}")
    print("\nuse_case distribution:")
    for uc, n in use_cases.most_common():
        print(f"   {uc:<24} {n}")
    print(
        f"\nresearch_question length: min={min(rq_lens)} median={sorted(rq_lens)[len(rq_lens)//2]} max={max(rq_lens)}"
    )
    print(f"   empty research_question : {empty_rq}")
    print(
        f"   terse (<60 chars)       : {terse}  (most likely to benefit from PICO folding)"
    )
    print(f"   has content-PICO to fold: {pico_rich} / {len(records)}")


# Guarded so importing this module can't hit Supabase.
if __name__ == "__main__":
    run_export()
