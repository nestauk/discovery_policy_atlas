# Search experiments — ASTA-inspired retrieval (Arms A/B/C)

> **New to this project?** Start with [ONBOARDING.md](ONBOARDING.md) — reading path,
> code map, full runbook, credentials checklist, and the sharp edges.

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

`reporting/metrics.py` reimplements the ASTA-bench metric formulas (~100 lines) so we don't pull in
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
uv run smoke/phase3a_core.py      # live — query analysis + Cohere rerank + blend + §4.7 sweep
uv run smoke/phase3b_loop.py      # offline — BTS allocation spotlight + full broad_search loop
uv run smoke/phase4_openalex.py   # live — Arm B client: formulate → search → coverage → suggest/ground → snowball
```

## The frozen judge (Phase 2)

`core/judge.py` is the experiment's measuring instrument (spec §4.5): one frozen judge applied
identically to every arm, so the A→B→C ranking is valid even if the judge is imperfect.

- **Criteria extraction** (gpt-5.5, once/query, cached to `results/judgements/criteria/`):
  ports PF's `_identify_relevance_criteria_prompt_tmpl` — decomposes the free-text question
  into weighted, **content-only** criteria summing to 1. No PICO slots, no study-design
  criteria (relevance = topical bearing, not evidence pedigree).
- **Per-paper judging** (gpt-5.4-mini, batched via `LLMProcessor`, resumable JSONL shard
  per query): ports BENCH's per-criterion judge prompt; scored by
  `reporting.metrics.relevance_criteria_score` → `reporting.metrics.bucket_0_to_3` (the same functions the
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
| `reporting/metrics.py` | ✅ Phase 1 | recall@k_est, corrected nDCG, precision, adjusted F1, k_est inflation. |
| `core/judge.py` | ✅ Phase 2 | Per-query criteria extraction + per-paper judge + parquet cache. |
| `core/source.py` | ✅ Phase 3a | Source-agnostic contract: `Candidate`, `Capabilities`, `SourceClient`, `FakeSource`. |
| `query_analysis.py` | ✅ Phase 3a | Step 0: content extraction + recency/centrality intent (gpt-5.5, cached). |
| `core/ranking.py` | ✅ Phase 3a | Step 5: PF content blend + intent weights + Cohere rerank + §4.7 sweep. |
| `core/adaptive.py` | ✅ Phase 3b | Batched Thompson Sampling judging + `HighlyRelevantShortcircuit` + reward. |
| `core/snowball.py` | ✅ Phase 3b | Edge-sum citation-snowball scoring + top-k promotion (PF-faithful). |
| `core/broad_search.py` | ✅ Phase 3b | The shared source-agnostic loop (Steps 1–5); Arms B/C are thin wrappers. |
| `tests/` | ✅ Phase 1–9 | Offline pytest suites (…/arm_a/fanout/arm_b/arm_c/collect_results). |
| `smoke/` | ✅ Phase 1–8 | Verbose per-phase end-to-end scripts (`phaseN_*.py`). |
| `retrieval/_cache.py` | ✅ Phase 4 | Content-addressed disk cache for retrieval calls (resumable; mandatory for S2). |
| `retrieval/enrich.py` | ✅ Phase 4 | Arm A/B abstract-coverage classification + title-only stat (§4.4 — **measure, no resolver**). |
| `retrieval/suggest.py` | ✅ Phase 4 | Parametric LLM suggestions + source-grounding; title-similarity recorded per match. |
| `retrieval/openalex_client.py` | ✅ Phase 4/7 | `OpenAlexSource` (Arm B): v2 boolean formulation (cached), keyword search w/ SR/RCT fanout, `cites:`/`referenced_works` snowball. |
| `retrieval/_fanout.py` | ✅ Phase 7 | Shared SR/RCT query fanout (base/SR/RCT) used by Arms A + B. |
| `retrieval/s2_client.py`, `dense_s2.py`, `keyword_s2.py` | ✅ Phase 4 | `S2Source` (Arm C): relevance + dense/snippet legs, influential-citation snowball, native abstracts. Per-leg formulation — keyword (`keyword_s2`) vs dense (`dense_s2`), PF's two-agent split. |
| `queries/` | ✅ Phase 5 | 26 stratified curated queries (`queries.jsonl`) + `loader.py`; prod export (`export_search_contexts.py`) → faithful PICO fold (`fold_query.py`) → assembly (`build_queries.py`). |
| `arms/arm_a.py` | ✅ Phase 6 | Arm A baseline — composes prod (multi-query + SR/RCT fanout + OpenAlex search), native order, paper_id dedup, frozen judge. Current-prod multi-query (deviates from §4.2 single-query; see FINDINGS). |
| `arms/arm_b.py` | ✅ Phase 7 | Arm B — `broad_search` loop over `OpenAlexSource` (multi-query+fanout, suggest, snowball, adaptive judge, §4.3 blend+Cohere rank). Production-default citation floor (held constant across A/B/C, 2026-06-26). |
| `arms/arm_c.py` | ✅ Phase 8 | Arm C — `broad_search` loop over `S2Source` (all-True caps light up dense leg + influential snowball + snippet blend). Arm B template + source swap; reuses the source-agnostic loop helpers. |
| `reporting/collect_results.py` | ◑ Phase 9 | Pooled-normalizer metrics engine: recall@k_est + Perfect-found + nDCG + precision + F1 per arm, over the cross-arm pool, aggregated (+ secondary use_case/density cut). **Deferred:** §4.7 reranker sweep (needs candidate-feature persistence), §4.6 padding runs. |
| `run_experiment.py` | ◑ Phase 9 | Experiment-execution driver: all three arms over all 26 queries (per-query interleaved, resilient, cache-warm) → `collect_results`. `PYTHONUNBUFFERED=1 uv run run_experiment.py`. |
| `reporting/cost.py` | ◑ Phase 9 | Per-arm **$ cost** reconstructed from persisted `n_judged` × configurable rates (`PRICES`/`TOKENS`); attributed (standalone) + actual (cache-union) views. `run_cost_report()`. Derived, not measured — works on existing runs, no re-run. |
| `reporting/plots.py` | ◑ Phase 9 | Per-arm distribution plots (strip+box over the cross-arm intersection) for any `collect_results` metric → `results/plots/`. `run_distribution_plots()` / `plot_metric_distribution("recall_at_k_est")`. |
| `smoke/phase9_pilot.py` | ✅ Phase 9 | Small validation pilot (~4 stratified queries) — same flow as `run_experiment` but bounded. |
| `docs/report/findings.md` | ⬜ Phase 10 | Findings report. |
