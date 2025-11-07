"""Generate experiment charts for individual questions and prompt summaries.

Usage (run from backend directory):
    cd backend
    
    # Default experiment (experiment1) with 3 questions:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py
    
    # Custom experiment name:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --experiment experiment2
    
    # Specify number of questions (identifiers) to plot:
    uv run python testing/r_and_d/boolean_queries/plot_experiment.py --n-questions 10
"""

import argparse
import pandas as pd
import altair as alt
import yaml
from pathlib import Path
from testing import TESTING_DIR, logger
from testing.r_and_d.boolean_queries.query_tester import get_question_id

# Paths
BOOL_DIR = TESTING_DIR / "r_and_d/boolean_queries/outputs/"
CONFIG_PATH = TESTING_DIR / "r_and_d/boolean_queries/config.yaml"

# Load config
config = yaml.load(open(CONFIG_PATH, "r"), Loader=yaml.SafeLoader)


def process_results(df: pd.DataFrame) -> pd.DataFrame:
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


def plot_individual_question(
    analysis_df: pd.DataFrame, reference: str, outputs_dir: Path, model_temps: list
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
    metrics_df: pd.DataFrame, reference: str, outputs_dir: Path, model_temps: list
):
    """Generate metric charts for a single question."""
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


def plot_prompt_analysis(
    llm_filtered: pd.DataFrame,
    baseline_filtered: pd.DataFrame,
    prompt: str,
    outputs_dir: Path,
    model_temps: list,
):
    """Generate prompt analysis charts."""
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

    # Chart 1: Retrieved total by model-temp with IQR
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


def main(experiment_name: str, n_questions: int):
    """Generate all experiment charts."""
    logger.info("=" * 80)
    logger.info(f"EXPERIMENT CHARTS: {experiment_name}")
    logger.info("=" * 80)

    # Setup output directory
    BASE_OUTPUTS_DIR = TESTING_DIR / "r_and_d/boolean_queries/outputs" / experiment_name
    BASE_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    llm_results_df = pd.read_json(
        BOOL_DIR / f"{experiment_name}_results.jsonl", lines=True
    ).pipe(process_results)
    logger.info(f"Loaded {experiment_name} results: {llm_results_df.shape}")

    baseline_results_df = (
        pd.read_json(BOOL_DIR / "baseline_results.jsonl", lines=True)
        .pipe(process_results)
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

            # Plot basic charts
            plot_individual_question(analysis_df, reference, OUTPUTS_DIR, model_temps)

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
                    metrics_df, reference, OUTPUTS_DIR, model_temps
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
            llm_filtered, baseline_filtered, prompt, OUTPUTS_DIR, model_temps
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

    args = parser.parse_args()
    main(experiment_name=args.experiment, n_questions=args.n_questions)
