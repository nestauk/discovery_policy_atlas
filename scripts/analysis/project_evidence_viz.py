"""Stacked bar chart of evidence categories per thematic cluster.

Reads the Intervention Themes tab from the QA spreadsheet, filters to
interventions with comparable/match geography context fit, then aggregates
evidence categories up to the project (thematic cluster) level.
"""

from __future__ import annotations

import re
import textwrap
from collections import defaultdict
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

# Evidence category colours and order (strongest evidence first),
# matching clustering.py definitions.
EVIDENCE_CATEGORIES = [
    ("Systematic Review and Meta-Analysis", "#0F294A"),
    ("RCTs and Quasi-Experimental Studies", "#9A1BBE"),
    ("Observational Research Studies", "#0000FF"),
    ("Modelling & Simulation", "#18A48C"),
    ("Policy Syntheses & Guidance Documents", "#97D9E3"),
    ("Qualitative & Contextual Evidence", "#A59BEE"),
    ("Expert Opinion and Commentary", "#F6A4B7"),
    ("Other (Non-evidence documents)", "#F8F5F4"),
    ("Unknown / Insufficient information", "#F8F5F4"),
]
CATEGORY_COLORS = {name: color for name, color in EVIDENCE_CATEGORIES}
CATEGORY_ORDER = [name for name, _ in EVIDENCE_CATEGORIES]

VALID_GEO_FIT = {"comparable", "match"}

# Project title -> reference meta-theme label mapping.
PROJECT_TO_THEME: dict[str, str] = {
    "Interventions to improve early years and family foundations": "Early years & family foundations",
    "Interventions to improve mental health, behaviour and individual capacity": "Mental health, behaviour & individual capability",
    "Interventions to improve community resilience and social capital": "Community resilience & social capital",
    "Interventions for place-based adaptation and climate resilience": "Climate & place-based adaptation",
    "Interventions to improve digital and information resilience": "Digital & information resilience",
    "Institutional and governance reforms to improve agency and resilience": "Institutional & governance reform",
}

DEFAULT_QA = Path("scripts/output/ar_bottom_up/data/qa_review.xlsx")
DEFAULT_OUTPUT = Path("scripts/output/ar_bottom_up/charts")


def _parse_category_string(text: str) -> dict[str, int]:
    """Parse 'Category A (12), Category B (5)' into {category: count}."""
    counts: dict[str, int] = {}
    for match in re.finditer(r"(.+?)\s*\((\d+)\)", str(text)):
        name = match.group(1).strip().strip(",").strip()
        counts[name] = int(match.group(2))
    return counts


def _wrap(label: str, width: int = 30) -> str:
    return "<br>".join(textwrap.wrap(label, width))


def _parse_doc_categories(raw: str) -> list[tuple[str, str]]:
    """Parse 'doc_id::category | ...' into (doc_id, category) pairs."""
    if not raw or raw.strip() == "":
        return []
    pairs = []
    for part in raw.split(" | "):
        part = part.strip()
        if "::" in part:
            doc_id, cat = part.split("::", 1)
            pairs.append((doc_id.strip(), cat.strip()))
    return pairs


def _aggregate_by_theme(interventions: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Aggregate evidence categories per thematic cluster, deduplicating source documents.

    Uses the Source Doc Categories column (doc_id::category pairs) to count
    each document only once per theme, matching the clustering pipeline's
    deduplication approach.
    """
    # {theme: {category: {doc_ids}}}
    theme_cat_docs: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    for _, row in interventions.iterrows():
        title = str(row.get("Project Title") or "")
        theme = PROJECT_TO_THEME.get(title)
        if not theme:
            continue
        for doc_id, cat in _parse_doc_categories(
            str(row.get("Source Doc Categories") or "")
        ):
            theme_cat_docs[theme][cat].add(doc_id)

    # Convert sets to counts
    return {
        theme: {cat: len(doc_ids) for cat, doc_ids in cats.items()}
        for theme, cats in theme_cat_docs.items()
    }


def make_stacked_bar(
    theme_counts: dict[str, dict[str, int]],
    geo_filtered: bool = False,
    subtitle: str | None = None,
) -> go.Figure:
    """Build horizontal stacked bar chart of evidence categories per theme."""
    labels = list(theme_counts.keys())
    all_counts = [theme_counts[lbl] for lbl in labels]

    # Collect all categories that appear, preserving canonical order
    seen = set()
    for counts in all_counts:
        seen.update(counts.keys())
    ordered_cats = [c for c in CATEGORY_ORDER if c in seen]
    for c in sorted(seen - set(ordered_cats)):
        ordered_cats.append(c)

    display_names = [_wrap(lbl) for lbl in labels]

    fig = go.Figure()
    for cat in ordered_cats:
        values = [counts.get(cat, 0) for counts in all_counts]
        fig.add_trace(
            go.Bar(
                y=display_names,
                x=values,
                name=cat,
                orientation="h",
                marker_color=CATEGORY_COLORS.get(cat, "#CCCCCC"),
            )
        )

    fig.update_layout(
        barmode="stack",
        title=(
            "Evidence categories by thematic cluster"
            + (f"<br><sub>{subtitle}</sub>" if subtitle
               else "<br><sub>Filtered to comparable/match geography context fit</sub>" if geo_filtered
               else "")
        ),
        template="plotly_white",
        width=1200,
        height=max(400, len(labels) * 80 + 150),
        xaxis=dict(title="Source Documents"),
        yaxis=dict(tickfont=dict(size=13)),
        legend=dict(
            font=dict(size=11),
            orientation="h",
            yanchor="bottom",
            y=-0.35,
            xanchor="center",
            x=0.5,
        ),
        margin=dict(l=280, b=120, t=80),
    )
    return fig


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evidence categories per project chart")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_QA,
        help="Path to QA spreadsheet (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory (default: %(default)s)",
    )
    args = parser.parse_args()

    all_interventions = pd.read_excel(args.input, sheet_name="Intervention Themes")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # --- Unfiltered chart ---
    print(f"Loaded {len(all_interventions)} interventions")
    theme_counts_all = _aggregate_by_theme(all_interventions)
    for theme, cats in sorted(theme_counts_all.items()):
        print(f"  {theme}: {sum(cats.values())} source documents")

    fig_all = make_stacked_bar(theme_counts_all, geo_filtered=False)
    fig_all.write_html(str(args.output_dir / "project_evidence_categories.html"))
    fig_all.write_image(str(args.output_dir / "project_evidence_categories.png"), scale=2)
    print(f"Saved: project_evidence_categories.html")

    # --- Geography-filtered chart ---
    filtered = all_interventions[
        all_interventions["Geography Context Fit"]
        .str.lower()
        .str.strip()
        .isin(VALID_GEO_FIT)
    ]
    print(f"\nAfter geography fit filter: {len(filtered)} interventions")
    theme_counts_geo = _aggregate_by_theme(filtered)
    for theme, cats in sorted(theme_counts_geo.items()):
        print(f"  {theme}: {sum(cats.values())} source documents")

    fig_geo = make_stacked_bar(theme_counts_geo, geo_filtered=True)
    fig_geo.write_html(str(args.output_dir / "project_evidence_categories_geo_filtered.html"))
    fig_geo.write_image(str(args.output_dir / "project_evidence_categories_geo_filtered.png"), scale=2)
    print(f"Saved: project_evidence_categories_geo_filtered.html")

    # --- Project-level chart (straight from Projects tab, no intervention aggregation) ---
    projects_df = pd.read_excel(args.input, sheet_name="Projects")
    project_counts: dict[str, dict[str, int]] = {}
    for _, row in projects_df.iterrows():
        title = str(row.get("Project Title") or "")
        theme = PROJECT_TO_THEME.get(title)
        if not theme:
            continue
        project_counts[theme] = _parse_category_string(
            row.get("Evidence Categories") or ""
        )
    print(f"\nProject-level (no dedup/aggregation): {len(project_counts)} themes")
    for theme, cats in sorted(project_counts.items()):
        print(f"  {theme}: {sum(cats.values())} source documents")

    fig_proj = make_stacked_bar(project_counts, subtitle="From project-level totals (no intervention aggregation)")
    fig_proj.write_html(str(args.output_dir / "project_evidence_categories_project_level.html"))
    fig_proj.write_image(str(args.output_dir / "project_evidence_categories_project_level.png"), scale=2)
    print(f"Saved: project_evidence_categories_project_level.html")


if __name__ == "__main__":
    main()
