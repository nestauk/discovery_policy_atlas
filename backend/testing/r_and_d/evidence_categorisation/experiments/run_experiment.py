"""
Run a single evidence categorisation experiment.

Usage:
    python run_experiment.py --model gpt-5-mini --prompt variant_a --dataset run_child_obesity
"""

import asyncio
import sys
from pathlib import Path
import json
from datetime import datetime
import pandas as pd

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_DIR.parents[2]

# Add paths for imports
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from prompt_variants import get_prompt_variant  # noqa: E402
from categorise_evidence import EvidenceCategorizer  # noqa: E402
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
    max_concurrent: int = 5,
) -> str:
    """
    Run a single experiment: classify documents and validate against ground truth.

    Args:
        model: Model name (e.g., "gpt-5-mini")
        prompt_variant: Prompt variant ("variant_a" or "variant_b")
        dataset: Dataset folder name (e.g., "run_child_obesity")
        batch_size: Batch size for classification
        max_concurrent: Max concurrent API calls

    Returns:
        Experiment ID
    """
    # Generate experiment ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Shorten model name for directory (remove "gpt-" prefix)
    model_short = model.replace("gpt-", "").replace(".", "")
    exp_id = f"{dataset}_{model_short}_{prompt_variant}_{timestamp}"

    # Setup paths
    input_csv = PROJECT_DIR / "inputs" / dataset / "references.csv"
    validation_csv = PROJECT_DIR / "inputs" / dataset / "validation_set.csv"
    output_dir = PROJECT_DIR / "outputs_experiments" / exp_id
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_csv = output_dir / "predictions.csv"
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

    # Get prompts for this variant
    system_prompt, user_prompt = get_prompt_variant(prompt_variant)

    # Initialize categorizer with custom prompts
    print("\nInitializing categorizer...")
    categorizer = EvidenceCategorizer(
        model=model,
        temperature=0.0,
        batch_size=batch_size,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    # Load and classify documents
    print(f"Loading documents from: {input_csv}")
    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} documents")

    print("\nClassifying documents...")
    df_classified = await categorizer.classify_dataframe(
        df, max_concurrent=max_concurrent
    )

    # Save predictions
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
        "max_concurrent": max_concurrent,
    }

    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 60)
    print(f"EXPERIMENT COMPLETE: {exp_id}")
    print(f"Results saved to: {output_dir}")
    print("=" * 60 + "\n")

    return exp_id


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a single evidence categorisation experiment"
    )
    parser.add_argument(
        "--model",
        required=True,
        choices=MODELS,
        help=f"Model to use. Options: {MODELS}",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        choices=PROMPTS,
        help=f"Prompt variant. Options: {PROMPTS}",
    )
    parser.add_argument(
        "--dataset",
        required=True,
        choices=DATASETS,
        help=f"Dataset folder name. Options: {DATASETS}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for processing (default: 10)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Max concurrent API calls (default: 5)",
    )

    args = parser.parse_args()

    asyncio.run(
        run_experiment(
            model=args.model,
            prompt_variant=args.prompt,
            dataset=args.dataset,
            batch_size=args.batch_size,
            max_concurrent=args.max_concurrent,
        )
    )


if __name__ == "__main__":
    main()
