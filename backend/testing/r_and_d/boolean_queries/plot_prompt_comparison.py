"""
Compare results from two different prompts (pairwise comparison).

Usage:
    uv run python testing/r_and_d/boolean_queries/plot_prompt_comparison.py --comparison comparison_1
"""

from pathlib import Path
import pandas as pd
import altair as alt
import yaml
from testing import TESTING_DIR, logger


def load_prompt_data(
    experiment_name: str, prompt_name: str, metric_type: str = "by_question"
) -> pd.DataFrame:
    """
    Load metrics data for a specific prompt from experiment directory.

    Args:
        experiment_name: Name of the experiment (e.g., "experiment1")
        prompt_name: Name of the prompt subdirectory
        metric_type: Either "by_question" or "by_model_temp"

    Returns:
        DataFrame with prompt metrics
    """
    outputs_dir = TESTING_DIR / "r_and_d/boolean_queries/outputs"

    if metric_type == "by_question":
        filename = "prompt_metrics_by_question.csv"
    elif metric_type == "by_model_temp":
        filename = "prompt_metrics_by_model_temp.csv"
    else:
        raise ValueError(f"Invalid metric_type: {metric_type}")

    file_path = outputs_dir / experiment_name / prompt_name / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Metrics file not found: {file_path}")

    df = pd.read_csv(file_path)
    df["prompt"] = prompt_name
    return df


def plot_f1_by_question(
    df1: pd.DataFrame, df2: pd.DataFrame, output_path: Path, save: bool = True
) -> alt.LayerChart:
    """Create F1 score comparison chart by question with connecting lines."""
    df = pd.concat([df1, df2], ignore_index=True)

    base = alt.Chart(df)

    lines = base.mark_line(color="gray", opacity=0.3).encode(
        y=alt.Y("question:N", title="Question"),
        x=alt.X("f1_median:Q", title="F1 Score"),
        detail="question:N",
    )

    points = base.mark_circle(opacity=1, size=100).encode(
        y=alt.Y("question:N", title="Question"),
        x=alt.X("f1_median:Q", title="F1 Score"),
        color=alt.Color(
            "prompt:N", title="Prompt", scale=alt.Scale(scheme="tableau10")
        ),
    )

    fig = lines + points

    if save:
        fig.save(str(output_path / "prompt_f1_by_question.png"), scale_factor=2)

    return fig


def plot_f1_by_model_temp(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    model_temps: list[str],
    output_path: Path,
    save: bool = True,
) -> alt.LayerChart:
    """Create F1 score comparison chart by model-temperature with connecting lines."""
    df = pd.concat([df1, df2], ignore_index=True)
    common_models = set(df1["model_temp"].unique()) & set(df2["model_temp"].unique())
    df = df[df["model_temp"].isin(common_models)]

    base = alt.Chart(df)

    lines = base.mark_line(color="gray", opacity=0.3).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("f1_median:Q", title="F1 Score"),
        detail="model_temp:N",
    )

    points = base.mark_circle(opacity=1, size=100).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("f1_median:Q", title="F1 Score"),
        color=alt.Color(
            "prompt:N", title="Prompt", scale=alt.Scale(scheme="tableau10")
        ),
    )

    fig = lines + points

    if save:
        fig.save(str(output_path / "prompt_f1_by_model_temp.png"), scale_factor=2)

    return fig


def plot_retrieved_total_by_model_temp(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    model_temps: list[str],
    output_path: Path,
    save: bool = True,
) -> alt.LayerChart:
    """Create retrieved total comparison chart by model-temperature with connecting lines."""
    df = pd.concat([df1, df2], ignore_index=True)
    common_models = set(df1["model_temp"].unique()) & set(df2["model_temp"].unique())
    df = df[df["model_temp"].isin(common_models)]

    base = alt.Chart(df)

    lines = base.mark_line(color="gray", opacity=0.3).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("retrieved_total_median:Q", title="Retrieved Total (Median)"),
        detail="model_temp:N",
    )

    points = base.mark_circle(opacity=1, size=100).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("retrieved_total_median:Q", title="Retrieved Total (Median)"),
        color=alt.Color(
            "prompt:N", title="Prompt", scale=alt.Scale(scheme="tableau10")
        ),
    )

    fig = lines + points

    if save:
        fig.save(
            str(output_path / "prompt_retrieved_total_by_model_temp.png"),
            scale_factor=2,
        )

    return fig


def plot_n_elements_by_model_temp(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    model_temps: list[str],
    output_path: Path,
    save: bool = True,
) -> alt.LayerChart:
    """Create number of elements comparison chart by model-temperature with connecting lines."""
    df = pd.concat([df1, df2], ignore_index=True)
    common_models = set(df1["model_temp"].unique()) & set(df2["model_temp"].unique())
    df = df[df["model_temp"].isin(common_models)]

    base = alt.Chart(df)

    lines = base.mark_line(color="gray", opacity=0.3).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("n_elements_mean:Q", title="No of Elements (Mean)"),
        detail="model_temp:N",
    )

    points = base.mark_circle(opacity=1, size=100).encode(
        x=alt.X(
            "model_temp:N",
            title="Model-Temperature",
            axis=alt.Axis(labelAngle=-45),
            sort=model_temps,
        ),
        y=alt.Y("n_elements_mean:Q", title="No of Elements (Mean)"),
        color=alt.Color(
            "prompt:N", title="Prompt", scale=alt.Scale(scheme="tableau10")
        ),
    )

    fig = lines + points

    if save:
        fig.save(
            str(output_path / "prompt_n_elements_by_model_temp.png"), scale_factor=2
        )

    return fig


def get_model_temps_order(config_name: str) -> list[str]:
    """
    Get the ordered list of model-temperature combinations from config.

    Args:
        config_name: Name of the config file (e.g., "config.yaml")

    Returns:
        Ordered list of model-temperature combinations
    """
    config_path = TESTING_DIR / "r_and_d/boolean_queries" / config_name
    with open(config_path) as f:
        config = yaml.safe_load(f)

    model_temps = []
    for model in config.get("models", []):
        for temp in config.get("temperatures", []):
            model_temps.append(f"{model} temp={temp:.1f}")

    return model_temps


def compare_prompts(
    experiment1: str,
    prompt1_name: str,
    experiment2: str,
    prompt2_name: str,
    output_dir: Path,
    config_name: str,
    save_charts: bool = True,
):
    """
    Compare results from two prompts and generate comparison charts.

    Args:
        experiment1: Name of first experiment
        prompt1_name: Name of first prompt
        experiment2: Name of second experiment
        prompt2_name: Name of second prompt
        output_dir: Directory to save comparison charts
        config_name: Name of config file for model ordering
        save_charts: Whether to save charts to disk
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get model-temperature ordering
    model_temps = get_model_temps_order(config_name)

    logger.info(f"Loading data for prompt 1: {prompt1_name} from {experiment1}")
    df1_by_question = load_prompt_data(experiment1, prompt1_name, "by_question")
    df1_by_model_temp = load_prompt_data(experiment1, prompt1_name, "by_model_temp")

    logger.info(f"Loading data for prompt 2: {prompt2_name} from {experiment2}")
    df2_by_question = load_prompt_data(experiment2, prompt2_name, "by_question")
    df2_by_model_temp = load_prompt_data(experiment2, prompt2_name, "by_model_temp")

    logger.info("Generating comparison charts...")

    logger.info("  - F1 score by question")
    plot_f1_by_question(df1_by_question, df2_by_question, output_dir, save=save_charts)

    logger.info("  - F1 score by model-temperature")
    plot_f1_by_model_temp(
        df1_by_model_temp, df2_by_model_temp, model_temps, output_dir, save=save_charts
    )

    logger.info("  - Retrieved total by model-temperature")
    plot_retrieved_total_by_model_temp(
        df1_by_model_temp, df2_by_model_temp, model_temps, output_dir, save=save_charts
    )

    logger.info("  - Number of elements by model-temperature")
    plot_n_elements_by_model_temp(
        df1_by_model_temp, df2_by_model_temp, model_temps, output_dir, save=save_charts
    )

    logger.info(f"Charts saved to: {output_dir}")


def load_comparison_config(config_path: Path) -> dict:
    """Load comparison configuration from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    """Main function with CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare results from two prompts (pairwise comparison)"
    )
    parser.add_argument(
        "--comparison",
        type=str,
        required=True,
        help="Comparison ID from config_comparison.yaml (e.g., 'comparison_1')",
    )
    parser.add_argument(
        "--config-comparison",
        type=str,
        default="config_comparison.yaml",
        help="Name of comparison config file (default: config_comparison.yaml)",
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Don't save charts to disk"
    )

    args = parser.parse_args()

    # Load comparison configuration
    config_path = TESTING_DIR / "r_and_d/boolean_queries" / args.config_comparison
    if not config_path.exists():
        raise FileNotFoundError(f"Comparison config not found: {config_path}")

    comparison_configs = load_comparison_config(config_path)

    if args.comparison not in comparison_configs:
        available = ", ".join(comparison_configs.keys())
        raise ValueError(
            f"Comparison '{args.comparison}' not found in config. Available: {available}"
        )

    comp_config = comparison_configs[args.comparison]

    # Extract configuration
    experiment1 = comp_config["experiment1"]
    prompt1_name = comp_config["prompt1"]
    experiment2 = comp_config.get("experiment2", experiment1)
    prompt2_name = comp_config["prompt2"]
    output_subdir = comp_config["output_dir"]
    config_name = comp_config.get("config", "config.yaml")

    # Build output path
    outputs_dir = TESTING_DIR / "r_and_d/boolean_queries/outputs"
    output_dir = outputs_dir / output_subdir

    logger.info(f"=== Comparison: {args.comparison} ===")
    logger.info(
        f"Comparing: {experiment1}/{prompt1_name} vs {experiment2}/{prompt2_name}"
    )
    logger.info(f"Output: {output_dir}")

    compare_prompts(
        experiment1=experiment1,
        prompt1_name=prompt1_name,
        experiment2=experiment2,
        prompt2_name=prompt2_name,
        output_dir=output_dir,
        config_name=config_name,
        save_charts=not args.no_save,
    )


if __name__ == "__main__":
    main()
