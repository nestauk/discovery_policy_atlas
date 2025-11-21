"""Generate experiment charts for individual questions and prompt summaries.

This script generates various visualizations including:
- Individual question metrics (retrieved totals, F1 scores, etc.)
- Prompt-level summaries aggregating across questions
- Optional combined runs analysis comparing single-run vs multi-run performance

Usage (run from backend directory):
    cd backend
    
    # Default experiment (experiment1) with 3 questions, using config.yaml:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py
    
    # Custom experiment name:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment2
    
    # Specify number of questions (identifiers) to plot:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --n-questions 10
    
    # Use alternate config file:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --config config_2.yaml
    
    # Combine runs (deduplicate across multiple runs):
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --combine-runs
    
    # Generate comparison charts between single and combined runs:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --compare-combined-runs
"""

import argparse
import pandas as pd
import altair as alt
import yaml
import numpy as np
from pathlib import Path
from testing import TESTING_DIR, logger
from testing.r_and_d.boolean_queries.query_tester import get_question_id

# Paths
BOOL_DIR = TESTING_DIR / "r_and_d/boolean_queries/outputs/"


def process_results(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Process experiment results.

    More specifically, it adds the following columns:
    - identifier: the question ID
    - identifier_no: the question number
    - model_temp: the model name and temperature

    And changes gpt-5 model temperatures to empty string.
    """
    is_gpt5 = df["model"].str.contains("gpt-5")
    return (
        df.assign(identifier=lambda df: df["question"].apply(get_question_id))
        .assign(
            identifier_no=lambda df: df["identifier"].str.extract(r"(\d+)").astype(int)
        )
        .assign(
            model=lambda df: pd.Categorical(
                df["model"], categories=config["models"], ordered=True
            )
        )
        .assign(temperature=lambda df: df["temperature"].where(~is_gpt5, ""))
        .assign(
            **{
                "model_temp": lambda df: df["model"]
                .astype(str)
                .where(
                    is_gpt5,
                    df["model"].astype(str) + " temp=" + df["temperature"].astype(str),
                )
            }
        )
    )


def get_precision(baseline_set: list[str], retrieved_set: list[str]) -> float:
    return (
        len(set(baseline_set) & set(retrieved_set)) / len(set(retrieved_set))
        if retrieved_set
        else 0
    )


def get_recall(baseline_set: list[str], retrieved_set: list[str]) -> float:
    return (
        len(set(baseline_set) & set(retrieved_set)) / len(set(baseline_set))
        if baseline_set
        else 0
    )


def get_topn_recall_precision(
    baseline_set: list[str], retrieved_set: list[str], n: int
) -> tuple[float, float]:
    n = len(retrieved_set)
    topn_baseline_set = baseline_set[:n]
    recall = get_recall(topn_baseline_set, retrieved_set)
    precision = get_precision(topn_baseline_set, retrieved_set)
    return recall, precision


def get_metrics(
    baseline_set: list[str], retrieved_set: list[str]
) -> tuple[float, float, float, float, float]:
    precision = get_precision(baseline_set, retrieved_set)
    recall = get_recall(baseline_set, retrieved_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    topn_recall, topn_precision = get_topn_recall_precision(
        baseline_set, retrieved_set, 10
    )
    return precision, recall, f1, topn_recall, topn_precision


def combine_runs(
    df: pd.DataFrame, max_runs: int = 5, random_seed: int = 42
) -> pd.DataFrame:
    """Combine and deduplicate results across multiple runs.

    For each unique combination of (identifier, model, temperature, prompt),
    combines the results_id lists from all runs (or random sample if > max_runs).

    Args:
        df: DataFrame with columns including identifier, model, temperature, prompt, results_id
        max_runs: Maximum number of runs to combine (randomly sampled if more exist)
        random_seed: Random seed for reproducibility

    Returns:
        DataFrame with combined results, one row per (identifier, model, temperature, prompt)
    """
    np.random.seed(random_seed)

    combined_results = []
    group_cols = ["identifier", "model", "temperature", "prompt", "model_temp"]

    for group_key, group_df in df.groupby(group_cols):
        # If more than max_runs, randomly sample
        if len(group_df) > max_runs:
            group_df = group_df.sample(n=max_runs, random_state=random_seed)

        # Combine and deduplicate result IDs
        all_results = []
        for results_id in group_df["results_id"]:
            if isinstance(results_id, list):
                all_results.extend(results_id)

        combined_results_id = list(set(all_results))  # Deduplicate

        # Create combined row
        combined_row = {
            "identifier": group_key[0],
            "model": group_key[1],
            "temperature": group_key[2],
            "prompt": group_key[3],
            "model_temp": group_key[4],
            "results_id": combined_results_id,
            "n_runs_combined": len(group_df),
            "n_elements": len(combined_results_id),
            "retrieved_total": len(combined_results_id),
            "question": group_df.iloc[0]["question"],
            "identifier_no": group_df.iloc[0]["identifier_no"],
        }
        combined_results.append(combined_row)

    return pd.DataFrame(combined_results)


def plot_individual_question(
    analysis_df: pd.DataFrame,
    reference: str,
    outputs_dir: Path,
    model_temps: list,
    skip_ranges: bool = False,
):
    """Generate charts for a single question.

    Args:
        analysis_df: DataFrame containing the experiment results for a single question. The columns include:
            - model: the model name
            - temperature: the temperature
            - retrieved_total: the total number of retrieved elements
            - model_temp: the model name and temperature
        reference: the question ID
        outputs_dir: the directory to save the charts
        model_temps: the model temperatures to include in the charts
        skip_ranges: if True, skip charts with IQR/ranges (for combined runs with single values)
    """
    logger.info(f"  Plotting question: {reference}")

    # Chart 1: Retrieved total horizontal (scatter)
    fig = (
        alt.Chart(
            analysis_df[["model", "temperature", "retrieved_total", "model_temp"]]
        )
        .mark_point(size=60, opacity=0.7)
        .encode(
            x=alt.X(
                "model_temp:N",
                title="Model",
                sort=model_temps,
                axis=alt.Axis(labelAngle=-45),
            ),
            y=alt.Y(
                "retrieved_total:Q",
                title="Retrieved Total",
                scale=alt.Scale(domain=[0, 5000], clamp=True),
            ),
            color=alt.Color(
                "temperature:Q",
                title="Temperature",
                scale=alt.Scale(scheme="orangered"),
            ),
        )
    )
    fig.save(
        str(outputs_dir / f"retrieved_total_horizontal_{reference}.png"), scale_factor=2
    )

    if skip_ranges:
        return

    # Chart 2: Retrieved total median with IQR
    base = alt.Chart(
        analysis_df[["model", "temperature", "retrieved_total", "model_temp"]]
    )

    points = base.mark_circle(size=60, opacity=1).encode(
        x=alt.X(
            "model_temp:N",
            title="Model",
            sort=model_temps,
            axis=alt.Axis(labelAngle=-45),
        ),
        y=alt.Y(
            "median(retrieved_total):Q",
            title="Retrieved Total",
            scale=alt.Scale(domain=[0, 1000], clamp=True),
        ),
        color=alt.Color(
            "temperature:Q", title="Temperature", scale=alt.Scale(scheme="orangered")
        ),
    )

    error_bars = base.mark_errorbar(extent="iqr").encode(
        x=alt.X("model_temp:N", sort=model_temps, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("retrieved_total:Q", scale=alt.Scale(domain=[0, 5000], clamp=True)),
        color=alt.Color("temperature:Q", scale=alt.Scale(scheme="orangered")),
    )

    fig = error_bars + points
    fig.save(
        str(outputs_dir / f"retrieved_total_median_iqr_{reference}.png"), scale_factor=2
    )

    # Chart 3: Temperature vs retrieved total (excluding GPT-5)
    exclude_models = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]  # noqa: F841
    mean_temp = (
        analysis_df.query("model not in @exclude_models")
        .groupby(["temperature"])
        .agg(
            retrieved_total_median=("retrieved_total", "median"),
            retrieved_total_q1=("retrieved_total", lambda x: x.quantile(0.25)),
            retrieved_total_q3=("retrieved_total", lambda x: x.quantile(0.75)),
        )
        .reset_index()
        .sort_values(["temperature"])
    )

    base = alt.Chart(mean_temp)

    points = base.mark_circle(size=60, opacity=1, color="red").encode(
        x=alt.X("temperature:Q", title="Temperature"),
        y=alt.Y("retrieved_total_median:Q", title="Retrieved Total"),
    )

    error_bars = base.mark_errorbar(color="red").encode(
        x=alt.X("temperature:Q"),
        y=alt.Y("retrieved_total_q1:Q", title=""),
        y2=alt.Y2("retrieved_total_q3:Q"),
    )

    fig = error_bars + points
    fig = fig.properties(
        width=200, height=200, title="Temperature vs Retrieved Total (Median + IQR)"
    )
    fig.save(
        str(outputs_dir / f"retrieved_total_temperature_median_iqr_{reference}.png"),
        scale_factor=2,
    )


def plot_individual_question_with_metrics(
    metrics_df: pd.DataFrame,
    reference: str,
    outputs_dir: Path,
    model_temps: list,
    skip_ranges: bool = False,
):
    """Generate metric charts for a single question.

    Args:
        metrics_df: DataFrame with metrics for the question
        reference: the question ID
        outputs_dir: the directory to save the charts
        model_temps: the model temperatures to include in the charts
        skip_ranges: if True, skip charts with IQR/ranges (for combined runs with single values)
    """
    if skip_ranges:
        return
    # Chart 4: F1 median with IQR
    base = alt.Chart(metrics_df[["model", "temperature", "f1", "model_temp"]])

    points = base.mark_circle(size=60, opacity=1).encode(
        x=alt.X(
            "model_temp:N",
            title="Model",
            sort=model_temps,
            axis=alt.Axis(labelAngle=-45),
        ),
        y=alt.Y("median(f1):Q", title="F1"),
        color=alt.Color(
            "temperature:Q", title="Temperature", scale=alt.Scale(scheme="orangered")
        ),
    )

    error_bars = base.mark_errorbar(extent="iqr").encode(
        x=alt.X("model_temp:N", sort=model_temps, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("f1:Q", title="F1"),
        color=alt.Color("temperature:Q", scale=alt.Scale(scheme="orangered")),
    )

    fig = error_bars + points
    fig.save(str(outputs_dir / f"f1_median_iqr_{reference}.png"), scale_factor=2)

    # Chart 5: N elements median with IQR
    base = alt.Chart(metrics_df[["model", "temperature", "n_elements", "model_temp"]])

    points = base.mark_circle(size=60, opacity=1).encode(
        x=alt.X(
            "model_temp:N",
            title="Model",
            sort=model_temps,
            axis=alt.Axis(labelAngle=-45),
        ),
        y=alt.Y("median(n_elements):Q", title="No of elements"),
        color=alt.Color(
            "temperature:Q", title="Temperature", scale=alt.Scale(scheme="orangered")
        ),
    )

    error_bars = base.mark_errorbar(extent="iqr").encode(
        x=alt.X("model_temp:N", sort=model_temps, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("n_elements:Q", title="No of elements"),
        color=alt.Color("temperature:Q", scale=alt.Scale(scheme="orangered")),
    )

    fig = error_bars + points
    fig.save(str(outputs_dir / f"elements_median_iqr_{reference}.png"), scale_factor=2)


def plot_combined_vs_single_comparison(
    single_run_df: pd.DataFrame,
    combined_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    outputs_dir: Path,
    model_temps: list,
):
    """Compare single-run vs combined-runs metrics.

    Args:
        single_run_df: Original DataFrame with individual runs
        combined_df: DataFrame with combined and deduplicated runs
        baseline_df: Baseline results for computing metrics
        outputs_dir: Directory to save charts
        model_temps: List of model-temperature combinations for sorting
    """
    logger.info("  Plotting combined vs single-run comparison")

    # Prepare baseline lookup
    baseline_lookup = {}
    for _, row in baseline_df.iterrows():
        baseline_lookup[row["identifier"]] = row.get("results_id")

    # Compute metrics for single runs
    single_metrics = []
    for _, row in single_run_df.iterrows():
        baseline_ids = baseline_lookup.get(row["identifier"])
        results_id = row.get("results_id")
        if not isinstance(results_id, list):
            results_id = []

        if baseline_ids and isinstance(baseline_ids, list):
            precision, recall, f1, _, _ = get_metrics(baseline_ids, results_id)
            single_metrics.append(
                {
                    "identifier": row["identifier"],
                    "model_temp": row["model_temp"],
                    "temperature": row["temperature"],
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "n_elements": len(results_id) if results_id else 0,
                    "run_type": "single",
                }
            )

    single_metrics_df = pd.DataFrame(single_metrics)

    # Compute metrics for combined runs
    combined_metrics = []
    for _, row in combined_df.iterrows():
        baseline_ids = baseline_lookup.get(row["identifier"])
        results_id = row.get("results_id")
        if not isinstance(results_id, list):
            results_id = []

        if baseline_ids and isinstance(baseline_ids, list):
            precision, recall, f1, _, _ = get_metrics(baseline_ids, results_id)
            combined_metrics.append(
                {
                    "identifier": row["identifier"],
                    "model_temp": row["model_temp"],
                    "temperature": row["temperature"],
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "n_elements": len(results_id) if results_id else 0,
                    "n_runs_combined": row["n_runs_combined"],
                    "run_type": "combined",
                }
            )

    combined_metrics_df = pd.DataFrame(combined_metrics)

    # Aggregate metrics by model_temp
    single_agg = (
        single_metrics_df.groupby("model_temp")
        .agg(
            f1_mean=("f1", "mean"),
            f1_median=("f1", "median"),
            precision_mean=("precision", "mean"),
            recall_mean=("recall", "mean"),
            n_elements_mean=("n_elements", "mean"),
            temperature=("temperature", "first"),
        )
        .reset_index()
        .assign(run_type="single")
    )

    combined_agg = (
        combined_metrics_df.groupby("model_temp")
        .agg(
            f1_mean=("f1", "mean"),
            f1_median=("f1", "median"),
            precision_mean=("precision", "mean"),
            recall_mean=("recall", "mean"),
            n_elements_mean=("n_elements", "mean"),
            n_runs_combined_mean=("n_runs_combined", "mean"),
            temperature=("temperature", "first"),
        )
        .reset_index()
        .assign(run_type="combined")
    )

    comparison_df = pd.concat([single_agg, combined_agg], ignore_index=True)

    # Save comparison metrics
    comparison_df.to_csv(outputs_dir / "combined_vs_single_metrics.csv", index=False)
    logger.info("  Saved: combined_vs_single_metrics.csv")

    # Chart 1: F1 comparison by model-temp
    fig = (
        alt.Chart(comparison_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "model_temp:N",
                title="Model-Temperature",
                axis=alt.Axis(labelAngle=-45),
                sort=model_temps,
            ),
            y=alt.Y("f1_mean:Q", title="F1 Score (Mean)"),
            color=alt.Color(
                "run_type:N",
                title="Run Type",
                scale=alt.Scale(
                    domain=["single", "combined"], range=["steelblue", "orange"]
                ),
            ),
            xOffset="run_type:N",
            tooltip=[
                "model_temp:N",
                "run_type:N",
                "f1_mean:Q",
                "precision_mean:Q",
                "recall_mean:Q",
            ],
        )
        .properties(
            width=800,
            height=400,
            title="F1 Score: Single Run vs Combined Runs",
        )
    )
    fig.save(str(outputs_dir / "f1_single_vs_combined.png"), scale_factor=2)

    # Chart 2: Precision and Recall comparison
    comparison_long = pd.melt(
        comparison_df,
        id_vars=["model_temp", "run_type", "temperature"],
        value_vars=["precision_mean", "recall_mean"],
        var_name="metric",
        value_name="score",
    )

    fig = (
        alt.Chart(comparison_long)
        .mark_bar()
        .encode(
            x=alt.X(
                "model_temp:N",
                title="Model-Temperature",
                axis=alt.Axis(labelAngle=-45),
                sort=model_temps,
            ),
            y=alt.Y("score:Q", title="Score"),
            color=alt.Color(
                "run_type:N",
                title="Run Type",
                scale=alt.Scale(
                    domain=["single", "combined"], range=["steelblue", "orange"]
                ),
            ),
            xOffset="run_type:N",
            column=alt.Column("metric:N", title="Metric"),
        )
        .properties(
            width=350, height=400, title="Precision & Recall: Single vs Combined"
        )
    )
    fig.save(
        str(outputs_dir / "precision_recall_single_vs_combined.png"), scale_factor=2
    )

    # Chart 3: N elements comparison
    fig = (
        alt.Chart(comparison_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "model_temp:N",
                title="Model-Temperature",
                axis=alt.Axis(labelAngle=-45),
                sort=model_temps,
            ),
            y=alt.Y("n_elements_mean:Q", title="Number of Elements (Mean)"),
            color=alt.Color(
                "run_type:N",
                title="Run Type",
                scale=alt.Scale(
                    domain=["single", "combined"], range=["steelblue", "orange"]
                ),
            ),
            xOffset="run_type:N",
        )
        .properties(
            width=800,
            height=400,
            title="Number of Retrieved Elements: Single vs Combined",
        )
    )
    fig.save(str(outputs_dir / "n_elements_single_vs_combined.png"), scale_factor=2)


def plot_prompt_analysis(
    llm_filtered: pd.DataFrame,
    baseline_filtered: pd.DataFrame,
    prompt: str,
    outputs_dir: Path,
    model_temps: list,
    skip_ranges: bool = False,
):
    """Generate prompt analysis charts.

    Args:
        llm_filtered: DataFrame with LLM results
        baseline_filtered: DataFrame with baseline results
        prompt: the prompt name
        outputs_dir: the directory to save the charts
        model_temps: the model temperatures to include in the charts
        skip_ranges: if True, skip charts with IQR/ranges (for combined runs with single values)
    """
    logger.info(f"  Plotting prompt analysis: {prompt}")

    # Compute F1 scores with baseline
    baseline_lookup = {}
    for _, row in baseline_filtered.iterrows():
        baseline_lookup[row["identifier"]] = row.get("results_id")

    f1_scores = []
    precision_scores = []
    recall_scores = []

    for _, row in llm_filtered.iterrows():
        baseline_ids = baseline_lookup.get(row["identifier"])
        results_id = row.get("results_id")
        if not isinstance(results_id, list):
            results_id = []

        if results_id is not None and len(results_id) > 0:
            precision, recall, f1, _, _ = get_metrics(baseline_ids, set(results_id))
            f1_scores.append(f1)
            precision_scores.append(precision)
            recall_scores.append(recall)
        else:
            f1_scores.append(0)
            precision_scores.append(0)
            recall_scores.append(0)

    llm_with_metrics = llm_filtered.assign(
        f1=f1_scores, precision=precision_scores, recall=recall_scores
    )

    # Aggregate by model-temperature
    by_model_temp = (
        llm_with_metrics.groupby(["model_temp", "prompt"])
        .agg(
            n_questions=("identifier", "nunique"),
            retrieved_total_mean=("retrieved_total", "mean"),
            retrieved_total_median=("retrieved_total", "median"),
            retrieved_total_q1=("retrieved_total", lambda x: x.quantile(0.25)),
            retrieved_total_q3=("retrieved_total", lambda x: x.quantile(0.75)),
            n_elements_mean=("n_elements", "mean"),
            f1_mean=("f1", "mean"),
            f1_median=("f1", "median"),
            precision_mean=("precision", "mean"),
            recall_mean=("recall", "mean"),
            temperature=("temperature", "first"),
        )
        .reset_index()
        .round(4)
    )

    # Save by_model_temp table
    by_model_temp.to_csv(outputs_dir / "prompt_metrics_by_model_temp.csv", index=False)
    logger.info("  Saved: prompt_metrics_by_model_temp.csv")

    # Aggregate by question
    by_question = (
        llm_with_metrics.groupby(["identifier", "identifier_no", "question"])
        .agg(
            n_model_temps=("model_temp", "nunique"),
            retrieved_total_mean=("retrieved_total", "mean"),
            retrieved_total_median=("retrieved_total", "median"),
            n_elements_mean=("n_elements", "mean"),
            f1_mean=("f1", "mean"),
            f1_median=("f1", "median"),
            precision_mean=("precision", "mean"),
            recall_mean=("recall", "mean"),
        )
        .reset_index()
        .sort_values("identifier_no")
        .round(4)
    )

    # Save by_question table
    by_question.to_csv(outputs_dir / "prompt_metrics_by_question.csv", index=False)
    logger.info("  Saved: prompt_metrics_by_question.csv")

    # Chart 1: Retrieved total by model-temp (with IQR if not skip_ranges)
    base = alt.Chart(by_model_temp)

    points = base.mark_circle(size=80, opacity=1).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("retrieved_total_median:Q", title="Retrieved Total (Median)"),
        color=alt.Color(
            "temperature:N", title="Temperature", scale=alt.Scale(scheme="orangered")
        ),
        tooltip=[
            "model_temp:N",
            "retrieved_total_median:Q",
            "retrieved_total_mean:Q",
            "f1_mean:Q",
        ],
    )

    if skip_ranges:
        fig = points.properties(
            width=800, height=400, title=f"Retrieved Total by Model-Temp - {prompt}"
        )
    else:
        error_bars = base.mark_errorbar().encode(
            x=alt.X("model_temp:N", axis=alt.Axis(labelAngle=-45), sort=model_temps),
            y=alt.Y("retrieved_total_q1:Q", title=""),
            y2=alt.Y2("retrieved_total_q3:Q", title=""),
            color=alt.Color("temperature:N", scale=alt.Scale(scheme="orangered")),
        )
        fig = (error_bars + points).properties(
            width=800, height=400, title=f"Retrieved Total by Model-Temp - {prompt}"
        )

    fig.save(
        str(outputs_dir / "prompt_retrieved_total_by_model_temp.png"), scale_factor=2
    )

    # Chart 2: F1 scores by model-temp
    fig = (
        alt.Chart(by_model_temp)
        .mark_bar(opacity=1)
        .encode(
            x=alt.X(
                "model_temp:N",
                title="Model-Temperature",
                axis=alt.Axis(labelAngle=-45),
                sort=model_temps,
            ),
            y=alt.Y("f1_mean:Q", title="F1 Score"),
            color=alt.Color(
                "temperature:Q",
                title="Temperature",
                scale=alt.Scale(scheme="orangered"),
            ),
            tooltip=["model_temp:N", "f1_mean:Q", "precision_mean:Q", "recall_mean:Q"],
        )
        .properties(
            width=800, height=400, title=f"F1 Score by Model-Temperature - {prompt}"
        )
    )
    fig.save(str(outputs_dir / "prompt_f1_by_model_temp.png"), scale_factor=2)

    # Chart 2: F1 median by model-temp
    fig = (
        alt.Chart(by_model_temp)
        .mark_bar(opacity=1)
        .encode(
            x=alt.X(
                "model_temp:N",
                title="Model-Temperature",
                axis=alt.Axis(labelAngle=-45),
                sort=model_temps,
            ),
            y=alt.Y("f1_median:Q", title="F1 Score"),
            color=alt.Color(
                "temperature:Q",
                title="Temperature",
                scale=alt.Scale(scheme="orangered"),
            ),
        )
        .properties(
            width=800,
            height=400,
            title=f"F1 Score Median by Model-Temperature - {prompt}",
        )
    )
    fig.save(str(outputs_dir / "prompt_f1_median_by_model_temp.png"), scale_factor=2)

    # Chart 3: F1 by question
    fig = (
        alt.Chart(by_question)
        .mark_bar()
        .encode(
            y=alt.Y(
                "question:N",
                title="Question",
                sort=alt.EncodingSortField(field="identifier_no"),
            ),
            x=alt.X("f1_mean:Q", title="F1 Score"),
            tooltip=["identifier:N", "f1_mean:Q", "retrieved_total_mean:Q"],
        )
        .properties(width=300, height=200, title=f"F1 Score by Question - {prompt}")
    )
    fig.save(str(outputs_dir / "prompt_f1_by_question.png"), scale_factor=2)

    # Chart 4: F1 median by question
    fig = (
        alt.Chart(by_question)
        .mark_bar(opacity=1)
        .encode(
            y=alt.Y(
                "question:N",
                title="Question",
                sort=alt.EncodingSortField(field="identifier_no"),
            ),
            x=alt.X("f1_median:Q", title="F1 Score"),
            tooltip=["identifier:N", "f1_median:Q", "retrieved_total_mean:Q"],
        )
        .properties(
            width=300, height=200, title=f"F1 Score Median by Question - {prompt}"
        )
    )
    fig.save(str(outputs_dir / "prompt_f1_median_by_question.png"), scale_factor=2)


def main(
    experiment_name: str,
    n_questions: int,
    config_path: Path,
    combine_runs_flag: bool = False,
    compare_combined_runs: bool = False,
):
    """Generate all experiment charts.

    Args:
        experiment_name: Name of the experiment
        n_questions: Number of questions to process
        config_path: Path to config YAML file
        combine_runs_flag: If True, combine and deduplicate results across runs
        compare_combined_runs: If True, generate comparison charts between single and combined runs
    """
    # Load config
    config = yaml.load(open(config_path, "r"), Loader=yaml.SafeLoader)

    mode_str = "COMBINED RUNS" if combine_runs_flag else "INDIVIDUAL RUNS"
    logger.info("=" * 80)
    logger.info(f"EXPERIMENT CHARTS: {experiment_name} ({mode_str})")
    logger.info("=" * 80)

    # Setup output directory
    if combine_runs_flag:
        BASE_OUTPUTS_DIR = (
            TESTING_DIR
            / "r_and_d/boolean_queries/outputs"
            / experiment_name
            / "combined_results"
        )
    else:
        BASE_OUTPUTS_DIR = (
            TESTING_DIR / "r_and_d/boolean_queries/outputs" / experiment_name
        )
    BASE_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    llm_results_df = pd.read_json(
        BOOL_DIR / f"{experiment_name}_results.jsonl", lines=True
    ).pipe(process_results, config=config)
    logger.info(f"Loaded {experiment_name} results: {llm_results_df.shape}")

    # Combine runs if requested
    if combine_runs_flag:
        logger.info("Combining runs (max 5 per parameter combination)...")
        llm_results_df = combine_runs(llm_results_df, max_runs=5, random_seed=42)
        logger.info(f"Combined results shape: {llm_results_df.shape}")

    baseline_results_df = (
        pd.read_json(BOOL_DIR / "baseline_results.jsonl", lines=True)
        .pipe(process_results, config=config)
        .drop_duplicates(subset=["identifier"], keep="first")
    )
    logger.info(f"Loaded baseline results: {baseline_results_df.shape}")

    # Get model_temps for sorting
    model_temps = [
        f"{model} temp={temp:.1f}"
        for model in config["models"]
        for temp in config["temperatures"]
    ]

    # Get unique references (identifiers) up to n_questions
    references = (
        llm_results_df.sort_values("identifier_no")
        .drop_duplicates("identifier")
        .iloc[:n_questions]["identifier"]
        .tolist()
    )
    logger.info(f"Processing {len(references)} questions: {references}")

    # Get prompts from config
    prompts = config.get("prompts")
    logger.info(f"Processing {len(prompts)} prompts: {prompts}")

    # Process each prompt separately
    for prompt in prompts:
        logger.info("\n" + "=" * 80)
        logger.info(f"PROMPT: {prompt}")
        logger.info("=" * 80)

        # Create prompt-specific output directory
        OUTPUTS_DIR = BASE_OUTPUTS_DIR / prompt
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

        # Filter data for this prompt
        llm_prompt_df = llm_results_df.query("prompt == @prompt")

        if len(llm_prompt_df) == 0:
            logger.warning(f"  No data for prompt {prompt}, skipping")
            continue

        # Plot individual questions for this prompt
        logger.info("\n" + "-" * 80)
        logger.info(f"INDIVIDUAL QUESTION CHARTS - {prompt}")
        logger.info("-" * 80)

        for reference in references:
            # Filter for this question
            analysis_df = llm_prompt_df.query("identifier == @reference").fillna(
                {"retrieved_count": 0, "retrieved_total": 0}
            )

            if len(analysis_df) == 0:
                logger.warning(f"  No data for {reference}, skipping")
                continue

            # Plot basic charts (skip ranges for combined runs)
            plot_individual_question(
                analysis_df,
                reference,
                OUTPUTS_DIR,
                model_temps,
                skip_ranges=combine_runs_flag,
            )

            # Compute metrics for this question
            baseline_result_ids = baseline_results_df.query("identifier == @reference")
            if len(baseline_result_ids) > 0 and isinstance(
                baseline_result_ids.iloc[0].get("results_id"), list
            ):
                baseline_ids = baseline_result_ids.results_id.iloc[0]

                metrics_df = analysis_df.copy()
                for index, row in analysis_df.iterrows():
                    test_ids = row.get("results_id")
                    if isinstance(test_ids, list):
                        (
                            precision,
                            recall,
                            f1,
                            topn_recall,
                            topn_precision,
                        ) = get_metrics(baseline_ids, test_ids)
                        metrics_df.loc[index, "precision"] = precision
                        metrics_df.loc[index, "recall"] = recall
                        metrics_df.loc[index, "f1"] = f1
                        metrics_df.loc[index, "topn_recall"] = topn_recall
                        metrics_df.loc[index, "topn_precision"] = topn_precision
                    else:
                        metrics_df.loc[index, "precision"] = 0
                        metrics_df.loc[index, "recall"] = 0
                        metrics_df.loc[index, "f1"] = 0
                        metrics_df.loc[index, "topn_recall"] = 0
                        metrics_df.loc[index, "topn_precision"] = 0

                # Plot metric charts
                plot_individual_question_with_metrics(
                    metrics_df,
                    reference,
                    OUTPUTS_DIR,
                    model_temps,
                    skip_ranges=combine_runs_flag,
                )

        # Plot prompt summary analysis
        logger.info("\n" + "-" * 80)
        logger.info(f"PROMPT SUMMARY CHARTS - {prompt}")
        logger.info("-" * 80)

        # Filter for this prompt and first n_questions
        llm_filtered = llm_prompt_df[
            llm_prompt_df["identifier_no"] < n_questions
        ].fillna({"retrieved_total": 0})

        baseline_filtered = baseline_results_df[
            baseline_results_df["identifier_no"] < n_questions
        ]

        logger.info(
            f"  Filtered to {len(llm_filtered)} LLM rows, {len(baseline_filtered)} baseline rows"
        )

        # Plot prompt analysis
        plot_prompt_analysis(
            llm_filtered,
            baseline_filtered,
            prompt,
            OUTPUTS_DIR,
            model_temps,
            skip_ranges=combine_runs_flag,
        )

        # Combined runs comparison analysis (optional)
        if compare_combined_runs and not combine_runs_flag:
            logger.info("\n" + "-" * 80)
            logger.info(f"COMBINED RUNS ANALYSIS - {prompt}")
            logger.info("-" * 80)

            # Combine results across runs (max 5 runs per parameter combination)
            combined_df = combine_runs(llm_filtered, max_runs=5, random_seed=42)
            logger.info(
                f"  Combined {len(llm_filtered)} individual runs into {len(combined_df)} combined results"
            )

            # Plot comparison between single and combined runs
            plot_combined_vs_single_comparison(
                llm_filtered,
                combined_df,
                baseline_filtered,
                OUTPUTS_DIR,
                model_temps,
            )

    logger.info("\n" + "=" * 80)
    logger.info(f"✓ Experiment charts complete! Saved to: {BASE_OUTPUTS_DIR}")
    logger.info("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate experiment charts")
    parser.add_argument(
        "--experiment",
        type=str,
        default="experiment1",
        help="Experiment name (e.g., 'experiment1', 'experiment2')",
    )
    parser.add_argument(
        "--n-questions",
        type=int,
        default=3,
        help="Number of questions (identifiers) to process",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Config file name (e.g., 'config.yaml', 'config_2.yaml')",
    )
    parser.add_argument(
        "--combine-runs",
        action="store_true",
        help="Combine and deduplicate results across runs (max 5 runs per parameter)",
    )
    parser.add_argument(
        "--compare-combined-runs",
        action="store_true",
        help="Generate comparison charts between single and combined runs",
    )

    args = parser.parse_args()

    # Build config path
    config_path = TESTING_DIR / "r_and_d/boolean_queries" / args.config

    main(
        experiment_name=args.experiment,
        n_questions=args.n_questions,
        config_path=config_path,
        combine_runs_flag=args.combine_runs,
        compare_combined_runs=args.compare_combined_runs,
    )
