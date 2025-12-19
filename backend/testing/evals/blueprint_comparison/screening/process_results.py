#!/usr/bin/env python3
"""
Summarise blueprint screening evaluation outputs and generate overview plots.

The script scans each topic directory under ./results, reads the
`screening_metrics.json` file produced by `evaluate_screening.py`, and aggregates
the per-topic statistics. Outputs include:

* `summary/topics_summary.csv` – table of coverage/accuracy means + variances
* `summary/overall_summary.json` – high-level roll-up across topics
* Bar charts for coverage and accuracy (with variance-derived error bars)
* Scatter plot comparing title vs full-text accuracy
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent / "results"


@dataclass
class TopicSummary:
    topic: str
    runs_requested: Optional[int]
    runs_completed: Optional[int]
    coverage_total: Optional[int]
    coverage_mean: Optional[float]
    coverage_var: Optional[float]
    title_metrics: Dict[str, Optional[float]]
    full_metrics: Dict[str, Optional[float]]

    @property
    def coverage_pct(self) -> Optional[float]:
        if self.coverage_total and self.coverage_mean is not None:
            return (self.coverage_mean / self.coverage_total) * 100.0
        return None


def load_topic_summary(topic_dir: Path) -> Optional[TopicSummary]:
    metrics_path = topic_dir / "screening_metrics.json"
    if not metrics_path.exists():
        logger.warning("Skipping %s (missing screening_metrics.json)", topic_dir)
        return None

    with metrics_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    agg = data.get("aggregate") or {}
    coverage = agg.get("coverage") or {}
    title_agg = agg.get("title_abstract")
    full_agg = agg.get("full_text")

    def extract_stage(stage: Optional[Dict]) -> Dict[str, Optional[float]]:
        if not stage:
            return {
                "accuracy_mean": None,
                "accuracy_var": None,
                "precision_mean": None,
                "precision_var": None,
                "recall_mean": None,
                "recall_var": None,
                "specificity_mean": None,
                "specificity_var": None,
                "f1_mean": None,
                "f1_var": None,
                "tp_mean": None,
                "tn_mean": None,
                "fp_mean": None,
                "fn_mean": None,
                "tp_var": None,
                "tn_var": None,
                "fp_var": None,
                "fn_var": None,
            }
        mean = stage.get("mean") or {}
        var = stage.get("variance") or {}
        return {
            "accuracy_mean": mean.get("accuracy"),
            "accuracy_var": var.get("accuracy"),
            "precision_mean": mean.get("precision"),
            "precision_var": var.get("precision"),
            "recall_mean": mean.get("recall"),
            "recall_var": var.get("recall"),
            "specificity_mean": mean.get("specificity"),
            "specificity_var": var.get("specificity"),
            "f1_mean": mean.get("f1"),
            "f1_var": var.get("f1"),
            "tp_mean": mean.get("tp"),
            "tn_mean": mean.get("tn"),
            "fp_mean": mean.get("fp"),
            "fn_mean": mean.get("fn"),
            "tp_var": var.get("tp"),
            "tn_var": var.get("tn"),
            "fp_var": var.get("fp"),
            "fn_var": var.get("fn"),
        }

    return TopicSummary(
        topic=topic_dir.name.replace("_", " "),
        runs_requested=agg.get("runs_requested"),
        runs_completed=agg.get("runs_completed"),
        coverage_total=coverage.get("total"),
        coverage_mean=coverage.get("found_mean"),
        coverage_var=coverage.get("found_variance"),
        title_metrics=extract_stage(title_agg),
        full_metrics=extract_stage(full_agg),
    )


def build_dataframe(summaries: List[TopicSummary]) -> pd.DataFrame:
    records = []
    for summary in summaries:
        records.append(
            {
                "topic": summary.topic,
                "runs_requested": summary.runs_requested,
                "runs_completed": summary.runs_completed,
                "coverage_total": summary.coverage_total,
                "coverage_mean": summary.coverage_mean,
                "coverage_variance": summary.coverage_var,
                "coverage_pct": summary.coverage_pct,
                "title_accuracy_mean": summary.title_metrics.get("accuracy_mean"),
                "title_accuracy_var": summary.title_metrics.get("accuracy_var"),
                "title_precision_mean": summary.title_metrics.get("precision_mean"),
                "title_precision_var": summary.title_metrics.get("precision_var"),
                "title_recall_mean": summary.title_metrics.get("recall_mean"),
                "title_recall_var": summary.title_metrics.get("recall_var"),
                "title_tp_mean": summary.title_metrics.get("tp_mean"),
                "title_tn_mean": summary.title_metrics.get("tn_mean"),
                "title_fp_mean": summary.title_metrics.get("fp_mean"),
                "title_fn_mean": summary.title_metrics.get("fn_mean"),
                "full_accuracy_mean": summary.full_metrics.get("accuracy_mean"),
                "full_accuracy_var": summary.full_metrics.get("accuracy_var"),
                "full_precision_mean": summary.full_metrics.get("precision_mean"),
                "full_precision_var": summary.full_metrics.get("precision_var"),
                "full_recall_mean": summary.full_metrics.get("recall_mean"),
                "full_recall_var": summary.full_metrics.get("recall_var"),
                "full_tp_mean": summary.full_metrics.get("tp_mean"),
                "full_tn_mean": summary.full_metrics.get("tn_mean"),
                "full_fp_mean": summary.full_metrics.get("fp_mean"),
                "full_fn_mean": summary.full_metrics.get("fn_mean"),
            }
        )
    return pd.DataFrame(records)


def overall_summary(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    def safe_sum(series_name: str) -> Optional[float]:
        if series_name not in df.columns:
            return None
        series = df[series_name].dropna()
        return float(series.sum()) if not series.empty else None

    def safe_mean(series_name: str, scale: float = 1.0) -> Optional[float]:
        if series_name not in df.columns:
            return None
        series = df[series_name].dropna()
        if series.empty:
            return None
        return float(series.mean()) / scale

    total_docs = safe_sum("coverage_total")
    total_tp = safe_sum("title_tp_mean")
    total_fp = safe_sum("title_fp_mean")
    total_fn = safe_sum("title_fn_mean")
    total_tn = safe_sum("title_tn_mean")

    return {
        "num_targets": int(df.shape[0]),
        "total_documents": int(total_docs) if total_docs is not None else None,
        "total_tp": int(round(total_tp)) if total_tp is not None else None,
        "total_fp": int(round(total_fp)) if total_fp is not None else None,
        "total_fn": int(round(total_fn)) if total_fn is not None else None,
        "total_tn": int(round(total_tn)) if total_tn is not None else None,
        "mean_recall": safe_mean("title_recall_mean", scale=100.0),
        "mean_precision": safe_mean("title_precision_mean", scale=100.0),
        "mean_title_accuracy": safe_mean("title_accuracy_mean", scale=100.0),
        "mean_full_accuracy": safe_mean("full_accuracy_mean", scale=100.0),
        "mean_wss_95": None,
        "mean_f_beta_2": None,
        "mean_avg_conf_tp": None,
        "mean_avg_conf_tn": None,
        "mean_avg_conf_fp": None,
        "mean_avg_conf_fn": None,
    }


def _std_from_var(value: Optional[float]) -> Optional[float]:
    return math.sqrt(value) if value is not None and value >= 0 else None


def plot_bars(df: pd.DataFrame, output_dir: Path) -> None:
    sns.set_theme(style="whitegrid")
    output_dir.mkdir(parents=True, exist_ok=True)

    def _plot(field_mean: str, field_var: str, title: str, filename: str):
        data = df[["topic", field_mean, field_var]].dropna(subset=[field_mean])
        if data.empty:
            logger.warning("Skipping %s plot (no data)", title)
            return
        data = data.copy()
        data["error"] = data[field_var].apply(_std_from_var)

        plt.figure(figsize=(12, max(4, len(data) * 0.35)))
        ax = sns.barplot(
            data=data,
            y="topic",
            x=field_mean,
            orient="h",
            color="#1f77b4",
            errorbar=None,
        )
        for i, (_, row) in enumerate(data.iterrows()):
            err = row["error"]
            if err and not math.isnan(err):
                ax.errorbar(
                    row[field_mean],
                    i,
                    xerr=err,
                    fmt="",
                    color="#333333",
                    capsize=4,
                    linewidth=1,
                )

        ax.set_title(title)
        ax.set_xlabel("Percentage")
        ax.set_ylabel("")
        plt.tight_layout()
        plt.savefig(output_dir / filename)
        plt.close()

    _plot(
        "coverage_pct", "coverage_variance", "Coverage (mean ± σ)", "coverage_bar.png"
    )
    _plot(
        "title_recall_mean",
        "title_recall_var",
        "Title/Abstract recall (mean ± σ)",
        "title_recall_bar.png",
    )
    _plot(
        "full_recall_mean",
        "full_recall_var",
        "Full-text recall (mean ± σ)",
        "full_recall_bar.png",
    )


def plot_scatter(df: pd.DataFrame, output_dir: Path) -> None:
    scatter_df = df.dropna(subset=["title_recall_mean", "full_recall_mean"])
    if scatter_df.empty:
        logger.warning("Skipping scatter plot (missing accuracy data).")
        return

    plt.figure(figsize=(8, 6))
    sns.scatterplot(
        data=scatter_df,
        x="title_recall_mean",
        y="full_recall_mean",
        hue="coverage_pct",
        palette="viridis",
        s=80,
    )
    for _, row in scatter_df.iterrows():
        plt.text(
            row["title_recall_mean"],
            row["full_recall_mean"],
            row["topic"],
            fontsize=8,
            ha="left",
            va="bottom",
        )
    plt.xlabel("Title/Abstract recall (mean %)")
    plt.ylabel("Full-text recall (mean %)")
    plt.title("Recall comparison across topics")
    plt.legend(title="Coverage (%)", loc="best")
    plt.tight_layout()
    plt.savefig(output_dir / "accuracy_scatter.png")
    plt.close()


def process_results(results_root: Optional[Path] = None) -> None:
    results_root = Path(results_root) if results_root else DEFAULT_RESULTS_ROOT
    if not results_root.exists():
        raise FileNotFoundError(f"Results directory not found: {results_root}")

    topic_dirs = [
        path
        for path in sorted(results_root.iterdir())
        if path.is_dir() and (path / "screening_metrics.json").exists()
    ]
    if not topic_dirs:
        raise RuntimeError(f"No topic results found under {results_root}")

    summaries = [load_topic_summary(path) for path in topic_dirs]
    summaries = [s for s in summaries if s]
    if not summaries:
        raise RuntimeError("No valid screening metrics found.")

    df = build_dataframe(summaries)
    summary_dir = results_root / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    csv_path = summary_dir / "topics_summary.csv"
    df.sort_values("topic").to_csv(csv_path, index=False)
    logger.info("Wrote topic summary table to %s", csv_path)

    overall = overall_summary(df)
    overall_path = summary_dir / "overall_summary.json"
    overall_path.write_text(json.dumps(overall, indent=2))
    logger.info("Wrote overall summary to %s", overall_path)

    plot_bars(df, summary_dir)
    plot_scatter(df, summary_dir)
    logger.info("Charts saved in %s", summary_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarise blueprint screening results and plot aggregates."
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
        help="Path to the screening results directory (defaults to ./results next to this script).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    process_results(Path(args.results_dir) if args.results_dir else None)


if __name__ == "__main__":
    main()
