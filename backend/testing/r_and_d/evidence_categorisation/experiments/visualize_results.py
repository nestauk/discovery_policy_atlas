"""
Generate visualizations from experiment results.

Produces 3 plots:
1. model_comparison.png - Bar charts comparing models on 3 key metrics
2. prompt_comparison.png - Prompt impact for the best performing model
3. accuracy_heatmap.png - Model × Prompt accuracy heatmap

Usage:
    python visualize_results.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
PLOTS_DIR = PROJECT_DIR / "plots"

# Style settings
plt.style.use("seaborn-v0_8-whitegrid")
COLORS = {
    "accuracy": "steelblue",
    "macro_recall": "coral",
    "macro_f1": "mediumseagreen",
    "variant_a": "steelblue",
    "variant_b": "darkorange",
}


def plot_model_comparison(df: pd.DataFrame, output_dir: Path) -> None:
    """
    Create bar charts comparing models across 3 key metrics.
    Averaged across all datasets and prompts.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Average across datasets and prompts
    model_metrics = (
        df.groupby("model")
        .agg({"accuracy": "mean", "macro_recall": "mean", "macro_f1": "mean"})
        .sort_values("accuracy", ascending=True)
    )

    metrics = [
        ("accuracy", "Accuracy", COLORS["accuracy"]),
        ("macro_recall", "Macro Recall", COLORS["macro_recall"]),
        ("macro_f1", "Macro F1", COLORS["macro_f1"]),
    ]

    for ax, (metric, title, color) in zip(axes, metrics):
        values = model_metrics[metric]
        bars = ax.barh(model_metrics.index, values, color=color)
        ax.set_xlabel(title)
        ax.set_title(f"Model Comparison: {title}")
        ax.set_xlim([0, 1])

        # Add value labels
        for bar, val in zip(bars, values):
            ax.text(
                val + 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.1%}",
                va="center",
                fontsize=9,
            )

    plt.tight_layout()
    output_path = output_dir / "model_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path.name}")


def plot_prompt_comparison(df: pd.DataFrame, output_dir: Path) -> None:
    """
    Compare prompts for the best performing model (by accuracy).
    """
    # Identify best model by accuracy
    model_acc = df.groupby("model")["accuracy"].mean()
    best_model = model_acc.idxmax()
    print(f"  Best model (by accuracy): {best_model}")

    # Filter to best model only
    df_best = df[df["model"] == best_model]

    # Group by prompt variant
    prompt_metrics = df_best.groupby("prompt_variant").agg(
        {"accuracy": "mean", "macro_recall": "mean", "macro_f1": "mean"}
    )

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    metrics = [
        ("accuracy", "Accuracy"),
        ("macro_recall", "Macro Recall"),
        ("macro_f1", "Macro F1"),
    ]

    x_labels = prompt_metrics.index.tolist()
    colors = [COLORS.get(label, "gray") for label in x_labels]

    for ax, (metric, title) in zip(axes, metrics):
        values = prompt_metrics[metric]
        bars = ax.bar(x_labels, values, color=colors)
        ax.set_ylabel(title)
        ax.set_title(f"Prompt Comparison: {title}\n(Model: {best_model})")
        ax.set_ylim([0, 1])

        # Add value labels
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val + 0.02,
                f"{val:.1%}",
                ha="center",
                fontsize=10,
            )

    plt.tight_layout()
    output_path = output_dir / "prompt_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path.name}")


def plot_accuracy_heatmap(df: pd.DataFrame, output_dir: Path) -> None:
    """
    Create heatmap showing accuracy for Model × Prompt combinations.
    Averaged across datasets.
    """
    # Pivot: rows=model, columns=prompt_variant, values=accuracy
    pivot = df.pivot_table(
        values="accuracy", index="model", columns="prompt_variant", aggfunc="mean"
    )

    fig, ax = plt.subplots(figsize=(8, 6))

    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1%",
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        ax=ax,
        cbar_kws={"label": "Accuracy"},
        linewidths=0.5,
    )

    ax.set_title("Accuracy Heatmap: Model × Prompt", fontsize=14, fontweight="bold")
    ax.set_xlabel("Prompt Variant", fontsize=12)
    ax.set_ylabel("Model", fontsize=12)

    plt.tight_layout()
    output_path = output_dir / "accuracy_heatmap.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path.name}")


def main():
    print("=" * 60)
    print("Generating Visualizations")
    print("=" * 60)

    # Load results
    results_csv = SCRIPT_DIR / "results_summary.csv"
    if not results_csv.exists():
        print(f"Results file not found: {results_csv}")
        print("Run collect_results.py first!")
        return

    df = pd.read_csv(results_csv)
    print(f"Loaded {len(df)} experiments from {results_csv.name}")
    print()

    # Create plots directory
    PLOTS_DIR.mkdir(exist_ok=True)

    print("Generating plots...")
    plot_model_comparison(df, PLOTS_DIR)
    plot_prompt_comparison(df, PLOTS_DIR)
    plot_accuracy_heatmap(df, PLOTS_DIR)

    print()
    print("=" * 60)
    print("VISUALIZATIONS COMPLETE")
    print("=" * 60)
    print(f"Plots saved to: {PLOTS_DIR}")
    print()
    print("Files created:")
    for plot_file in sorted(PLOTS_DIR.glob("*.png")):
        print(f"  - {plot_file.name}")


if __name__ == "__main__":
    main()
