# Evidence Categorisation

R&D experiment to automatically classify research and policy documents into an evidence hierarchy using LLMs. This helps assess the strength and type of evidence in a corpus.

## Evidence Categories

From strongest to weakest evidence:

1. **Systematic Review & Meta-Analysis** - Cochrane reviews, PRISMA studies
2. **RCTs & Quasi-Experimental** - Randomized trials, controlled studies
3. **Observational Studies** - Cohort, case-control, cross-sectional
4. **Modelling & Simulation** - Economic models, forecasting
5. **Policy Syntheses & Guidance** - White papers, policy briefs
6. **Qualitative & Contextual** - Interviews, focus groups, case studies
7. **Expert Opinion & Commentary** - Editorials, thought leadership
8. **Other (Non-evidence)** - Statistical bulletins, legislation
9. **Unknown / Insufficient info** - Not enough information to classify

## Quick Start

From the `backend/` directory:

```bash
uv run python testing/r_and_d/evidence_categorisation/categorise_evidence.py \
  --input testing/r_and_d/evidence_categorisation/inputs/references.csv \
  --output testing/r_and_d/evidence_categorisation/outputs/categorised_evidence.csv
```

### Options

- `--model` - LLM model (default: gpt-5.2)
- `--batch-size` - Documents per batch (default: 10)
- `--sleep-time` - Seconds between batches (default: 0.5)

## Input/Output

**Input CSV** needs: `title`, `abstract_or_summary`, `source`, `document_type`, `year`

**Output CSV** adds: `evidence_category`, `evidence_confidence` (0-1), `category_reasoning`

## Running Experiments

The `experiments/` directory contains tools for testing different model/prompt combinations against validation sets.

```bash
# Run a single experiment
uv run python testing/r_and_d/evidence_categorisation/experiments/run_experiment.py \
  --model gpt-5.2 --prompt variant_a --dataset run_child_obesity

# Run all combinations (models × prompts × datasets)
./testing/r_and_d/evidence_categorisation/experiments/batch_run_all.sh

# Collect and visualise results
uv run python testing/r_and_d/evidence_categorisation/experiments/collect_results.py
uv run python testing/r_and_d/evidence_categorisation/experiments/visualize_results.py
```

Experiments require a `validation_set.csv` (with ground truth labels) in each dataset folder under `inputs/`.

## Validation with Argilla

Optional: use Argilla to manually label documents and validate classifier accuracy.

```bash
# Load documents for labelling
uv run python testing/r_and_d/evidence_categorisation/setup_argilla.py \
  --csv inputs/references.csv --dataset-name evidence-categorization --api-key admin.apikey

# Export labelled results
uv run python testing/r_and_d/evidence_categorisation/export_from_argilla.py \
  --dataset-name evidence-categorization --output inputs/validation_set.csv --api-key admin.apikey
```

## Key Files

- `categorise_evidence.py` - Main script (uses `LLMProcessor` from `app.utils.llm.batch_check`)
- `prompts.py` - LLM prompts and detailed category definitions
- `setup_argilla.py` / `export_from_argilla.py` - Argilla integration
