"""
Collect all experiment results into a single CSV file.

Usage:
    python collect_results.py
"""

import json
import re
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs_experiments"


def parse_validation_report(report_path: Path) -> dict:
    """
    Extract metrics from a validation report text file.

    Args:
        report_path: Path to validation_report.txt

    Returns:
        Dictionary of metrics
    """
    with open(report_path) as f:
        content = f.read()

    metrics = {}

    # Overall metrics section
    acc_match = re.search(r"accuracy: ([\d.]+)", content)
    metrics["accuracy"] = float(acc_match.group(1)) if acc_match else None

    macro_f1_match = re.search(r"macro_f1: ([\d.]+)", content)
    metrics["macro_f1"] = float(macro_f1_match.group(1)) if macro_f1_match else None

    macro_precision_match = re.search(r"macro_precision: ([\d.]+)", content)
    metrics["macro_precision"] = (
        float(macro_precision_match.group(1)) if macro_precision_match else None
    )

    macro_recall_match = re.search(r"macro_recall: ([\d.]+)", content)
    metrics["macro_recall"] = (
        float(macro_recall_match.group(1)) if macro_recall_match else None
    )

    weighted_f1_match = re.search(r"weighted_f1: ([\d.]+)", content)
    metrics["weighted_f1"] = (
        float(weighted_f1_match.group(1)) if weighted_f1_match else None
    )

    # Unknown category metrics from detailed classification report
    # Format: "Unknown / Insufficient information      0.750     0.333     0.462         9"
    unknown_match = re.search(
        r"Unknown / Insufficient information\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)",
        content,
    )
    if unknown_match:
        metrics["unknown_precision"] = float(unknown_match.group(1))
        metrics["unknown_recall"] = float(unknown_match.group(2))
        metrics["unknown_f1"] = float(unknown_match.group(3))
        metrics["unknown_support"] = int(unknown_match.group(4))
    else:
        # Unknown category might not appear if there were no predictions or ground truth
        metrics["unknown_precision"] = 0.0
        metrics["unknown_recall"] = 0.0
        metrics["unknown_f1"] = 0.0
        metrics["unknown_support"] = 0

    # Confidence analysis
    correct_conf_match = re.search(
        r"Correct predictions - Mean confidence: ([\d.]+)", content
    )
    metrics["confidence_correct"] = (
        float(correct_conf_match.group(1)) if correct_conf_match else None
    )

    incorrect_conf_match = re.search(
        r"Incorrect predictions - Mean confidence: ([\d.]+)", content
    )
    metrics["confidence_incorrect"] = (
        float(incorrect_conf_match.group(1)) if incorrect_conf_match else None
    )

    correct_count_match = re.search(r"Correct count: (\d+)", content)
    metrics["correct_count"] = (
        int(correct_count_match.group(1)) if correct_count_match else None
    )

    incorrect_count_match = re.search(r"Incorrect count: (\d+)", content)
    metrics["incorrect_count"] = (
        int(incorrect_count_match.group(1)) if incorrect_count_match else None
    )

    return metrics


def collect_results() -> pd.DataFrame:
    """
    Scan outputs_experiments/ and collect all experiment results.

    Returns:
        DataFrame with all experiment results
    """
    if not OUTPUTS_DIR.exists():
        print(f"Output directory not found: {OUTPUTS_DIR}")
        return pd.DataFrame()

    results = []

    for exp_dir in sorted(OUTPUTS_DIR.glob("*")):
        if not exp_dir.is_dir() or exp_dir.name.startswith("."):
            continue

        metadata_file = exp_dir / "metadata.json"
        report_file = exp_dir / "validation_report.txt"

        if not metadata_file.exists():
            print(f"  Skipping {exp_dir.name} (no metadata.json)")
            continue

        if not report_file.exists():
            print(f"  Skipping {exp_dir.name} (no validation_report.txt)")
            continue

        # Load metadata
        with open(metadata_file) as f:
            metadata = json.load(f)

        # Parse validation report
        metrics = parse_validation_report(report_file)

        # Combine metadata and metrics
        result = {
            "experiment_id": metadata.get("experiment_id"),
            "timestamp": metadata.get("timestamp"),
            "model": metadata.get("model"),
            "prompt_variant": metadata.get("prompt_variant"),
            "dataset": metadata.get("dataset"),
            **metrics,
        }
        results.append(result)

    if not results:
        print("No experiments found!")
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame(results)

    # Sort by dataset, model, prompt_variant
    df = df.sort_values(["dataset", "model", "prompt_variant"])

    return df


def main():
    print("=" * 60)
    print("Collecting Experiment Results")
    print("=" * 60)
    print(f"Scanning: {OUTPUTS_DIR}")
    print()

    df = collect_results()

    if len(df) == 0:
        print("No experiments to collect!")
        return

    # Save to CSV
    output_csv = SCRIPT_DIR / "results_summary.csv"
    df.to_csv(output_csv, index=False)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Experiments collected: {len(df)}")
    print(f"Models:   {df['model'].nunique()} ({', '.join(df['model'].unique())})")
    print(
        f"Prompts:  {df['prompt_variant'].nunique()} ({', '.join(df['prompt_variant'].unique())})"
    )
    print(f"Datasets: {df['dataset'].nunique()} ({', '.join(df['dataset'].unique())})")
    print()
    print("Key Metrics (averaged across all experiments):")
    print(
        f"  Accuracy:       {df['accuracy'].mean():.3f} (range: {df['accuracy'].min():.3f} - {df['accuracy'].max():.3f})"
    )
    print(
        f"  Unknown Recall: {df['unknown_recall'].mean():.3f} (range: {df['unknown_recall'].min():.3f} - {df['unknown_recall'].max():.3f})"
    )
    print(
        f"  Macro F1:       {df['macro_f1'].mean():.3f} (range: {df['macro_f1'].min():.3f} - {df['macro_f1'].max():.3f})"
    )
    print()
    print(f"Results saved to: {output_csv}")
    print("=" * 60)


if __name__ == "__main__":
    main()
