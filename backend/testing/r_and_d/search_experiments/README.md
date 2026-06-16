# Search experiments — ASTA-inspired retrieval (Arms A/B/C)

Research code for the retrieval experiment in
[`docs/specs/spec_retrieval_experiment_openalex.md`](../../../../docs/specs/spec_retrieval_experiment_openalex.md).
**Not shipped** — this lives under `backend/testing/r_and_d/` alongside the other
research experiments (`evidence_categorisation`, `boolean_queries`) and is never imported
by the deployable app.

## What this is

A three-way comparison (the **A→B→C ladder**) of retrieval pipelines on real Policy Atlas
queries, scored by a single frozen relevance judge:

- **Arm A** — v2 baseline: one boolean query → OpenAlex → done (thin wrapper over `backend`).
- **Arm B** — full Paper Finder machinery (adaptive judging, snowball, reformulation,
  Cohere rerank) on **OpenAlex**.
- **Arm C** — the *same* machinery on **Semantic Scholar** (+ dense/snippet leg,
  influential-citation signal, native abstracts).

A→B isolates the agentic machinery (corpus held fixed); B→C isolates the source.

Mechanisms are ported from **PF** (`asta-paper-finder`); metric/scoring definitions from
**BENCH** (`asta-bench`). See the spec §3 for exact source files.

## Setup

This is a self-contained `uv` project (unlike its `r_and_d` siblings, which share the
backend env) because it needs extra deps — `cohere`, `httpx`, `pyarrow`. The `backend`
package is an editable path dependency at `../../..`, so the v2 baseline, `OpenAlexService`,
and the LLM helpers are importable directly.

```bash
cd backend/testing/r_and_d/search_experiments
uv sync
```

## Run the parity tests (Phase 1 deliverable)

`metrics.py` reimplements the ASTA-bench metric formulas (~100 lines) so we don't pull in
`inspect-ai` + a HuggingFace dataset download. `tests/test_metrics.py` pins parity against
hand-computed values taken from the BENCH source:

```bash
uv run pytest tests/test_metrics.py -v
```

Expect **33 passed**. The tests assert, among others, the k_est inflation worked examples
(1→10, 2→6, 3→6, 5→10, 10→20, 100→200), `find_dcg`'s natural-log discount, corrected-nDCG
bounds (sorted-desc → 1.0, sorted-asc → 0.0, all-equal → 0.0), and the 0–3 bucketing
boundaries.

`tests/test_judge.py` (Phase 2) covers the judge's pure logic offline — dynamic
output-field construction, weight normalisation, per-row scoring (cross-checked against
`metrics.py`), and parquet-cache consolidation:

```bash
uv run pytest -q          # both suites: 43 passed
```

## Smoke tests (one per phase)

`tests/` asserts pure logic offline; `smoke/` *runs the real pipeline* (live LLM/API calls)
and **prints what each stage produces**. One script per phase — see `smoke/README.md`:

```bash
uv run smoke/phase1_metrics.py    # offline — metric worked examples
uv run smoke/phase2_judge.py      # live — OpenAlex retrieve -> judge -> 0-3 levels
```

## The frozen judge (Phase 2)

`judge.py` is the experiment's measuring instrument (spec §4.5): one frozen judge applied
identically to every arm, so the A→B→C ranking is valid even if the judge is imperfect.

- **Criteria extraction** (gpt-5.5, once/query, cached to `results/judgements/criteria/`):
  ports PF's `_identify_relevance_criteria_prompt_tmpl` — decomposes the free-text question
  into weighted, **content-only** criteria summing to 1. No PICO slots, no study-design
  criteria (relevance = topical bearing, not evidence pedigree).
- **Per-paper judging** (gpt-5.4-mini, batched via `LLMProcessor`, resumable JSONL shard
  per query): ports BENCH's per-criterion judge prompt; scored by
  `metrics.relevance_criteria_score` → `metrics.bucket_0_to_3` (the same functions the
  recall metric is built on).
- **Cache** keyed by `(query_id, paper_id)` → `results/judgements/judgements.parquet`. A
  paper pooled across arms + normalizer runs is judged exactly once; the companion judge
  spec reuses this cache.
- The prompts carry a light **policy-research domain framing** (persona + context) for
  construct validity, but deliberately avoid v2's PICO/evidence-type/hard-geography logic.

The live end-to-end demonstration of the judge (criteria → retrieve → judge → levels) is
`smoke/phase2_judge.py` above.

## Conventions

- **REPL-first.** Modules expose objects + `run_xxx()` helpers — no `main()`, no `argparse`,
  no `if __name__` blocks. Matches `backend/testing/r_and_d/evidence_categorisation/`.
- **Frozen config.** Every shared knob (models, budgets, blend weights, thresholds) lives in
  `config.py` as one frozen dataclass — the A→B→C ladder relies on arms differing only in the
  axis under test.
- **Everything cached to disk** (parquet) so reruns are cheap and the experiment is resumable.
  The `judgements/` cache and `queries/queries.jsonl` are shared artefacts the companion
  judge spec builds on.

## Layout (built incrementally over 10 phases — see spec §5)

| File | Status | Purpose |
|---|---|---|
| `config.py` | ✅ Phase 1 | Frozen models, budgets, blend weights, judge thresholds, inflation. |
| `metrics.py` | ✅ Phase 1 | recall@k_est, corrected nDCG, precision, adjusted F1, k_est inflation. |
| `judge.py` | ✅ Phase 2 | Per-query criteria extraction + per-paper judge + parquet cache. |
| `tests/` | ✅ Phase 1–2 | Offline pytest suites (`test_metrics.py`, `test_judge.py`). |
| `smoke/` | ✅ Phase 1–2 | Verbose per-phase end-to-end scripts (`phaseN_*.py`). |
| `query_analysis.py`, `adaptive.py`, `snowball.py`, `ranking.py` | ⬜ Phase 3 | Shared source-agnostic agentic core. |
| `retrieval/` | ⬜ Phase 4 | OpenAlex + S2 + dense + enrich + suggest clients. |
| `queries/queries.jsonl` | ⬜ Phase 5 | ~25 stratified curated queries. |
| `arms/` | ⬜ Phases 6–8 | Arm A baseline, Arm B (OpenAlex), Arm C (S2). |
| `collect_results.py` | ⬜ Phase 9 | Three-way metrics + reranker sweep. |
| `report/findings.md` | ⬜ Phase 10 | Findings report. |
