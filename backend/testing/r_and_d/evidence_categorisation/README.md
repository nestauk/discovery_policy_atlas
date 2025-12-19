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

## Experiment Workflow

There are two ways to use this:

### Option A: Simple Classification (with optional validation)

1. Run `categorise_evidence.py` on your data (see Quick Start above)
2. Optionally validate results:
   - Load output into Argilla for manual labelling → export as `validation_set.csv`
   - Run `validate_classifier.py --validation validation_set.csv --predictions <your_output>.csv`

### Option B: Full Experiment Pipeline

To evaluate classifier performance across models/prompts, follow this sequence:

**1. Create validation set (manual labelling via Argilla)**

```bash
# Start Argilla (if not running)
docker run -d --name argilla -p 6900:6900 argilla/argilla-quickstart:latest

# Load documents into Argilla for labelling
uv run python testing/r_and_d/evidence_categorisation/setup_argilla.py \
  --csv inputs/references.csv --dataset-name evidence-categorization --api-key admin.apikey

# Label documents in Argilla UI at http://localhost:6900

# Export labelled results as ground truth
uv run python testing/r_and_d/evidence_categorisation/export_from_argilla.py \
  --dataset-name evidence-categorization --output inputs/<dataset>/validation_set.csv --api-key admin.apikey
```

**2. Run experiments**

```bash
# Run a single experiment
uv run python testing/r_and_d/evidence_categorisation/experiments/run_experiment.py \
  --model gpt-5.2 --prompt variant_a --dataset run_child_obesity

# Or run all combinations (models × prompts × datasets)
./testing/r_and_d/evidence_categorisation/experiments/batch_run_all.sh
```

**3. Collect and analyse results**

```bash
uv run python testing/r_and_d/evidence_categorisation/experiments/collect_results.py
uv run python testing/r_and_d/evidence_categorisation/experiments/visualize_results.py
```

Results are saved to `experiments/results_summary.csv` and `plots/`.

## Key Files

- `categorise_evidence.py` - Main script (uses `LLMProcessor` from `app.utils.llm.batch_check`)
- `prompts.py` - LLM prompts and detailed category definitions
- `setup_argilla.py` / `export_from_argilla.py` - Argilla integration
