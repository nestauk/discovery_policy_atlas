# Boolean Query Testing Framework

This directory contains tools for testing and evaluating LLM-generated boolean queries for academic literature search.

## Overview

The framework consists of three main scripts:
1. **`test_llm_generation.py`** - Generates boolean queries using LLMs and tests their retrieval performance
2. **`plot_experiment.py`** - Analyzes and visualizes the experimental results
3. **`plot_prompt_comparison.py`** - Compares results from two different prompts. Configure comparisons in `config_comparison.yaml` and run: `uv run python testing/r_and_d/boolean_queries/plot_prompt_comparison.py --comparison comparison_1`

## Quick Start

All commands should be run from the `backend` directory:

```bash
cd backend
```

### 0. Generate Baseline Results (Required)

Before running plotting scripts, you must first generate baseline results:

```bash
# Fast mode - count only
uv run python testing/r_and_d/boolean_queries/test_baseline.py --count-only

# Full mode - retrieve all papers
uv run python testing/r_and_d/boolean_queries/test_baseline.py
```

### 1. Generate Test Results

```bash
# Fast mode - count only (no paper ID retrieval, just the total count)
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --count-only --output-name experiment1

# Full mode - retrieve all papers (slower but complete, retrieves all paper IDs)
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --output-name experiment1
```

### 2. Generate Visualizations

For baseline visualisations:

```bash
uv run python testing/r_and_d/boolean_queries/plot_baseline.py
```

For tests:

```bash
# Visualization
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment1

# Analyze only the top_n user questions (I usually stopped running experiments after the first 10 questions were done)
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment1 --n-questions 10
```

## Configuration Files

Two configuration files are provided:

- **`config.yaml`** - Default configuration with Policy Atlas prompts
- **`config_2.yaml`** - Alternative configuration with Wang et al. inspired prompts

Each config file specifies:
- Models to test (e.g., gpt-4o, claude-3-5-sonnet)
- Temperature values
- Prompts to use
- Number of runs per query
- Concurrency settings

## test_llm_generation.py

Tests LLM-generated boolean queries across different models, temperatures, and prompts.

### Usage Examples

```bash
# Default: use config.yaml, full results
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --output-name experiment1

# Use alternate config
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --config config_2.yaml --output-name experiment2

# Count only (much faster - no paper ID retrieval)
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --count-only --output-name experiment1
```

### Arguments

- `--output-name` - Name prefix for output files (default: "llm")
  - Produces `{name}_results.jsonl` or `{name}_counts.jsonl`
- `--config` - Config file name (default: "config.yaml")
- `--count-only` - Only retrieve counts, not full results (much faster)

### Output

Results are saved to `testing/r_and_d/boolean_queries/outputs/{output_name}_results.jsonl`

Each line contains:
- Research question
- Model and temperature used
- Generated boolean query
- Retrieved paper IDs
- Retrieved counts

## plot_experiment.py

Generates comprehensive visualizations and analysis of experimental results.

### Usage Examples

```bash
# Basic usage
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment1

# Analyze more questions
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment1 --n-questions 10

# Use alternate config (must match the config used in test_llm_generation)
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment2 --config config_2.yaml

# Generate combined runs analysis (combine and deduplicate across multiple runs of the same parameters)
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment1 --combine-runs

# Generate comparison charts (single vs combined runs)
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment1 --compare-combined-runs
```

### Arguments

- `--experiment` - Experiment name to analyze (default: "experiment1")
  - Must match the `--output-name` from test_llm_generation.py
- `--n-questions` - Number of questions to analyze (default: 3)
- `--config` - Config file name (default: "config.yaml")
- `--combine-runs` - Combine and deduplicate results across runs
- `--compare-combined-runs` - Generate comparison charts between single and combined runs

### Output

Charts and CSV files are saved to:
- Default: `testing/r_and_d/boolean_queries/outputs/{experiment}/`
- Combined runs: `testing/r_and_d/boolean_queries/outputs/{experiment}/combined_results/`

Each prompt gets its own subdirectory with:

**Individual Question Charts:**
- `retrieved_total_horizontal_{question_id}.png` - Scatter plot of retrieved totals
- `retrieved_total_median_iqr_{question_id}.png` - Median with IQR error bars
- `retrieved_total_temperature_median_iqr_{question_id}.png` - Temperature effect
- `f1_median_iqr_{question_id}.png` - F1 scores with IQR
- `elements_median_iqr_{question_id}.png` - Number of elements

**Prompt Summary Charts:**
- `prompt_retrieved_total_by_model_temp.png` - Retrieved totals by model-temperature
- `prompt_f1_by_model_temp.png` - F1 scores (mean)
- `prompt_f1_median_by_model_temp.png` - F1 scores (median)
- `prompt_f1_by_question.png` - F1 scores by question
- `prompt_f1_median_by_question.png` - F1 scores by question (median)

**CSV Files:**
- `prompt_metrics_by_model_temp.csv` - Aggregated metrics by model-temperature
- `prompt_metrics_by_question.csv` - Aggregated metrics by question

**Comparison Charts** (when `--compare-combined-runs` is used):
- `f1_single_vs_combined.png` - F1 score comparison
- `precision_recall_single_vs_combined.png` - Precision and recall comparison
- `n_elements_single_vs_combined.png` - Number of elements comparison
- `combined_vs_single_metrics.csv` - Detailed comparison metrics

## Complete Workflow Example

```bash
cd backend

# 1. Run experiment with default config
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --output-name my_experiment

# 2. Generate visualizations for first 5 questions
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment my_experiment --n-questions 5

# 3. Generate comparison analysis
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment my_experiment --compare-combined-runs

# Run alternate experiment with different prompts
uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --config config_2.yaml --output-name wang_experiment

# Visualize alternate experiment
uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment wang_experiment --config config_2.yaml --n-questions 5
```

## Available Prompts

See `prompts.py` for the full prompt definitions. Current prompts:

## Adding New Prompts

1. Add your prompt string to `prompts.py`
2. Import it in `test_llm_generation.py`
3. Add it to the `PROMPT_REGISTRY` dictionary
4. Reference it in your config file's `prompts` list

## Metrics

The framework calculates:

- **Precision** - Proportion of retrieved papers that are relevant
- **Recall** - Proportion of relevant papers that were retrieved
- **F1 Score** - Harmonic mean of precision and recall
- **Retrieved Total** - Total number of papers retrieved
- **N Elements** - Number of unique boolean query elements

All metrics are computed against a baseline query for each research question.

## Notes

- Results are saved incrementally (after each query), so interrupted runs can be resumed
- Existing results are skipped to avoid duplication
- Use `--count-only` for fast iteration when testing configurations
- Always use the same config file for both generation and plotting
- The `--combine-runs` flag helps analyze whether multiple runs improve results through deduplication

