"""
Collect all experiment results into a single CSV file.

Usage:
    python collect_results.py
"""

import json
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs_experiments"


def collect_results() -> pd.DataFrame:
    """
    Scan outputs_experiments/ and collect all experiment results.

    Returns:
        DataFrame with all experiment results
    """
    if not OUTPUTS_DIR.exists():
        logger.warning(f"Output directory not found: {OUTPUTS_DIR}")
        return pd.DataFrame()

    results = []

    for exp_dir in sorted(OUTPUTS_DIR.glob("*")):
        if not exp_dir.is_dir() or exp_dir.name.startswith("."):
            continue

        metadata_file = exp_dir / "metadata.json"
        metrics_file = exp_dir / "validation_report.json"

        if not metadata_file.exists():
            logger.debug(f"Skipping {exp_dir.name} (no metadata.json)")
            continue

        if not metrics_file.exists():
            logger.debug(f"Skipping {exp_dir.name} (no validation_report.json)")
            continue

        with open(metadata_file) as f:
            metadata = json.load(f)
        with open(metrics_file) as f:
            metrics = json.load(f)

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
        logger.warning("No experiments found!")
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values(["dataset", "model", "prompt_variant"])
    return df


if __name__ == "__main__":
    logger.info("Collecting experiment results")
    logger.info(f"Scanning: {OUTPUTS_DIR}")

    df = collect_results()

    if len(df) == 0:
        logger.warning("No experiments to collect!")
    else:
        output_csv = SCRIPT_DIR / "results_summary.csv"
        df.to_csv(output_csv, index=False)

        logger.info(f"Experiments collected: {len(df)}")
        logger.info(
            f"Models: {df['model'].nunique()} ({', '.join(df['model'].unique())})"
        )
        logger.info(
            f"Prompts: {df['prompt_variant'].nunique()} ({', '.join(df['prompt_variant'].unique())})"
        )
        logger.info(
            f"Datasets: {df['dataset'].nunique()} ({', '.join(df['dataset'].unique())})"
        )
        logger.info(
            f"Accuracy: {df['accuracy'].mean():.3f} (range: {df['accuracy'].min():.3f} - {df['accuracy'].max():.3f})"
        )
        logger.info(
            f"Macro F1: {df['macro_f1'].mean():.3f} (range: {df['macro_f1'].min():.3f} - {df['macro_f1'].max():.3f})"
        )
        logger.info(
            f"Weighted F1: {df['weighted_f1'].mean():.3f} (range: {df['weighted_f1'].min():.3f} - {df['weighted_f1'].max():.3f})"
        )
        logger.info(f"Results saved to: {output_csv}")
