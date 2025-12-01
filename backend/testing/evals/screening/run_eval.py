import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

# Load .env from backend root
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    logger.info(f"Loaded environment variables from {env_path}")
else:
    logger.warning(f".env file not found at {env_path}")

try:
    from app.services.analysis.relevance import RelevanceService
except ImportError as e:
    logger.error(
        f"Failed to import RelevanceService. Ensure you are running from the correct environment. Error: {e}"
    )
    sys.exit(1)

try:
    import config
    import adapter
except ImportError:
    from testing.evals.screening import config
    from testing.evals.screening import adapter


async def evaluate_target(target: dict, output_dir: Path) -> dict:
    """
    Run evaluation for a single target.
    """
    target_name = target["name"]
    logger.info(f"Starting evaluation for: {target_name} ({target['id']})")

    # 1. Load and Adapt Data
    try:
        df = adapter.load_and_adapt_dataset(target)
        logger.info(f"Dataset loaded. Shape: {df.shape}")
    except Exception as e:
        logger.error(f"Failed to load dataset for {target_name}: {e}")
        return {"target": target_name, "error": str(e)}

    if df.empty:
        logger.warning(f"Dataset empty for {target_name}")
        return {"target": target_name, "error": "Dataset empty"}

    # 2. Save temp input
    temp_input_path = output_dir / f"temp_input_{target_name}.csv"
    df.to_csv(temp_input_path, index=False)

    # 3. Run RelevanceService
    service = RelevanceService(query=target["query"], export_dir=str(output_dir))

    # Retry logic for connection errors
    max_retries = 3
    result_path = str(temp_input_path)

    for attempt in range(max_retries):
        try:
            result_path = await service.check_relevance(str(temp_input_path))

            # Verify if results were actually written
            # RelevanceService returns the path even on failure, but if it worked,
            # the CSV should now have 'is_relevant' column populated.
            check_df = pd.read_csv(result_path)

            # Check for success indicators
            if "is_relevant" in check_df.columns:
                # If we have results, break the retry loop
                # Note: It's possible some rows are NaN if partial failure,
                # but if the column exists, the service likely ran.
                break

            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} for {target_name} completed but returned no relevance data. Retrying..."
            )

        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} for {target_name} failed with error: {e}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))  # Linear backoff
            else:
                logger.error(f"All retries failed for {target_name}")
                return {
                    "target": target_name,
                    "error": f"Failed after {max_retries} attempts: {str(e)}",
                }

    # 4. Load Results
    result_df = pd.read_csv(result_path)

    # 5. Calculate Metrics
    metrics = calculate_metrics(result_df)
    metrics["target"] = target_name
    metrics["id"] = target["id"]
    metrics["dataset_source"] = target["dataset_source"]
    metrics["num_docs"] = len(result_df)
    metrics["num_positives"] = int(result_df["ground_truth_relevant"].sum())

    # Save individual result for debugging/plotting later
    result_df = result_df.copy()
    result_df["dataset_source"] = target.get("dataset_source")
    result_df.to_csv(output_dir / f"result_{target_name}.csv", index=False)

    return metrics


def calculate_metrics(df: pd.DataFrame) -> dict:
    """
    Calculate Recall, Precision, WSS@95, F_beta.
    """

    def _mean_or_none(series: pd.Series) -> float | None:
        return float(series.mean()) if not series.empty else None

    # Ensure columns exist and are correct types
    if "is_relevant" not in df.columns:
        # If service failed to add columns, everything is effectively False?
        df["is_relevant"] = False
        df["relevance_confidence"] = 0.0

    # Fill NaNs
    df["is_relevant"] = df["is_relevant"].fillna(False).astype(bool)
    df["relevance_confidence"] = pd.to_numeric(
        df["relevance_confidence"], errors="coerce"
    ).fillna(0.0)
    df["ground_truth_relevant"] = df["ground_truth_relevant"].astype(int)

    y_true = df["ground_truth_relevant"].values
    y_pred = df["is_relevant"].astype(int).values
    y_score = df["relevance_confidence"].values

    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    fn = np.sum((y_true == 1) & (y_pred == 0))
    tn = np.sum((y_true == 0) & (y_pred == 0))

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    beta = 2
    f_beta = (
        (1 + beta**2) * (precision * recall) / ((beta**2 * precision) + recall)
        if (precision + recall) > 0
        else 0.0
    )

    # WSS@95
    # Work Saved over Sampling at 95% Recall

    y_score_series = pd.Series(y_score)
    avg_conf_tp = _mean_or_none(y_score_series[(y_true == 1) & (y_pred == 1)])
    avg_conf_tn = _mean_or_none(y_score_series[(y_true == 0) & (y_pred == 0)])
    avg_conf_fp = _mean_or_none(y_score_series[(y_true == 0) & (y_pred == 1)])
    avg_conf_fn = _mean_or_none(y_score_series[(y_true == 1) & (y_pred == 0)])

    return {
        "recall": float(recall),
        "precision": float(precision),
        "f_beta_2": float(f_beta),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "avg_conf_tp": avg_conf_tp,
        "avg_conf_tn": avg_conf_tn,
        "avg_conf_fp": avg_conf_fp,
        "avg_conf_fn": avg_conf_fn,
    }


async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent / "results" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for target in config.ALL_EVAL_TARGETS:
        metrics = await evaluate_target(target, output_dir)
        if metrics:
            results.append(metrics)

    # Aggregate Report
    if results:
        results_df = pd.DataFrame(results)
        print("\n=== Evaluation Results ===")
        # Columns to show
        cols = [
            "dataset_source",
            "target",
            "num_docs",
            "recall",
            "precision",
            "f_beta_2",
        ]
        print(results_df[cols].to_string())
        print("\n=== Average Confidence by Outcome ===")
        conf_cols = ["avg_conf_tp", "avg_conf_tn", "avg_conf_fp", "avg_conf_fn"]
        conf_df = results_df[["dataset_source", "target"] + conf_cols].copy()
        for col in conf_cols:
            conf_df[col] = conf_df[col].apply(
                lambda x: round(x, 3) if isinstance(x, (int, float)) else x
            )
        print(conf_df.to_string())

        # Save JSON
        with open(output_dir / f"eval_results_{timestamp}.json", "w") as f:
            json.dump(results, f, indent=2)

        # Post-processing (summaries & visualisations)
        try:
            from process_results import process_results as _process_results
        except ImportError:
            from test.evals.screening.process_results import (
                process_results as _process_results,
            )

        _process_results(output_dir)
        logger.info(f"Evaluation complete. Results saved to {output_dir}")
    else:
        logger.error("No results generated.")


if __name__ == "__main__":
    asyncio.run(main())
