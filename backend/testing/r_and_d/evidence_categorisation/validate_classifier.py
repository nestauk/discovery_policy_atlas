"""
Validation script for evidence categorization classifier.

Compares LLM predictions against human-labeled ground truth and calculates
comprehensive performance metrics.
"""

import json
import pandas as pd
from pathlib import Path
import logging
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix,
)
from typing import Dict, Tuple

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


EVIDENCE_CATEGORIES = [
    "Systematic Review and Meta-Analysis",
    "RCTs and Quasi-Experimental Studies",
    "Observational Research Studies",
    "Modelling & Simulation",
    "Policy Syntheses & Guidance Documents",
    "Qualitative & Contextual Evidence",
    "Expert Opinion and Commentary",
    "Other (Non-evidence documents)",
    "Unknown / Insufficient information",
]


def load_validation_data(
    validation_csv: str, predictions_csv: str
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load validation ground truth and classifier predictions.

    Args:
        validation_csv: Path to CSV with ground_truth_category
        predictions_csv: Path to CSV with classifier predictions (evidence_category)

    Returns:
        Tuple of (validation_df, predictions_df)
    """
    logger.info(f"Loading validation data from {validation_csv}")
    validation_df = pd.read_csv(validation_csv)

    logger.info(f"Loading predictions from {predictions_csv}")
    predictions_df = pd.read_csv(predictions_csv)

    # Check required columns
    if "ground_truth_category" not in validation_df.columns:
        raise ValueError("validation_csv must have 'ground_truth_category' column")

    if "evidence_category" not in predictions_df.columns:
        raise ValueError("predictions_csv must have 'evidence_category' column")

    logger.info(f"Loaded {len(validation_df)} validation records")
    logger.info(f"Loaded {len(predictions_df)} predictions")

    return validation_df, predictions_df


def merge_predictions_with_ground_truth(
    validation_df: pd.DataFrame, predictions_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge predictions with ground truth based on title and abstract.

    Args:
        validation_df: DataFrame with ground truth labels
        predictions_df: DataFrame with predictions

    Returns:
        Merged DataFrame with both ground truth and predictions
    """
    # Merge on title (assuming titles are unique)
    # If titles aren't unique, could merge on title + first 100 chars of abstract
    merged = validation_df.merge(
        predictions_df[
            ["title", "evidence_category", "evidence_confidence", "category_reasoning"]
        ],
        on="title",
        how="left",
        suffixes=("_ground_truth", "_predicted"),
    )

    # Drop rows where prediction is missing
    missing_predictions = merged["evidence_category"].isna().sum()
    if missing_predictions > 0:
        logger.warning(
            f"{missing_predictions} validation records don't have predictions (will be excluded)"
        )
        merged = merged.dropna(subset=["evidence_category"])

    logger.info(f"Successfully matched {len(merged)} records")

    return merged


def calculate_overall_metrics(y_true: pd.Series, y_pred: pd.Series) -> Dict[str, float]:
    """
    Calculate overall classification metrics.

    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels

    Returns:
        Dictionary of metrics
    """
    metrics = {}

    # Overall accuracy
    metrics["accuracy"] = accuracy_score(y_true, y_pred)

    # Macro and weighted averages
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    metrics["macro_precision"] = precision
    metrics["macro_recall"] = recall
    metrics["macro_f1"] = f1

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    metrics["weighted_precision"] = precision
    metrics["weighted_recall"] = recall
    metrics["weighted_f1"] = f1

    return metrics


def print_classification_report(y_true: pd.Series, y_pred: pd.Series) -> str:
    """
    Generate detailed classification report.

    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels

    Returns:
        Classification report as string
    """
    # Get labels that actually appear in the data
    labels = sorted(set(y_true) | set(y_pred))

    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=labels,
        zero_division=0,
        digits=3,
    )

    return report


def analyze_confusion_matrix(y_true: pd.Series, y_pred: pd.Series) -> pd.DataFrame:
    """
    Create confusion matrix as DataFrame for easy analysis.

    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels

    Returns:
        Confusion matrix as DataFrame
    """
    # Get labels that actually appear in the data
    labels = sorted(set(y_true) | set(y_pred))

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    cm_df = pd.DataFrame(cm, index=labels, columns=labels)

    return cm_df


def analyze_confidence_by_correctness(merged_df: pd.DataFrame) -> Dict:
    """
    Analyze how confidence scores correlate with correctness.

    Args:
        merged_df: DataFrame with both predictions and ground truth

    Returns:
        Dictionary with confidence analysis
    """
    merged_df["correct"] = (
        merged_df["ground_truth_category"] == merged_df["evidence_category"]
    )

    analysis = {
        "correct_mean_confidence": merged_df[merged_df["correct"]][
            "evidence_confidence"
        ].mean(),
        "incorrect_mean_confidence": merged_df[~merged_df["correct"]][
            "evidence_confidence"
        ].mean(),
        "correct_count": merged_df["correct"].sum(),
        "incorrect_count": (~merged_df["correct"]).sum(),
    }

    return analysis


def analyze_disagreements(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze cases where classifier disagreed with ground truth.

    Args:
        merged_df: DataFrame with both predictions and ground truth

    Returns:
        DataFrame with disagreement analysis
    """
    disagreements = merged_df[
        merged_df["ground_truth_category"] != merged_df["evidence_category"]
    ].copy()

    if len(disagreements) == 0:
        logger.info("No disagreements found - perfect accuracy!")
        return pd.DataFrame()

    # Select relevant columns
    disagreement_cols = [
        "title",
        "ground_truth_category",
        "evidence_category",
        "evidence_confidence",
        "annotator_confidence",
        "category_reasoning",
        "difficulty",
    ]

    available_cols = [col for col in disagreement_cols if col in disagreements.columns]
    disagreements_analysis = disagreements[available_cols]

    return disagreements_analysis


def analyze_by_difficulty(merged_df: pd.DataFrame) -> Dict:
    """
    Analyze performance by labeling difficulty.

    Args:
        merged_df: DataFrame with both predictions and ground truth

    Returns:
        Dictionary with difficulty analysis
    """
    if "difficulty" not in merged_df.columns or merged_df["difficulty"].isna().all():
        return {"error": "No difficulty ratings available"}

    merged_df["correct"] = (
        merged_df["ground_truth_category"] == merged_df["evidence_category"]
    )

    difficulty_analysis = {}

    for difficulty in merged_df["difficulty"].dropna().unique():
        subset = merged_df[merged_df["difficulty"] == difficulty]
        if len(subset) > 0:
            difficulty_analysis[difficulty] = {
                "count": len(subset),
                "accuracy": subset["correct"].mean(),
            }

    return difficulty_analysis


def main(
    validation_csv: str = "inputs/validation_set.csv",
    predictions_csv: str = "outputs/validation_results.csv",
    output_report: str = "outputs/validation_report.txt",
    output_disagreements: str = "outputs/disagreements.csv",
):
    """
    Main validation function.

    Args:
        validation_csv: Path to ground truth labels
        predictions_csv: Path to classifier predictions
        output_report: Path to save text report
        output_disagreements: Path to save disagreement analysis
    """
    logger.info("=" * 60)
    logger.info("Evidence Categorization Classifier Validation")
    logger.info("=" * 60)

    # Load data
    validation_df, predictions_df = load_validation_data(
        validation_csv, predictions_csv
    )

    # Merge predictions with ground truth
    merged_df = merge_predictions_with_ground_truth(validation_df, predictions_df)

    if len(merged_df) == 0:
        logger.error("No matching records found between validation and predictions!")
        return

    # Extract labels
    y_true = merged_df["ground_truth_category"]
    y_pred = merged_df["evidence_category"]

    # Calculate overall metrics
    logger.info("\n" + "=" * 60)
    logger.info("OVERALL METRICS")
    logger.info("=" * 60)

    metrics = calculate_overall_metrics(y_true, y_pred)

    for metric, value in metrics.items():
        logger.info(f"{metric}: {value:.3f}")

    # Print classification report
    logger.info("\n" + "=" * 60)
    logger.info("DETAILED CLASSIFICATION REPORT")
    logger.info("=" * 60)

    report = print_classification_report(y_true, y_pred)
    logger.info("\n" + report)

    # Confusion matrix
    logger.info("\n" + "=" * 60)
    logger.info("CONFUSION MATRIX")
    logger.info("=" * 60)
    logger.info("(Rows = Ground Truth, Columns = Predictions)\n")

    cm_df = analyze_confusion_matrix(y_true, y_pred)
    logger.info(cm_df.to_string())

    # Confidence analysis
    logger.info("\n" + "=" * 60)
    logger.info("CONFIDENCE ANALYSIS")
    logger.info("=" * 60)

    confidence_analysis = analyze_confidence_by_correctness(merged_df)
    logger.info(
        f"Correct predictions - Mean confidence: {confidence_analysis['correct_mean_confidence']:.2f}"
    )
    logger.info(
        f"Incorrect predictions - Mean confidence: {confidence_analysis['incorrect_mean_confidence']:.2f}"
    )
    logger.info(f"Correct count: {confidence_analysis['correct_count']}")
    logger.info(f"Incorrect count: {confidence_analysis['incorrect_count']}")

    # Difficulty analysis
    if "difficulty" in merged_df.columns:
        logger.info("\n" + "=" * 60)
        logger.info("PERFORMANCE BY DIFFICULTY")
        logger.info("=" * 60)

        difficulty_analysis = analyze_by_difficulty(merged_df)
        if "error" not in difficulty_analysis:
            for difficulty, stats in difficulty_analysis.items():
                logger.info(
                    f"{difficulty}: {stats['accuracy']:.1%} accuracy ({stats['count']} samples)"
                )
        else:
            logger.info(difficulty_analysis["error"])

    # Disagreement analysis
    logger.info("\n" + "=" * 60)
    logger.info("DISAGREEMENT ANALYSIS")
    logger.info("=" * 60)

    disagreements = analyze_disagreements(merged_df)

    if len(disagreements) > 0:
        logger.info(f"\nFound {len(disagreements)} disagreements")
        logger.info(f"Saving detailed disagreement analysis to: {output_disagreements}")

        # Save disagreements
        output_path = Path(output_disagreements)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        disagreements.to_csv(output_path, index=False)

        # Show top disagreements by confidence
        logger.info("\nTop 5 high-confidence disagreements:")
        top_disagreements = disagreements.nlargest(5, "evidence_confidence")[
            [
                "title",
                "ground_truth_category",
                "evidence_category",
                "evidence_confidence",
            ]
        ]
        logger.info("\n" + top_disagreements.to_string(index=False))
    else:
        logger.info("Perfect accuracy - no disagreements!")

    # Save full report
    logger.info("\n" + "=" * 60)
    logger.info(f"Saving full report to: {output_report}")
    logger.info("=" * 60)

    # Generate report content
    report_lines = [
        "Evidence Categorization Classifier Validation Report",
        "=" * 60,
        "",
        "OVERALL METRICS",
        "-" * 60,
    ]

    for metric, value in metrics.items():
        report_lines.append(f"{metric}: {value:.3f}")

    report_lines.extend(
        [
            "",
            "DETAILED CLASSIFICATION REPORT",
            "-" * 60,
            report,
            "",
            "CONFUSION MATRIX",
            "-" * 60,
            "(Rows = Ground Truth, Columns = Predictions)",
            "",
            cm_df.to_string(),
            "",
            "CONFIDENCE ANALYSIS",
            "-" * 60,
            f"Correct predictions - Mean confidence: {confidence_analysis['correct_mean_confidence']:.2f}",
            f"Incorrect predictions - Mean confidence: {confidence_analysis['incorrect_mean_confidence']:.2f}",
            f"Correct count: {confidence_analysis['correct_count']}",
            f"Incorrect count: {confidence_analysis['incorrect_count']}",
        ]
    )

    # Save report
    output_path = Path(output_report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(report_lines))

    # Save metrics as JSON for programmatic access
    metrics_json = {
        **metrics,
        "confidence_correct": confidence_analysis["correct_mean_confidence"],
        "confidence_incorrect": confidence_analysis["incorrect_mean_confidence"],
        "correct_count": confidence_analysis["correct_count"],
        "incorrect_count": confidence_analysis["incorrect_count"],
    }
    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(metrics_json, indent=2))
    logger.info(f"Metrics saved to: {json_path}")

    logger.info("\n✓ Validation complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate evidence categorization classifier against human labels"
    )
    parser.add_argument(
        "--validation",
        default="inputs/validation_set.csv",
        help="Path to validation set with ground truth labels",
    )
    parser.add_argument(
        "--predictions",
        default="outputs/categorised_evidence_run1_gpt5.csv",
        help="Path to classifier predictions",
    )
    parser.add_argument(
        "--output-report",
        default="outputs/validation_report.txt",
        help="Path to save validation report",
    )
    parser.add_argument(
        "--output-disagreements",
        default="outputs/disagreements.csv",
        help="Path to save disagreement analysis",
    )

    args = parser.parse_args()

    main(
        validation_csv=args.validation,
        predictions_csv=args.predictions,
        output_report=args.output_report,
        output_disagreements=args.output_disagreements,
    )
