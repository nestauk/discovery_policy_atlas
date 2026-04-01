"""Visualise recurring outcomes across meta themes.

Produces:
1. Heatmap: outcomes × meta themes, coloured by predicted magnitude
2. Horizontal bar chart: outcomes ranked by frequency (number of meta themes)
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

DATA_DIR = Path("scripts/output/ar_bottom_up/data/outcome_by_meta_theme")
OUT_DIR = Path("scripts/output/ar_bottom_up/charts")

MAGNITUDE_RANK = {
    "large": 4,
    "substantial": 3,
    "moderate": 2,
    "marginal": 1,
    "unknown": 0,
}

MAGNITUDE_COLORS = {
    "large": "#0d4f4f",
    "substantial": "#18a999",
    "moderate": "#5cc8b5",
    "marginal": "#b2e0d6",
    "unknown": "#e0e0e0",
}


def _pretty_theme(slug: str) -> str:
    return slug.replace("_", " ").title()


def load_all() -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(str(DATA_DIR / "*.csv"))):
        df = pd.read_csv(f)
        df["meta_theme"] = _pretty_theme(os.path.basename(f).replace(".csv", ""))
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def make_heatmap(combined: pd.DataFrame) -> go.Figure:
    """Outcome × meta-theme heatmap coloured by max predicted magnitude."""
    combined["mag_rank"] = combined["Predicted Magnitude"].map(MAGNITUDE_RANK).fillna(0)
    pivot = (
        combined.groupby(["Outcome Name", "meta_theme"])["mag_rank"]
        .max()
        .reset_index()
        .pivot(index="Outcome Name", columns="meta_theme", values="mag_rank")
        .fillna(-1)
    )

    # Sort outcomes by number of themes they appear in (descending)
    presence = (pivot >= 0).sum(axis=1).sort_values(ascending=True)
    pivot = pivot.loc[presence.index]

    colorscale = [
        [0.0, "#ffffff"],
        [0.2, "#e0e0e0"],
        [0.4, "#b2e0d6"],
        [0.6, "#5cc8b5"],
        [0.8, "#18a999"],
        [1.0, "#0d4f4f"],
    ]

    z_norm = (pivot.values + 1) / 5

    mag_labels = {v: k for k, v in MAGNITUDE_RANK.items()}
    mag_labels[-1] = "—"
    hover = []
    for i, outcome in enumerate(pivot.index):
        row = []
        for j, theme in enumerate(pivot.columns):
            val = pivot.iloc[i, j]
            row.append(
                f"<b>{outcome}</b><br>Theme: {theme}<br>"
                f"Magnitude: {mag_labels.get(int(val), '—')}"
            )
        hover.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z_norm,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            hovertext=hover,
            hoverinfo="text",
            colorscale=colorscale,
            showscale=False,
            xgap=2,
            ygap=2,
        )
    )

    fig.update_layout(
        title="Outcome recurrence across meta themes<br><sub>Colour = max predicted magnitude (darker = stronger)</sub>",
        xaxis=dict(tickangle=45, side="bottom"),
        yaxis=dict(autorange="reversed"),
        height=max(600, len(pivot) * 22),
        width=max(900, len(pivot.columns) * 70),
        margin=dict(l=350, b=200, t=80),
        font=dict(size=11),
    )
    return fig


def make_bar_chart(combined: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of outcomes by number of meta themes they appear in."""
    theme_counts = (
        combined.groupby("Outcome Name")["meta_theme"]
        .nunique()
        .sort_values(ascending=True)
        .reset_index()
    )
    theme_counts.columns = ["Outcome", "Num Themes"]

    row_counts = combined["Outcome Name"].value_counts().to_dict()
    theme_counts["Total Mentions"] = theme_counts["Outcome"].map(row_counts)

    combined["mag_rank"] = combined["Predicted Magnitude"].map(MAGNITUDE_RANK).fillna(0)
    max_mag = combined.groupby("Outcome Name")["mag_rank"].max().to_dict()
    mag_labels = {v: k for k, v in MAGNITUDE_RANK.items()}
    theme_counts["Max Magnitude"] = theme_counts["Outcome"].apply(
        lambda x: mag_labels.get(int(max_mag.get(x, 0)), "unknown")
    )
    theme_counts["color"] = theme_counts["Max Magnitude"].map(MAGNITUDE_COLORS)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=theme_counts["Outcome"],
            x=theme_counts["Num Themes"],
            orientation="h",
            marker_color=theme_counts["color"],
            hovertext=[
                f"<b>{row.Outcome}</b><br>"
                f"Appears in {row['Num Themes']} meta themes<br>"
                f"Total mentions: {row['Total Mentions']}<br>"
                f"Max magnitude: {row['Max Magnitude']}"
                for _, row in theme_counts.iterrows()
            ],
            hoverinfo="text",
        )
    )

    fig.update_layout(
        title="Outcomes by number of meta themes they appear in<br><sub>Colour = max predicted magnitude</sub>",
        xaxis=dict(title="Number of meta themes", dtick=1),
        yaxis=dict(autorange="reversed"),
        height=max(600, len(theme_counts) * 22),
        width=900,
        margin=dict(l=350, t=80),
        font=dict(size=11),
    )
    return fig


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    combined = load_all()

    heatmap = make_heatmap(combined)
    heatmap.write_html(str(OUT_DIR / "outcome_recurrence_heatmap.html"))
    heatmap.write_image(str(OUT_DIR / "outcome_recurrence_heatmap.png"), scale=2)
    print(f"Heatmap saved to {OUT_DIR / 'outcome_recurrence_heatmap.html'}")

    bar = make_bar_chart(combined)
    bar.write_html(str(OUT_DIR / "outcome_recurrence_bar.html"))
    bar.write_image(str(OUT_DIR / "outcome_recurrence_bar.png"), scale=2)
    print(f"Bar chart saved to {OUT_DIR / 'outcome_recurrence_bar.html'}")


if __name__ == "__main__":
    main()
