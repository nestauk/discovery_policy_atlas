# Analysis Pipeline Handoff

This note is for the next developer picking up the Agency & Resilience clustering workflow in [`scripts/analysis`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/analysis).

For a deeper explanation of the clustering choices, see [`CLUSTERING_METHODOLOGY.md`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/analysis/CLUSTERING_METHODOLOGY.md). This handoff is the practical version: how to run it, what it is doing, and what outputs to inspect.

## What This Pipeline Does

The pipeline takes extracted intervention themes and outcome themes from the Agency & Resilience work and groups them into reusable thematic families.

At a high level it is trying to answer three questions:

1. Which interventions recur across different searches?
2. Which outcomes recur across different searches?
3. Where is the strongest and most transferable evidence concentrated?

It does this by:

1. Filtering to relevant searches and UK-applicable interventions
2. Embedding intervention and outcome descriptions into vectors
3. Clustering similar descriptions with BERTopic/HDBSCAN
4. Using OpenAI models to label clusters and assign higher-level meta-themes
5. Detecting near-duplicates across searches
6. Exporting spreadsheets, logs, charts, and per-theme CSVs

## End-to-End Run

### Prerequisites

- Run from the repo root: `/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas`
- `uv` installed
- Python dependencies available to `uv run`
- `OPENAI_API_KEY` present in [`backend/.env`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/backend/.env) or your shell environment
- Input workbook present at:
  [`scripts/output/ar_bottom_up/data/qa_review.xlsx`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/data/qa_review.xlsx)

### Main Run Command

From the repo root:

```bash
cd scripts/analysis
uv run python cluster_themes.py
```

### Useful Variants

Skip merge review if you want a faster pass or more fine-grained clusters:

```bash
cd scripts/analysis
uv run python cluster_themes.py --no-merge
```

Rebuild outputs from cache without rerunning clustering and LLM steps:

```bash
cd scripts/analysis
uv run python cluster_themes.py --from-cache
```

Skip charts:

```bash
cd scripts/analysis
uv run python cluster_themes.py --no-viz
```

Skip all LLM use and fall back to TF-IDF labels:

```bash
cd scripts/analysis
uv run python cluster_themes.py --no-llm
```

### What A Healthy Run Looks Like

You should see log stages like:

- geography filtering
- loading the embedding model
- encoding texts
- clustering interventions
- clustering outcomes
- assigning meta-themes
- finding cross-search duplicates
- writing the spreadsheet
- generating visualisations
- exporting per-meta-theme CSVs
- a final summary line

The run should complete without:

- `TOKENIZERS_PARALLELISM` warnings
- noisy `httpx` request logs
- crashes when a filtered dataset is very small or empty

## Brief Methodology

### 1. Filtering

The script filters to Shabeer’s searches only, then keeps only interventions with geography context fit of `match` or `comparable`. Outcomes are retained only if they link back to a surviving intervention from the same project.

This is important because the downstream outputs are intended to emphasise evidence that is more likely to transfer into the UK context.

### 2. Embedding

Intervention summaries and outcome descriptions are embedded with `all-MiniLM-L6-v2`.

Why this model:

- fast enough to run locally
- good quality for short policy-theme descriptions
- deterministic

### 3. Clustering

BERTopic is used with:

- UMAP for dimensionality reduction
- HDBSCAN for density-based clustering
- TF-IDF keyword extraction as a fallback label source

This means similar descriptions are grouped automatically, while isolated items can remain outliers instead of being forced into bad clusters.

### 4. LLM Labelling And Grouping

If LLM mode is enabled:

- `gpt-5.4-mini` labels clusters
- optional merge review checks whether very similar clusters should be merged
- `gpt-5.4` assigns clusters to broader meta-themes

The reference meta-themes are suggestions, not a closed taxonomy. The model can create emergent themes where the existing buckets do not fit.

### 5. Duplicate Detection

The pipeline computes cosine similarity between items from different searches and reports likely duplicates above a configurable threshold.

This is useful for seeing where multiple search framings are actually surfacing the same intervention or outcome concepts.

### 6. Visualisation And Export

The script produces both tabular outputs and presentation-friendly charts. Some outputs use only positive-verdict outcomes so that the result is more clearly framed as “where positive evidence sits”, while unfiltered outputs are also retained for completeness.

## Output Summary

All outputs are written under:
[`scripts/output/ar_bottom_up/`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/)

### Spreadsheet

Path:
[`scripts/output/ar_bottom_up/data/theme_clusters.xlsx`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/data/theme_clusters.xlsx)

What it contains:

- intervention cluster summaries
- intervention member detail
- intervention cluster similarity table
- intervention duplicate pairs
- outcome cluster summaries
- outcome member detail
- outcome cluster similarity table
- outcome duplicate pairs

Use this when you want the full audit trail and a table you can filter manually.

### Logs

Paths:

- [`scripts/output/ar_bottom_up/logs/cluster_report.log`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/logs/cluster_report.log)
- [`scripts/output/ar_bottom_up/logs/emergent_meta_themes.log`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/logs/emergent_meta_themes.log)

What they contain:

- human-readable summaries of intervention and outcome families
- cross-search duplicate listings
- definitions and rationale for any emergent meta-themes created by the LLM

Use these when you want a narrative summary rather than raw sheets.

### Visualisations

Directory:
[`scripts/output/ar_bottom_up/viz/`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/viz/)

Main chart types:

- `umap.png` and `.html`
  - 2D map of items coloured by cluster
  - good for sanity-checking whether clusters look coherent

- `cluster_heatmap.png` and `.html`
  - search query by cluster coverage
  - good for seeing which searches contribute to which families

- `themed_heatmap.png` and `.html`
  - search query by meta-theme coverage
  - good for a higher-level overview

- `themed_positive_heatmap.png` and `.html`
  - same as above, but only positive-verdict outcomes

- `themed_bar.png` and `.html`
  - evidence volume by meta-theme
  - intervention bars use source document counts
  - outcome bars can show verdict composition or evidence category composition depending on available columns

- `drilldowns/`
  - one chart per meta-theme showing the clusters inside it
  - good for moving from top-level themes to specific outcome families

### Per-Meta-Theme CSVs

Directory:
[`scripts/output/ar_bottom_up/data/outcome_by_meta_theme/`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/output/ar_bottom_up/data/outcome_by_meta_theme/)

What they contain:

- one CSV per meta-theme
- positive-verdict outcomes only
- linked intervention
- project title
- verdict / magnitude / direction / mechanism
- source studies

Use these when someone wants a theme-specific working file without opening the full spreadsheet.

## Current Script Entry Points

- [`cluster_themes.py`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/analysis/cluster_themes.py)
  - orchestration, filtering, caching, spreadsheet export, logs

- [`clustering.py`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/analysis/clustering.py)
  - clustering logic, LLM labelling, meta-theme assignment, duplicate detection, report builders

- [`cluster_viz.py`](/Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/scripts/analysis/cluster_viz.py)
  - chart generation and figure export

## Recent Hardening Changes

These are already in place and are worth knowing before changing the pipeline:

- cache reuse is validated against the current filtered input, so `--from-cache` will fail fast if the underlying workbook changed
- outcomes are linked back to interventions using a per-project stable key, not intervention name alone
- tiny or empty filtered corpora no longer crash clustering and reporting
- chart export always writes HTML; PNG export is best-effort
- tokenizer fork warnings and noisy HTTP request logs are suppressed
- the logger name is `cluster_themes`, not `__main__`

## Known Follow-Ups

Not blockers for running the pipeline, but reasonable next tasks:

- add a short timing summary per stage
- add a small regression test layer around cache mismatch and empty-dataset paths
- promote drilldown generation from silent/debug output to a small `INFO` summary

## Recommended Starting Point For The Next Developer

1. Run `uv run python cluster_themes.py --no-merge`
2. Check the final summary line and confirm outputs were written
3. Open:
   - `theme_clusters.xlsx`
   - `logs/cluster_report.log`
   - `viz/outcomes/themed_bar.html`
   - `viz/outcomes/themed_positive_heatmap.html`
4. If the outputs look sensible, rerun without `--no-merge` and compare the shape of the families

