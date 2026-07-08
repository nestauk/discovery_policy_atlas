"""Metrics + reporting — the read-only layer over each arm's persisted per-query results.

Pure given the on-disk outputs under `results/` (one level up from this package): nothing here
hits a backend or re-runs retrieval. The three modules form a small pipeline:

  - `metrics`          — the BENCH-pinned scoring primitives (recall@k_est, precision@k, adjusted F1,
                         LBC-nDCG), plus the parallel Highly-Relevant (>=2) cutoff alongside Perfect (==3).
  - `collect_results`  — reads results/arms/{arm}/{qid}.json, pools judgements, applies `metrics`,
                         writes the per-arm/per-query summary to results/collect.
  - `plots`            — strip+box distributions across arms (over their intersection) and the
                         latency bars, written to results/plots.

Result paths resolve via `Path(__file__).parents[1]` (the package root), NOT `.parent` — these
modules live one level below the `results/` root.
"""
