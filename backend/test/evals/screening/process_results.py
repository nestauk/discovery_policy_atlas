import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)


def process_results(results_dir: Optional[Path | str] = None):
    """
    Generate summaries and visualisations for a given screening evaluation run.

    If results_dir is None, the most recent directory under ./results is used.
    """
    base_results_dir = Path(__file__).parent / "results"
    if results_dir is None:
        results_dir = _find_latest_results_dir(base_results_dir)
        if results_dir is None:
            raise FileNotFoundError(
                f"No results directories found under {base_results_dir}"
            )
    else:
        results_dir = Path(results_dir)

    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    logger.info(f"Processing evaluation outputs in {results_dir}")

    eval_results_path = _find_eval_results_file(results_dir)
    with open(eval_results_path, "r") as f:
        eval_results = json.load(f)

    results_df = pd.DataFrame(eval_results)
    metrics_df = results_df.dropna(subset=["recall"])
    timestamp = results_dir.name

    # Write summary JSONs
    summary_overall = build_summary(metrics_df)
    (results_dir / f"summary_overall_{timestamp}.json").write_text(
        json.dumps(summary_overall, indent=2)
    )

    for dataset_source in metrics_df["dataset_source"].dropna().unique():
        ds_df = metrics_df[metrics_df["dataset_source"] == dataset_source]
        ds_summary = build_summary(ds_df)
        safe_name = str(dataset_source).lower().replace(" ", "_")
        (results_dir / f"summary_{safe_name}_{timestamp}.json").write_text(
            json.dumps(ds_summary, indent=2)
        )

    # Visualisations
    doc_df = _load_document_level_data(results_dir, results_df)
    if doc_df.empty:
        logger.warning("No document-level CSVs found; skipping visualisations.")
        return

    sns.set_theme(style="whitegrid")
    _plot_confidence_hist(doc_df, results_dir / "confidence_dist.png", "(All Datasets)")
    _plot_calibration(doc_df, results_dir / "calibration_plot.png", "(All Datasets)")

    if "dataset_source" in doc_df.columns and doc_df["dataset_source"].notna().any():
        for source in doc_df["dataset_source"].dropna().unique():
            subset = doc_df[doc_df["dataset_source"] == source]
            if subset.empty:
                continue
            safe_name = str(source).lower().replace(" ", "_")
            title_suffix = f"({source})"
            _plot_confidence_hist(
                subset, results_dir / f"confidence_dist_{safe_name}.png", title_suffix
            )
            _plot_calibration(
                subset, results_dir / f"calibration_plot_{safe_name}.png", title_suffix
            )


def _find_latest_results_dir(base_dir: Path) -> Optional[Path]:
    dirs = [p for p in base_dir.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.name)


def _find_eval_results_file(results_dir: Path) -> Path:
    candidates = sorted(results_dir.glob("eval_results_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No eval_results_*.json found in {results_dir}")
    return candidates[-1]


def build_summary(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Aggregate metrics for a subset of result rows."""
    if df.empty:
        return {}

    def _mean(series: pd.Series) -> Optional[float]:
        series = series.dropna()
        return float(series.mean()) if not series.empty else None

    summary = {
        "num_targets": int(df.shape[0]),
        "total_documents": int(df["num_docs"].sum(skipna=True))
        if "num_docs" in df
        else None,
        "total_tp": int(df["tp"].sum(skipna=True)) if "tp" in df else None,
        "total_fp": int(df["fp"].sum(skipna=True)) if "fp" in df else None,
        "total_fn": int(df["fn"].sum(skipna=True)) if "fn" in df else None,
        "total_tn": int(df["tn"].sum(skipna=True)) if "tn" in df else None,
        "mean_recall": _mean(df["recall"]),
        "mean_precision": _mean(df["precision"]),
        "mean_f_beta_2": _mean(df["f_beta_2"]),
        "mean_avg_conf_tp": _mean(df["avg_conf_tp"]) if "avg_conf_tp" in df else None,
        "mean_avg_conf_tn": _mean(df["avg_conf_tn"]) if "avg_conf_tn" in df else None,
        "mean_avg_conf_fp": _mean(df["avg_conf_fp"]) if "avg_conf_fp" in df else None,
        "mean_avg_conf_fn": _mean(df["avg_conf_fn"]) if "avg_conf_fn" in df else None,
    }
    return summary


def _load_document_level_data(
    results_dir: Path, results_df: pd.DataFrame
) -> pd.DataFrame:
    mapping = {
        row["target"]: row.get("dataset_source")
        for row in results_df.to_dict("records")
    }
    doc_frames = []

    for csv_file in results_dir.glob("result_*.csv"):
        try:
            df = pd.read_csv(csv_file)
        except Exception as exc:
            logger.warning(f"Failed to read {csv_file}: {exc}")
            continue

        if "dataset_source" not in df.columns or df["dataset_source"].isna().all():
            target_name = csv_file.stem.replace("result_", "")
            df["dataset_source"] = mapping.get(target_name)

        df["pred_label"] = df["is_relevant"].map(
            {True: "Predicted Relevant", False: "Predicted Irrelevant"}
        )
        df["is_correct"] = df["is_relevant"].astype(int) == df["ground_truth_relevant"]
        doc_frames.append(df)

    if not doc_frames:
        return pd.DataFrame()

    combined = pd.concat(doc_frames, ignore_index=True)
    combined["relevance_confidence"] = pd.to_numeric(
        combined["relevance_confidence"], errors="coerce"
    ).fillna(0.0)
    return combined


def _plot_confidence_hist(df: pd.DataFrame, path: Path, title_suffix: str = ""):
    plt.figure(figsize=(10, 6))
    bins = np.linspace(0, 1, 11)
    bin_labels = [f"{bins[i]:.1f}–{bins[i + 1]:.1f}" for i in range(len(bins) - 1)]
    df = df.copy()
    df["conf_bin"] = pd.cut(
        df["relevance_confidence"], bins=bins, include_lowest=True, labels=bin_labels
    )
    pivot = (
        df.groupby(["conf_bin", "pred_label"])
        .size()
        .reset_index(name="count")
        .pivot(index="conf_bin", columns="pred_label", values="count")
        .fillna(0)
    )
    pivot.plot(kind="bar", stacked=True, color=["#1f77b4", "#ff7f0e"], width=0.9)
    plt.xticks(rotation=45, ha="right")
    plt.title(f"Confidence Score Distribution {title_suffix}".strip())
    plt.xlabel("Confidence Score")
    plt.ylabel("Document Count")
    plt.legend(title="Prediction")
    plt.savefig(path)
    plt.close()


def _plot_calibration(df: pd.DataFrame, path: Path, title_suffix: str = ""):
    plt.figure(figsize=(8, 8))
    plt.plot([0, 1], [0, 1], "k--", label="Perfect Calibration")

    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    colors = {"Predicted Relevant": "green", "Predicted Irrelevant": "red"}

    for pred_label in ["Predicted Relevant", "Predicted Irrelevant"]:
        subset = df[df["pred_label"] == pred_label].copy()
        if subset.empty:
            continue

        subset["conf_bin"] = pd.cut(
            subset["relevance_confidence"], bins=bins, include_lowest=True
        )
        grouped = (
            subset.groupby("conf_bin")
            .agg(
                mean_conf=("relevance_confidence", "mean"),
                accuracy=("is_correct", "mean"),
                count=("doc_id", "count"),
            )
            .reset_index()
        )

        plt.plot(
            grouped["mean_conf"],
            grouped["accuracy"],
            "o-",
            label=f"{pred_label}",
            color=colors.get(pred_label),
        )

    plt.xlabel("Predicted Confidence")
    plt.ylabel("Fraction Correct")
    plt.title(f"Calibration Plot {title_suffix}".strip())
    plt.legend()
    plt.grid(True)
    plt.savefig(path)
    plt.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Process screening evaluation outputs."
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        default=None,
        help="Path to a specific results directory. Defaults to the latest run.",
    )
    args = parser.parse_args()
    process_results(args.results_dir)
