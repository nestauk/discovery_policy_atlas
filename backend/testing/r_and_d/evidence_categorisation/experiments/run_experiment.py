"""
Run a single evidence categorisation experiment.

Usage:
    python run_experiment.py --model gpt-5-mini --prompt variant_a --dataset run_child_obesity
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Setup paths for imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR.parents[2]))  # backend dir

from prompt_variants import get_prompt_variant  # noqa: E402
from categorise_evidence import classify_dataframe  # noqa: E402
from validate_classifier import main as run_validation  # noqa: E402

# Available options
MODELS = ["gpt-5-mini", "gpt-5", "gpt-5.2"]
PROMPTS = ["variant_a", "variant_b"]
DATASETS = ["run_child_obesity", "run_home_heating", "run_intervention_home_learning"]


async def run_experiment(
    model: str,
    prompt_variant: str,
    dataset: str,
    batch_size: int = 10,
) -> str:
    """
    Run a single experiment: classify documents and validate against ground truth.

    Args:
        model: Model name (e.g., "gpt-5-mini")
        prompt_variant: Prompt variant ("variant_a" or "variant_b")
        dataset: Dataset folder name (e.g., "run_child_obesity")
        batch_size: Batch size for classification

    Returns:
        Experiment ID
    """
    # Generate experiment ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_short = model.replace("gpt-", "").replace(".", "")
    exp_id = f"{dataset}_{model_short}_{prompt_variant}_{timestamp}"

    # Setup paths
    input_csv = PROJECT_DIR / "inputs" / dataset / "references.csv"
    validation_csv = PROJECT_DIR / "inputs" / dataset / "validation_set.csv"
    output_dir = PROJECT_DIR / "outputs_experiments" / exp_id
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_csv = output_dir / "predictions.csv"
    jsonl_path = output_dir / "classification_results.jsonl"
    validation_report = output_dir / "validation_report.txt"
    disagreements_csv = output_dir / "disagreements.csv"

    print("\n" + "=" * 60)
    print(f"EXPERIMENT: {exp_id}")
    print("=" * 60)
    print(f"Model:   {model}")
    print(f"Prompt:  {prompt_variant}")
    print(f"Dataset: {dataset}")
    print(f"Output:  {output_dir}")
    print("=" * 60)

    # Load and classify documents
    print(f"Loading documents from: {input_csv}")
    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} documents")

    # TODO: prompt variants not yet supported with classify_dataframe
    # Would need to update classify_dataframe to accept custom prompts
    _ = get_prompt_variant(prompt_variant)

    print("\nClassifying documents...")
    df_classified = await classify_dataframe(
        df, output_path=str(jsonl_path), model=model, batch_size=batch_size
    )

    print(f"\nSaving predictions to: {predictions_csv}")
    df_classified.to_csv(predictions_csv, index=False)

    # Run validation
    print("\nRunning validation...")
    run_validation(
        validation_csv=str(validation_csv),
        predictions_csv=str(predictions_csv),
        output_report=str(validation_report),
        output_disagreements=str(disagreements_csv),
    )

    # Save experiment metadata
    metadata = {
        "experiment_id": exp_id,
        "timestamp": timestamp,
        "model": model,
        "prompt_variant": prompt_variant,
        "dataset": dataset,
        "input_csv": str(input_csv),
        "validation_csv": str(validation_csv),
        "output_dir": str(output_dir),
        "batch_size": batch_size,
    }

    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 60)
    print(f"EXPERIMENT COMPLETE: {exp_id}")
    print(f"Results saved to: {output_dir}")
    print("=" * 60 + "\n")

    return exp_id


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a single evidence categorisation experiment"
    )
    parser.add_argument(
        "--model", required=True, choices=MODELS, help=f"Model to use: {MODELS}"
    )
    parser.add_argument(
        "--prompt", required=True, choices=PROMPTS, help=f"Prompt variant: {PROMPTS}"
    )
    parser.add_argument(
        "--dataset", required=True, choices=DATASETS, help=f"Dataset folder: {DATASETS}"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10, help="Batch size (default: 10)"
    )
    args = parser.parse_args()

    asyncio.run(
        run_experiment(
            model=args.model,
            prompt_variant=args.prompt,
            dataset=args.dataset,
            batch_size=args.batch_size,
        )
    )
