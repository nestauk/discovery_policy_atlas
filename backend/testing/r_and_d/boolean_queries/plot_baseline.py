"""Generate baseline charts.

Usage (run from backend directory):
    cd backend
    uv run python testing/r_and_d/boolean_queries/plot_baseline.py
"""

import pandas as pd
import altair as alt
import yaml
from testing import TESTING_DIR, logger
from testing.r_and_d.boolean_queries.query_tester import get_question_id

# Paths
BOOL_DIR = TESTING_DIR / "r_and_d/boolean_queries/outputs/"
CONFIG_PATH = TESTING_DIR / "r_and_d/boolean_queries/config.yaml"
OUTPUTS_DIR = TESTING_DIR / "r_and_d/boolean_queries/outputs/baseline"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Load config
config = yaml.load(open(CONFIG_PATH, "r"), Loader=yaml.SafeLoader)


def process_results(df: pd.DataFrame) -> pd.DataFrame:
    """Process baseline results.

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


def main():
    logger.info("=" * 80)
    logger.info("BASELINE CHARTS")
    logger.info("=" * 80)

    # Load baseline data
    baseline_df = pd.read_json(BOOL_DIR / "baseline_results.jsonl", lines=True).pipe(
        process_results
    )
    logger.info(f"Baseline results: {baseline_df.shape}")

    # Chart 1: Retrieved count by question (full scale)
    fig = (
        alt.Chart(baseline_df)
        .mark_bar()
        .encode(
            x="retrieved_total:Q",
            y=alt.Y(
                "question:N",
                sort=alt.EncodingSortField(field="identifier_no", order="ascending"),
            ),
            tooltip=[
                alt.Tooltip("identifier:N", title="Question ID"),
                alt.Tooltip("question:N", title="Question"),
                alt.Tooltip("retrieved_total:Q", title="Retrieved count"),
                alt.Tooltip("boolean_query:N", title="Boolean query"),
            ],
        )
        .properties(
            width=600,
            height=400,
        )
    )
    fig.save(str(OUTPUTS_DIR / "retrieved_total_by_question.png"), scale_factor=2)
    logger.info("Saved: retrieved_total_by_question.png")

    # Chart 2: Retrieved count by question (clamped to 100k)
    fig = (
        alt.Chart(baseline_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "retrieved_total:Q", scale=alt.Scale(domain=[0, 100_000], clamp=True)
            ),
            y=alt.Y(
                "question:N",
                sort=alt.EncodingSortField(field="identifier_no", order="ascending"),
            ),
            tooltip=[
                alt.Tooltip("identifier:N", title="Question ID"),
                alt.Tooltip("question:N", title="Question"),
                alt.Tooltip("retrieved_total:Q", title="Retrieved count"),
                alt.Tooltip("boolean_query:N", title="Boolean query"),
            ],
        )
        .properties(
            width=600,
            height=400,
        )
    )
    fig.save(
        str(OUTPUTS_DIR / "retrieved_total_by_question_clamped.png"), scale_factor=2
    )
    logger.info("Saved: retrieved_total_by_question_clamped.png")

    # Chart 3: N tokens distribution
    fig = (
        alt.Chart(baseline_df)
        .mark_bar()
        .encode(
            x=alt.X("n_tokens:Q", bin=True),
            y=alt.Y("count()", title="Count", scale=alt.Scale(domain=[0, 15])),
        )
        .properties(
            width=250,
            height=150,
        )
    )
    fig.save(str(OUTPUTS_DIR / "n_tokens_distribution.png"), scale_factor=2)
    logger.info("Saved: n_tokens_distribution.png")

    # Chart 4: N elements distribution
    fig = (
        alt.Chart(baseline_df)
        .mark_bar()
        .encode(
            x=alt.X("n_elements:Q", bin=True),
            y=alt.Y("count()", title="Count"),
        )
        .properties(
            width=250,
            height=150,
        )
    )
    fig.save(str(OUTPUTS_DIR / "n_elements_distribution.png"), scale_factor=2)
    logger.info("Saved: n_elements_distribution.png")

    logger.info("\n" + "=" * 80)
    logger.info(f"✓ Baseline charts complete! Saved to: {OUTPUTS_DIR}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
