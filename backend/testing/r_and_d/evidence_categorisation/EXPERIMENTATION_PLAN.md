# Evidence Categorisation Experimentation Plan

## Problem
- Current accuracy: 43-70% across datasets
- **Critical issue**: Model rarely predicts "Unknown" even when information is insufficient
  - Home Learning: 0/5 unknowns identified (0% recall)
  - Home Heating: 3/9 unknowns identified (33% recall)
  - Childhood Obesity: 0/11 unknowns identified (0% recall)

## Experiments

### Models to Test (5)
1. `gpt-5-nano`
2. `gpt-5-mini` (current baseline)
3. `gpt-5`
4. `gpt-5.1`
5. `gpt-5.2`

### Prompts to Test (2)

#### Prompt A: Current (Baseline)
The existing prompt in `prompts.py`

#### Prompt B: Missing Abstract Handling
**Key change**: Add explicit instruction about missing abstracts

Add to classification instructions:
```
## Handling Missing Information

If the abstract_or_summary is missing or very brief, carefully consider whether the title alone provides enough methodological indicators to confidently assign a category. If the title is also generic or unclear, use "Unknown / Insufficient information" rather than guessing.
```

### Experiment Matrix

**Total experiments**: 5 models × 2 prompts × 3 datasets = **30 runs**

## Metrics

### Primary Metrics
1. **Overall Accuracy**
2. **Unknown Recall**
3. **Macro F1**

### Supporting Metrics
4. Unknown Precision
5. Unknown F1
6. Unknown Support (count)
7. Confusion Matrix

## Implementation

### File Structure
```
evidence_categorisation/
├── EXPERIMENTATION_PLAN.md
├── experiments/
│   └── results_summary.csv          # All experiment results
├── scripts/
│   ├── prompt_variants.py           # Define 2 prompts
│   ├── run_experiment.py            # Run single experiment
│   ├── batch_run_all.sh            # Run all 30 experiments
│   ├── collect_results.py           # Aggregate results into CSV
│   └── visualize_results.py         # Generate plots
├── outputs/
│   └── [exp_id]/                    # Per-experiment results
│       ├── predictions.csv
│       ├── validation_report.txt
│       ├── disagreements.csv
│       └── metadata.json
└── plots/
    ├── model_comparison.png          # Bar charts: Accuracy, Unknown Recall, Macro F1
    ├── prompt_comparison.png         # Prompt impact (for best model only)
    └── accuracy_heatmap.png          # Model × Prompt accuracy heatmap
```

### Scripts Needed

#### 1. `prompt_variants.py`
```python
"""Define prompt variants"""

from prompts import EVIDENCE_CATEGORIES_DEFINITION

# Variant A: Current baseline (import from prompts.py)
from prompts import CLASSIFICATION_SYSTEM_PROMPT as PROMPT_A_SYSTEM
from prompts import CLASSIFICATION_USER_PROMPT as PROMPT_A_USER

# Variant B: Add missing abstract handling
PROMPT_B_SYSTEM = f"""You are an expert evidence evaluator specializing in categorizing research and policy documents according to their evidence type and methodological strength.

Your task is to classify documents into one of 9 evidence categories based on their title, abstract, and metadata.

{EVIDENCE_CATEGORIES_DEFINITION}

## Classification Instructions:

1. Read the document title, abstract, and metadata carefully
2. Identify the PRIMARY evidence type - what is the main methodological approach?
3. Choose the SINGLE BEST-FIT category from the 9 options above
4. Provide brief reasoning (1-2 sentences) explaining your classification
5. Provide a confidence score (0.0-1.0) based on:
   - High confidence (0.8-1.0): Clear methodological indicators, explicit terminology
   - Medium confidence (0.5-0.79): Some indicators but mixed or ambiguous signals
   - Low confidence (0.0-0.49): Very unclear, limited information, or borderline between categories

## Handling Missing Information

If the abstract_or_summary is missing or very brief, carefully consider whether the title alone provides enough methodological indicators to confidently assign a category. If the title is also generic or unclear, use "Unknown / Insufficient information" rather than guessing.

## Edge Case Guidelines:

- If a document DESCRIBES a systematic review but is itself a policy synthesis, classify as "Policy Syntheses & Guidance Documents"
- If a document REFERENCES RCTs but doesn't conduct one, classify based on what it actually does
- If multiple categories could apply, choose the one representing the PRIMARY contribution
- Policy documents that synthesise evidence rank as "Policy Syntheses & Guidance Documents" even if they discuss high-quality studies
- Documents about methodology without presenting findings should be classified as "Expert Opinion and Commentary"

Return your classification in the specified JSON format.
"""

PROMPT_B_USER = PROMPT_A_USER  # Same user prompt

def get_prompt_variant(variant_name):
    """Get system and user prompts for a variant"""
    if variant_name == "variant_a":
        return PROMPT_A_SYSTEM, PROMPT_A_USER
    elif variant_name == "variant_b":
        return PROMPT_B_SYSTEM, PROMPT_B_USER
    else:
        raise ValueError(f"Unknown variant: {variant_name}")
```

#### 2. `run_experiment.py`
```python
"""Run a single experiment: classify + validate"""

import asyncio
import sys
from pathlib import Path
import json
from datetime import datetime
import pandas as pd

# Ensure backend package is importable
backend_dir = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(backend_dir))

from categorise_evidence import EvidenceCategorizer
from validate_classifier import main as validate_main
from prompt_variants import get_prompt_variant

async def run_experiment(model, prompt_variant, dataset):
    """Run classification + validation for one configuration"""

    # Generate experiment ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_id = f"{dataset}_{model}_{prompt_variant}_{timestamp}"

    # Setup paths
    input_csv = f"inputs/run_{dataset}/references.csv"
    validation_csv = f"inputs/run_{dataset}/validation_set.csv"
    output_dir = Path(f"outputs/{exp_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_csv = output_dir / "predictions.csv"
    validation_report = output_dir / "validation_report.txt"
    disagreements_csv = output_dir / "disagreements.csv"

    print(f"\n{'='*60}")
    print(f"Experiment: {exp_id}")
    print(f"{'='*60}")
    print(f"Model: {model}")
    print(f"Prompt: {prompt_variant}")
    print(f"Dataset: {dataset}")

    # Get prompts
    system_prompt, user_prompt = get_prompt_variant(prompt_variant)

    # Note: categorise_evidence.py needs to be modified to accept custom prompts
    # For now, this is a placeholder - you'll need to add this functionality

    # Run classification
    categorizer = EvidenceCategorizer(model=model, temperature=0.0, batch_size=10)

    df = pd.read_csv(input_csv)
    df_classified = await categorizer.classify_dataframe(df, max_concurrent=5)
    df_classified.to_csv(predictions_csv, index=False)

    # Run validation
    validate_main(
        validation_csv=validation_csv,
        predictions_csv=str(predictions_csv),
        output_report=str(validation_report),
        output_disagreements=str(disagreements_csv)
    )

    # Save metadata
    metadata = {
        "experiment_id": exp_id,
        "timestamp": timestamp,
        "model": model,
        "prompt_variant": prompt_variant,
        "dataset": dataset,
    }

    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✅ Experiment complete! Results: {output_dir}")
    return exp_id

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run single experiment")
    parser.add_argument("--model", required=True,
                       choices=["gpt-5-nano", "gpt-5-mini", "gpt-5", "gpt-5.1", "gpt-5.2"])
    parser.add_argument("--prompt", required=True,
                       choices=["variant_a", "variant_b"])
    parser.add_argument("--dataset", required=True,
                       choices=["childhood_obesity", "home_heating", "home_learning"])

    args = parser.parse_args()
    asyncio.run(run_experiment(args.model, args.prompt, args.dataset))
```

#### 3. `batch_run_all.sh`
```bash
#!/bin/bash
# Run all 30 experiments

MODELS=("gpt-5-nano" "gpt-5-mini" "gpt-5" "gpt-5.1" "gpt-5.2")
PROMPTS=("variant_a" "variant_b")
DATASETS=("childhood_obesity" "home_heating" "home_learning")

total=0
for dataset in "${DATASETS[@]}"; do
  for prompt in "${PROMPTS[@]}"; do
    for model in "${MODELS[@]}"; do
      total=$((total + 1))
      echo ""
      echo "[$total/30] Running: $model / $prompt / $dataset"
      python run_experiment.py --model "$model" --prompt "$prompt" --dataset "$dataset"
    done
  done
done

echo ""
echo "✅ All 30 experiments complete!"
```

#### 4. `collect_results.py`
```python
"""Collect all experiment results into results_summary.csv"""

import pandas as pd
import json
from pathlib import Path
import re

def parse_validation_report(report_path):
    """Extract metrics from validation report text file"""
    with open(report_path) as f:
        content = f.read()

    metrics = {}

    # Overall metrics
    acc_match = re.search(r'accuracy: ([\d.]+)', content)
    metrics['accuracy'] = float(acc_match.group(1)) if acc_match else None

    macro_match = re.search(r'macro_f1: ([\d.]+)', content)
    metrics['macro_f1'] = float(macro_match.group(1)) if macro_match else None

    # Unknown category metrics from detailed classification report
    # Pattern: "Unknown / Insufficient information      precision    recall  f1-score   support"
    unknown_match = re.search(
        r'Unknown / Insufficient information\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)',
        content
    )
    if unknown_match:
        metrics['unknown_precision'] = float(unknown_match.group(1))
        metrics['unknown_recall'] = float(unknown_match.group(2))
        metrics['unknown_f1'] = float(unknown_match.group(3))
        metrics['unknown_support'] = int(unknown_match.group(4))
    else:
        # Unknown category not present (recall=0)
        metrics['unknown_precision'] = 0.0
        metrics['unknown_recall'] = 0.0
        metrics['unknown_f1'] = 0.0
        metrics['unknown_support'] = 0

    return metrics

def collect_results():
    """Scan outputs/ and collect all experiment results"""

    results = []
    outputs_dir = Path("outputs")

    for exp_dir in sorted(outputs_dir.glob("*")):
        if not exp_dir.is_dir() or exp_dir.name.startswith('.'):
            continue

        metadata_file = exp_dir / "metadata.json"
        report_file = exp_dir / "validation_report.txt"

        if not metadata_file.exists() or not report_file.exists():
            print(f"⚠️  Skipping {exp_dir.name} (missing files)")
            continue

        # Load metadata
        with open(metadata_file) as f:
            metadata = json.load(f)

        # Parse validation report
        metrics = parse_validation_report(report_file)

        # Combine
        result = {**metadata, **metrics}
        results.append(result)

    # Convert to DataFrame
    df = pd.DataFrame(results)

    if len(df) == 0:
        print("❌ No experiments found!")
        return

    # Sort
    df = df.sort_values(['dataset', 'model', 'prompt_variant'])

    # Save
    Path("experiments").mkdir(exist_ok=True)
    df.to_csv("experiments/results_summary.csv", index=False)

    print(f"\n✅ Collected {len(df)} experiments")
    print(f"   Saved to: experiments/results_summary.csv")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Datasets: {df['dataset'].nunique()}")
    print(f"Models: {df['model'].nunique()}")
    print(f"Prompts: {df['prompt_variant'].nunique()}")
    print(f"\nMetrics collected:")
    print(f"  - Accuracy: {df['accuracy'].min():.3f} to {df['accuracy'].max():.3f}")
    print(f"  - Unknown Recall: {df['unknown_recall'].min():.3f} to {df['unknown_recall'].max():.3f}")
    print(f"  - Macro F1: {df['macro_f1'].min():.3f} to {df['macro_f1'].max():.3f}")

    return df

if __name__ == "__main__":
    collect_results()
```

#### 5. `visualize_results.py`
```python
"""Generate visualizations from experiment results"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

def plot_model_comparison(df, output_dir):
    """Bar charts comparing models across 3 key metrics"""

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Average across datasets and prompts
    model_metrics = df.groupby('model').agg({
        'accuracy': 'mean',
        'unknown_recall': 'mean',
        'macro_f1': 'mean'
    }).sort_values('accuracy', ascending=True)

    # Plot 1: Accuracy
    axes[0].barh(model_metrics.index, model_metrics['accuracy'], color='steelblue')
    axes[0].set_xlabel('Accuracy')
    axes[0].set_title('Model Comparison: Accuracy')
    axes[0].set_xlim([0, 1])
    for i, v in enumerate(model_metrics['accuracy']):
        axes[0].text(v + 0.02, i, f'{v:.2%}', va='center')

    # Plot 2: Unknown Recall
    axes[1].barh(model_metrics.index, model_metrics['unknown_recall'], color='coral')
    axes[1].set_xlabel('Unknown Recall')
    axes[1].set_title('Model Comparison: Unknown Recall')
    axes[1].set_xlim([0, 1])
    axes[1].axvline(x=0.6, color='green', linestyle='--', alpha=0.5, label='Target (60%)')
    axes[1].legend()
    for i, v in enumerate(model_metrics['unknown_recall']):
        axes[1].text(v + 0.02, i, f'{v:.2%}', va='center')

    # Plot 3: Macro F1
    axes[2].barh(model_metrics.index, model_metrics['macro_f1'], color='mediumseagreen')
    axes[2].set_xlabel('Macro F1')
    axes[2].set_title('Model Comparison: Macro F1')
    axes[2].set_xlim([0, 1])
    for i, v in enumerate(model_metrics['macro_f1']):
        axes[2].text(v + 0.02, i, f'{v:.2%}', va='center')

    plt.tight_layout()
    plt.savefig(output_dir / 'model_comparison.png', dpi=300, bbox_inches='tight')
    print(f"   ✓ Saved: model_comparison.png")

def plot_prompt_comparison(df, output_dir):
    """Compare prompts for the best performing model only"""

    # Identify best model by accuracy
    best_model = df.groupby('model')['accuracy'].mean().idxmax()
    print(f"   Best model (by accuracy): {best_model}")

    # Filter to best model
    df_best = df[df['model'] == best_model]

    # Group by prompt variant
    prompt_metrics = df_best.groupby('prompt_variant').agg({
        'accuracy': 'mean',
        'unknown_recall': 'mean',
        'macro_f1': 'mean'
    })

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    x_labels = prompt_metrics.index

    # Plot 1: Accuracy
    axes[0].bar(x_labels, prompt_metrics['accuracy'], color=['steelblue', 'darkorange'])
    axes[0].set_ylabel('Accuracy')
    axes[0].set_title(f'Prompt Comparison: Accuracy\n(Model: {best_model})')
    axes[0].set_ylim([0, 1])
    for i, v in enumerate(prompt_metrics['accuracy']):
        axes[0].text(i, v + 0.02, f'{v:.2%}', ha='center')

    # Plot 2: Unknown Recall
    axes[1].bar(x_labels, prompt_metrics['unknown_recall'], color=['steelblue', 'darkorange'])
    axes[1].set_ylabel('Unknown Recall')
    axes[1].set_title(f'Prompt Comparison: Unknown Recall\n(Model: {best_model})')
    axes[1].set_ylim([0, 1])
    axes[1].axhline(y=0.6, color='green', linestyle='--', alpha=0.5, label='Target')
    axes[1].legend()
    for i, v in enumerate(prompt_metrics['unknown_recall']):
        axes[1].text(i, v + 0.02, f'{v:.2%}', ha='center')

    # Plot 3: Macro F1
    axes[2].bar(x_labels, prompt_metrics['macro_f1'], color=['steelblue', 'darkorange'])
    axes[2].set_ylabel('Macro F1')
    axes[2].set_title(f'Prompt Comparison: Macro F1\n(Model: {best_model})')
    axes[2].set_ylim([0, 1])
    for i, v in enumerate(prompt_metrics['macro_f1']):
        axes[2].text(i, v + 0.02, f'{v:.2%}', ha='center')

    plt.tight_layout()
    plt.savefig(output_dir / 'prompt_comparison.png', dpi=300, bbox_inches='tight')
    print(f"   ✓ Saved: prompt_comparison.png")

def plot_accuracy_heatmap(df, output_dir):
    """Heatmap: Model × Prompt for Accuracy"""

    # Pivot table: rows=model, columns=prompt_variant, values=accuracy (averaged across datasets)
    pivot = df.pivot_table(values='accuracy', index='model', columns='prompt_variant', aggfunc='mean')

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(pivot, annot=True, fmt='.2%', cmap='RdYlGn', vmin=0, vmax=1,
               ax=ax, cbar_kws={'label': 'Accuracy'}, linewidths=0.5)
    ax.set_title('Accuracy Heatmap: Model × Prompt', fontsize=14, fontweight='bold')
    ax.set_xlabel('Prompt Variant', fontsize=12)
    ax.set_ylabel('Model', fontsize=12)

    plt.tight_layout()
    plt.savefig(output_dir / 'accuracy_heatmap.png', dpi=300, bbox_inches='tight')
    print(f"   ✓ Saved: accuracy_heatmap.png")

def main():
    # Load results
    results_csv = Path("experiments/results_summary.csv")
    if not results_csv.exists():
        print("❌ No results found! Run collect_results.py first.")
        return

    df = pd.read_csv(results_csv)
    print(f"Loaded {len(df)} experiments")

    # Create plots directory
    plots_dir = Path("plots")
    plots_dir.mkdir(exist_ok=True)

    print("\nGenerating visualizations...")

    plot_model_comparison(df, plots_dir)
    plot_prompt_comparison(df, plots_dir)
    plot_accuracy_heatmap(df, plots_dir)

    print("\n✅ All plots generated!")
    print(f"   Check: {plots_dir}/")

if __name__ == "__main__":
    main()
```

## Workflow

```bash
# 1. Create scripts
cd /Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/backend/testing/r_and_d/evidence_categorisation/

# 2. Run all experiments
bash batch_run_all.sh

# OR run individually:
python run_experiment.py --model gpt-5-mini --prompt variant_a --dataset home_learning

# 3. Collect results
python collect_results.py

# 4. Generate visualizations
python visualize_results.py

# 5. Review results
cat experiments/results_summary.csv
open plots/model_comparison.png
open plots/prompt_comparison.png
open plots/accuracy_heatmap.png
```

## Visualizations

### 1. `model_comparison.png`
Three horizontal bar charts showing average performance across all datasets and prompts:
- **Accuracy** (steelblue bars)
- **Unknown Recall** (coral bars, with target line at 60%)
- **Macro F1** (green bars)

Purpose: Identify best performing model overall

### 2. `prompt_comparison.png`
Three bar charts comparing variant_a vs variant_b for the **best performing model only**:
- **Accuracy**
- **Unknown Recall** (with target line)
- **Macro F1**

Purpose: Show impact of improved prompt on Unknown category

### 3. `accuracy_heatmap.png`
Heatmap with:
- **Rows**: Models (5)
- **Columns**: Prompt variants (2)
- **Values**: Accuracy (averaged across datasets)
- **Color**: Red-Yellow-Green scale

Purpose: Quick visual comparison of all model × prompt combinations

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Overall Accuracy | 43-70% | >75% |
| Unknown Recall | 0-33% | >60% |
| Macro F1 | 0.41-0.58 | >0.65 |

## Expected Outcomes

1. **Best model**: Likely `gpt-5.2` or `gpt-5.1`
2. **Prompt B impact**: Should improve Unknown Recall significantly (0-33% → 50-70%)
3. **Accuracy tradeoff**: May see slight accuracy drop (<5%) when Unknown detection improves
4. **Best config**: Likely `gpt-5.2` + `variant_b`

## Timeline

- **Day 1**: Create scripts (2-3 hours)
- **Day 2**: Run all 30 experiments (4-6 hours compute)
- **Day 3**: Collect results, generate plots, analyze (2 hours)

**Total: 2-3 days**
