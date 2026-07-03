# Onboarding — search experiments (ASTA-inspired retrieval, Arms A/B/C)

Who this is for: a Policy Atlas data scientist taking ownership of the retrieval
experiment. It assumes you know the product and the v2 search flow, but nothing about
this experiment, PaperFinder, or asta-bench.

How to use this doc: read §1–§3 before the onboarding session; use §4 (runbook) to do
your first full solo run afterwards; keep §5–§6 as reference. Everything else in the
repo is indexed with a status label in §6 so you know what's canon and what's history.

> Maintainer contact: Aidan Kelly.

---

## 1. What this is, in 30 seconds

A three-way comparison (the **A→B→C ladder**) of retrieval pipelines over real Policy
Atlas queries, scored by a single frozen LLM relevance judge:

- **Arm A** — the production v2 baseline: one boolean query → OpenAlex → done.
- **Arm B** — PaperFinder's agentic machinery (iterative reformulation, adaptive
  judging, citation snowball, Cohere rerank) kept on **OpenAlex**.
- **Arm C** — the *same* machinery on **Semantic Scholar** (dense/snippet leg,
  influential-citation signal, native abstracts).

A→B isolates the *machinery* (corpus held fixed); B→C isolates the *source*. The
mechanisms are faithful ports from PaperFinder; the metrics are reimplementations of
asta-bench's formulas with parity tests pinning them to the originals.

Headline results and their interpretation: [`docs/FINDINGS.md`](docs/FINDINGS.md).
The likely next step for the project is productionising one arm (probably B) — that
design is deliberately **not** prescribed here; it's yours to make once you understand
the ladder.

## 2. Annotated reading list

Read in this order. Each item says what it informed here, so you can read with a target.

| # | Read | What it informed here |
|---|------|----------------------|
| 1 | [`README.md`](README.md) | The experiment's own summary: the ladder, setup, phase log. Read first. |
| 2 | **PaperFinder blog & repo** (Ai2): https://allenai.org/blog/paper-finder & https://github.com/allenai/asta-paper-finder  | Arm B/C's machinery wholesale: the broad-search loop, batched Thompson-sampling adaptive judging, citation snowball, content blend + rerank. Our "diligent, 2 iterations" operating point is their diligent mode minus one iteration. |
| 3 | **asta-bench paper & repo** (Ai2): https://arxiv.org/abs/2510.21652 & https://github.com/allenai/asta-bench | The evaluation frame: judged pools, recall@k_est with the pooled-normalizer inflation factor, corrected nDCG, 0–3 relevance bucketing. `reporting/metrics.py` reimplements these (~100 lines); `tests/test_metrics.py` pins parity with hand-computed values from the BENCH source. |
| 4 | PF repo (`asta-paper-finder`), targeted modules | Only these, as reference for the ports: `relevance_loading_optimization.py` (→ `core/adaptive.py`), `snowball_agent.py` (→ `core/snowball.py`), `common/sorting.py` + `external_api/rerank/cohere.py` (→ `core/ranking.py`), `broad_search.py` (→ `core/broad_search.py`). [`docs/CODE_REUSE_RATIONALE.md`](docs/CODE_REUSE_RATIONALE.md) is the port-by-port map. |
| 5 | BENCH repo (`asta-bench`), targeted modules | `relevance.py` (bucketing, rj_4l codes) and `paper_finder_utils.py` (inflation factor) — read side-by-side with `reporting/metrics.py` and its parity tests. |
| 6 | [`docs/FINDINGS.md`](docs/FINDINGS.md) | The results themselves, plus some findings whilst writing and running the code (§6 some sharp edges which summarises the ones that will bite you). |
| 7 | Experiment spec — [`docs/specs/spec_retrieval_experiment_openalex.md`](../../../../docs/specs/spec_retrieval_experiment_openalex.md) | The design record (§ numbering used throughout code comments), this was the original document spec for doing this experiment. NB its "repo layout" section is the *plan*, superseded by the actual layout in §3 below. |

Deliberately deferred: the PF paper's fast-mode config and the 3-iteration diligent
default become relevant if you pick up the planned sweeps (§7).

## 3. Map of the code

Two kinds of files: **RUN** (entry points — execute them) and **LIB** (read/import them).
All entry points are `__main__`-guarded: importing them is always safe; only
`uv run …` executes.

| Path | Kind | What it is |
|------|------|-----------|
| `run_experiment.py` | RUN | The full experiment: every query × all three arms → persists `results/arms/`. Hours. I think this can be optimised (and will need to be for production). |
| `run_latency.py` | RUN | Cold-cache latency probe over a small subset (redirects caches to a temp dir; doesn't touch real results). |
| `query_analysis.py` | LIB | Per-query descriptive stats helpers (REPL). |
| `config.py` | LIB | **The frozen experiment config** — one dataclass, every shared knob, heavily annotated. Also bootstraps `backend/.env` on import; imported first by everything. |
| `core/` | LIB | The machinery: `broad_search.py` (the shared loop, Steps 1–5), `adaptive.py` (batched Thompson sampling + short-circuit), `judge.py` (frozen judge + shared parquet cache), `snowball.py` (citation snowball scoring), `ranking.py` (content blend + Cohere rerank), `source.py` (the `SourceClient` protocol seam that lets B and C share one loop). |
| `arms/` | LIB | `arm_a.py` / `arm_b.py` / `arm_c.py` — thin per-arm wrappers; A wraps the prod v2 path, B/C configure `core/broad_search.py`. |
| `retrieval/` | LIB | Source clients: `openalex_client.py`, `s2_client.py`, dense/keyword formulation, suggestion grounding, the OpenAlex heavy-query throttle, response caches. |
| `queries/` | RUN+LIB | `export_search_contexts.py` (RUN: prod Supabase → candidates), `build_queries.py` (RUN: LLM PICO-folding → `queries.jsonl`), `loader.py` (LIB). |
| `reporting/` | RUN+LIB | `collect_results.py` (aggregate + headline), `metrics.py` (BENCH formula reimplementations), `cost.py` (derived-dollar model), `plots.py` (standard plot set). All four import as LIB; collect/cost/plots also run via `python -m`. |
| `smoke/` | RUN | One verbose end-to-end script per build phase (live API calls, printed stages). Historical build order — useful as worked examples of each layer. |
| `tests/` | — | `uv run pytest` — 183 offline tests incl. the BENCH parity suite. |
| `scripts/` | RUN | One-off diagnostics (e.g. `diagnose_openalex_500.py`). |
| `_backend.py`, `_timing.py` | LIB | Plumbing: the seam that borrows prod services with experiment-side patches; wall-time bookkeeping. |
| `results/` | data | Gitignored: per-arm results, retrieval/judgement caches, plots, collect summaries. |

## 4. Runbook — full pipeline, fresh

You will re-extract queries from prod rather than inherit a dataset. **Expect your
numbers to differ from FINDINGS.md** — the prod query pool has grown and retrieval is
live; that's fine, the comparisons are within-run.

### 4.0 One-time setup

```bash
cd backend/testing/r_and_d/search_experiments
uv sync          # self-contained env; backend is an editable path dep
uv run pytest    # 183 passed = your env is sane (all offline, no keys needed)
```

Credentials — all read from `backend/.env` (loaded by `config.py` no matter the cwd),
shell exports win over the file:

| Env var | Needed by | Needed for | Have it? |
|---------|-----------|-----------|----------|
| `OPENAI_API_KEY` | judge, criteria, formulation (via backend `get_llm`) | every arm run + query build | probably already |
| `OPENALEX_EMAIL` | OpenAlex polite pool (10 req/s vs throttled common pool) | Arms A & B (snowball is call-heavy) | probably already |
| `SUPABASE_URL` + `SUPABASE_KEY` | `queries/export_search_contexts.py` | query extraction only | same as what we have in the repo |
| `COHERE_API_KEY` | `core/ranking.py` rerank | Arms B & C (degrades gracefully: warns, rerank term = 0) | I just created a personal account to get this, can discuss with the team about a shared API key! |
| `SEMANTIC_SCHOLAR_API_KEY` | `retrieval/s2_client.py` (hard error if unset) | Arm C only | In the document with the rest of our API keys |

### 4.1 → 4.5 The stages

```bash
# 1. Extract candidate search contexts from prod (Supabase read-only)
uv run python -m queries.export_search_contexts

# 2. Build the curated query set (LLM PICO-folding; writes queries/queries.jsonl)
uv run python -m queries.build_queries

# 3. THE RUN — all queries × arms A/B/C. Hours of wall-time (~3h typical), ~$30-60
#    in API spend (see reporting/cost.py output for the live estimate).
#    Idempotent + cache-warm: safe to interrupt and re-run, it resumes cheaply.
PYTHONUNBUFFERED=1 uv run run_experiment.py

# 4. Aggregate + headline metrics (offline, seconds)
uv run python -m reporting.collect_results

# 5. Cost breakdown and the standard plots (offline, seconds)
uv run python -m reporting.cost
uv run python -m reporting.plots      # PNGs -> results/plots/
```

Optional extras:

```bash
uv run run_latency.py                 # cold latency probe, n=3 (LATENCY_N to change)
uv run python smoke/phase2_judge.py   # worked example of any single layer
```

Everything is also REPL-drivable — the convention throughout is module-level objects +
`run_xxx()` helpers (e.g. `from reporting.collect_results import run_collect`).

## 5. Sharp edges (the month-three questions, answered now)

- **OpenAlex heavy-query governor.** Any query with >5 boolean operators is capped at
  1 req/s per client and intermittently 500s/429s (don't panic if this happens :D, it's normal but clearly something we'll want to optimise against).
  It's a governor, not a transient — reordering won't fix it. Handled at the pyalex chokepoint (`retrieval/_openalex_throttle.py`),
  simple calls stay full speed. Full story: `config.py` comments + FINDINGS 2026-06-30.
- **S2 keyword starvation (returns few or zero results).** S2 `/paper/search` starves on dense queries — fixed by
  per-leg query formulation (`retrieval/keyword_s2.py` + the protocol split in
  `core/source.py`). Don't "simplify" the legs back together.
- **Snippets are count-only.** Arm C uses S2 snippets as a *count* ranking signal, not
  as evidence text (unlike PF). The snippet-as-evidence variant is the designed-but-unbuilt
  Arm C′ (`docs/specs/spec_arm_c_prime_snippet_evidence.md`).
- **One judge cache, shared across arms.** A query's judgements are written once and
  reused by every arm (that's what makes the comparison fair *and* re-runs cheap).
  Deleting `results/` judgement parquets = re-paying the judge for everything.
- **Throttles are calibrated (can be optimised).** S2 at 1.2s/request and OpenAlex heavy-queries at 1.1s
  were both arrived at empirically (429s at lower values) — see `config.py` before touching.
- **Entry points are `__main__`-guarded** — importing any module is side-effect-free;
  only `uv run <script>` / `python -m <module>` executes. Keep it that way: an unguarded
  top-level run once turned an innocent `import run_experiment` into a live experiment run.

## 6. Docs index

| Doc | Status | Notes |
|-----|--------|-------|
| `README.md` (here) | **CURRENT** | Layout, setup, phase log. |
| `docs/FINDINGS.md` | **CURRENT — canonical results** | Read after the session. |
| `docs/CODE_REUSE_RATIONALE.md` | **CURRENT** | What's ported from PF/BENCH vs written fresh, and why. |
| `docs/report/` | **CURRENT** | Session/slide material (methodology per arm). |
| `../../../../docs/specs/spec_retrieval_experiment_openalex.md` | **DESIGN RECORD** | The plan; code comments cite its § numbers. Layout section superseded by §3 above. |
| `../../../../docs/specs/spec_arm_c_prime_snippet_evidence.md` | **ASPIRATIONAL** | Designed, not built (Arm C′). |
| `../../../../docs/explainers/batched_thompson_sampling.md`, `citation_snowballing.md`, `adaptive_judging.md`, `s2_client_walkthrough.md` | **CURRENT** | Concept explainers for the core/ machinery. |
| `../../../../docs/research/retrieval_strategy_v2_review_and_v3_directions.md` | **BACKGROUND** | Pre-experiment thinking that motivated the ladder. |

Anything not listed here (other specs, `misc_md/`, walkthroughs) is unrelated to this
experiment or historical — check with Aidan before treating it as current.

## 7. Where this could go next (options, not a plan)

Recorded so the context isn't lost — the choice and design are yours:

1. **Productionise an arm** (recommend arm B) — the stated goal. No integration sketch is
   pre-baked; start from `arms/arm_b.py` and the `_backend.py` seam to see what's borrowed
   from prod already.
2. **3-iteration sweep** — PF's diligent default is 3 iterations; we ran 2. Pure config
   overlay (`config.Budgets.n_search_iterations`), no code changes.
3. **Quick/fast mode** — PF's fast-mode quotas as a second config overlay (values in
   `config.Budgets` docstring).
4. **Arm C′** — snippet-as-evidence (spec above).
