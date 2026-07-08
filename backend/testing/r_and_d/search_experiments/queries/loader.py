"""Load + validate the curated query set (spec §4.1). The arms (Phases 6-8) read queries here.

`queries.jsonl` is the frozen shared artefact: one record per curated query. `query_text` is the
ONLY field fed to arms + judge (the PICO-folded natural-language question); everything else is
analysis metadata — `literature_density` (stratification axis, §3 stratified recall), `use_case`,
`source_idx` (traces back to the prod export), and the full `original_search_context` blob.

REPL usage (no main()/argparse — spec conventions):
    from queries.loader import load_queries
    qs = load_queries()
    qs[0].query_text          # the arm input
    [q.literature_density for q in qs]
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "queries.jsonl"
DENSITIES = {"dense", "medium", "sparse"}

# Dropped from the active set (2026-06-26): over-folded query_text (every PICO facet + the full OECD
# country list) → the v2 generator emits a multi-AND boolean too complex for OpenAlex, which 500s even
# with the citation floor (Arm A failed q01 *with* the floor). queries.jsonl keeps them (provenance) and
# query_ids stay stable for already-persisted results; load_queries just skips them. See FINDINGS.
EXCLUDED_QUERY_IDS = frozenset({"q01", "q23"})


@dataclass
class Query:
    """One curated query. `query_text` is the arm input; the rest is metadata with real consumers.

    Only fields something actually reads are surfaced here. `notes`/`source_idx` live in the jsonl
    (curation provenance) but nothing consumes them, so they're not modelled — read the raw file if
    ever needed.
    """

    query_id: str  # arms key results/caches on this
    query_text: str  # the ONLY field fed to arms + judge (PICO-folded NL question)
    use_case: (
        str | None
    )  # stratification axis (may be None — one project never set one)
    literature_density: str  # stratification axis (§3 stratified recall)
    original_search_context: (
        dict  # §4.2 sensitivity run + §4.7 PICO/evidence-mix analysis
    )


def load_queries(path: Path | str = DEFAULT_PATH) -> list[Query]:
    """Parse queries.jsonl into validated `Query` objects (raises on a malformed/duplicate record)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"query set not found: {path} (run queries/build_queries.py)"
        )

    queries: list[Query] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.open(), start=1):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        try:
            q = Query(
                query_id=rec["query_id"],
                query_text=rec["query_text"],
                use_case=rec.get("use_case"),
                literature_density=rec["literature_density"],
                original_search_context=rec["original_search_context"],
            )
        except KeyError as e:
            raise ValueError(f"{path}:{lineno} missing required field {e}") from e

        if not q.query_id or q.query_id in seen:
            raise ValueError(
                f"{path}:{lineno} missing or duplicate query_id {q.query_id!r}"
            )
        if not q.query_text.strip():
            raise ValueError(f"{path}:{lineno} empty query_text for {q.query_id}")
        if q.query_id in EXCLUDED_QUERY_IDS:
            seen.add(q.query_id)  # still flag duplicates of an excluded id
            continue
        if q.literature_density not in DENSITIES:
            raise ValueError(
                f"{path}:{lineno} bad literature_density {q.literature_density!r} "
                f"for {q.query_id} (expected one of {sorted(DENSITIES)})"
            )
        seen.add(q.query_id)
        queries.append(q)
    return queries
