"""Visualisation functions for theme clustering analysis.

Generates:
- UMAP scatter plots (coloured by cluster)
- Search x cluster heatmaps (with totals, white zeros)
- Search x meta-theme heatmaps (with optional verdict filtering)
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd
from umap import UMAP

from clustering import (
    EVIDENCE_CATEGORY_COLORS,
    EVIDENCE_CATEGORY_ORDER,
    TEAL_COLORSCALE,
    VERDICT_COLORS,
    VERDICT_ORDER,
    shorten_search,
    slugify,
    wrap_label,
)


# ---------------------------------------------------------------------------
# Heatmap helpers
# ---------------------------------------------------------------------------


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


def _has_doc_categories(df: pd.DataFrame) -> bool:
    """Check whether the DataFrame has usable Source Doc Categories data."""
    return (
        "Source Doc Categories" in df.columns
        and df["Source Doc Categories"].notna().any()
        and (df["Source Doc Categories"].astype(str).str.strip() != "").any()
    )


def _build_deduped_heatmap_matrix(
    df: pd.DataFrame,
    row_col: str,
    col_col: str,
    col_values: list,
    row_values: list,
) -> np.ndarray:
    """Build a heatmap matrix using deduplicated unique source doc counts."""
    matrix = np.zeros((len(row_values), len(col_values)))
    for ri, row_val in enumerate(row_values):
        for ci, col_val in enumerate(col_values):
            mask = (df[col_col] == col_val) & (df[row_col] == row_val)
            doc_ids: set[str] = set()
            for raw in df.loc[mask, "Source Doc Categories"]:
                for doc_id, _ in _parse_doc_categories(str(raw or "")):
                    doc_ids.add(doc_id)
            matrix[ri, ci] = len(doc_ids)
    return matrix


def _build_heatmap_matrix(
    df: pd.DataFrame,
    row_col: str,
    col_col: str,
    col_values: list,
    row_values: list,
    count_col: str | None,
) -> np.ndarray:
    """Build a count/sum matrix from a DataFrame with given row/column groupings."""
    matrix = np.zeros((len(row_values), len(col_values)))
    for ri, row_val in enumerate(row_values):
        for ci, col_val in enumerate(col_values):
            mask = (df[col_col] == col_val) & (df[row_col] == row_val)
            if count_col and count_col in df.columns:
                matrix[ri, ci] = df.loc[mask, count_col].sum()
            else:
                matrix[ri, ci] = mask.sum()
    return matrix


def _write_figure_outputs(fig, output_path: Path, width: int, height: int) -> None:
    """Write HTML output and best-effort static image output."""
    fig.write_html(str(output_path.with_suffix(".html")))
    try:
        fig.write_image(str(output_path), width=width, height=height, scale=2)
    except Exception as exc:
        logger.warning(
            "Static image export failed for %s (%s). HTML output was written.",
            output_path,
            exc,
        )


def _project_embeddings_2d(embeddings: np.ndarray) -> np.ndarray:
    """Project embeddings to 2D while handling tiny corpora safely."""
    n_rows = len(embeddings)
    if n_rows == 0:
        return np.empty((0, 2))
    if n_rows == 1:
        return np.array([[0.0, 0.0]])
    if n_rows == 2:
        return np.array([[0.0, 0.0], [1.0, 0.0]])

    reducer = UMAP(n_components=2, min_dist=0.3, metric="cosine", random_state=42)
    return reducer.fit_transform(embeddings)


def _render_heatmap(
    matrix: np.ndarray,
    col_labels: list[str],
    row_labels: list[str],
    title: str,
    output_path: Path,
    width: int = 1200,
    height: int = 650,
) -> None:
    """Render a heatmap with totals row/column, annotations, and teal colour scale."""
    import plotly.graph_objects as go

    # Append totals
    row_totals = matrix.sum(axis=1, keepdims=True)
    col_totals = matrix.sum(axis=0, keepdims=True)
    grand_total = matrix.sum()

    aug_matrix = np.hstack([matrix, row_totals])
    bottom_row = np.append(col_totals.flatten(), grand_total).reshape(1, -1)
    aug_matrix = np.vstack([aug_matrix, bottom_row])

    aug_col_labels = col_labels + ["Total"]
    aug_row_labels = row_labels + ["Total"]

    n_rows, n_cols = aug_matrix.shape
    data_max = matrix.max() if matrix.size > 0 else 1

    # Build annotations with bold totals
    annotations = []
    for ri in range(n_rows):
        for ci in range(n_cols):
            val = int(aug_matrix[ri, ci])
            is_total = ri == n_rows - 1 or ci == n_cols - 1
            if val == 0 and not is_total:
                continue
            font_color = (
                "white" if val > data_max * 0.6 and not is_total else "black"
            )
            annotations.append(dict(
                x=ci, y=ri, text=f"<b>{val}</b>" if is_total else str(val),
                font=dict(
                    size=10 if not is_total else 11,
                    color=font_color if not is_total else "#333",
                ),
                showarrow=False,
            ))

    # Mask total row/column so they don't distort the colour scale
    display_matrix = aug_matrix.copy()
    display_matrix[-1, :] = 0
    display_matrix[:, -1] = 0

    fig = go.Figure(data=go.Heatmap(
        z=display_matrix,
        x=aug_col_labels,
        y=aug_row_labels,
        colorscale=TEAL_COLORSCALE,
        showscale=True,
        colorbar=dict(title="Count"),
        zmin=0,
    ))

    fig.add_hline(y=n_rows - 1.5, line=dict(color="black", width=1.5))
    fig.add_vline(x=n_cols - 1.5, line=dict(color="black", width=1.5))

    fig.update_layout(
        title=title,
        template="plotly_white",
        width=width, height=height,
        xaxis=dict(tickangle=30, tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=10), autorange="reversed"),
        annotations=annotations,
        margin=dict(b=200, l=200),
    )

    _write_figure_outputs(fig, output_path, width=width, height=height)
    logger.info("Heatmap: %s", output_path)


# ---------------------------------------------------------------------------
# Public visualisation functions
# ---------------------------------------------------------------------------


def generate_umap_scatter(
    embeddings: np.ndarray,
    topics: list[int],
    names: list[str],
    searches: list[str],
    labels: dict[int, str],
    title: str,
    output_path: Path,
) -> None:
    """Generate 2D UMAP scatter plot coloured by cluster with LLM labels."""
    import plotly.express as px
    import plotly.graph_objects as go

    if len(embeddings) == 0:
        logger.info("Skipping %s -- no embeddings to plot", output_path.name)
        return

    coords = _project_embeddings_2d(embeddings)

    cluster_ids = sorted(set(topics))
    colours = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel1
    colour_map = {}
    ci = 0
    for cid in cluster_ids:
        if cid == -1:
            colour_map[cid] = "rgba(180,180,180,0.4)"
        else:
            colour_map[cid] = colours[ci % len(colours)]
            ci += 1

    fig = go.Figure()
    for cid in cluster_ids:
        mask = [i for i, t in enumerate(topics) if t == cid]
        label = labels.get(cid, f"Cluster {cid}")
        hover_texts = [
            f"{names[i]}<br><i>{shorten_search(searches[i])}</i>"
            for i in mask
        ]
        fig.add_trace(go.Scatter(
            x=coords[mask, 0], y=coords[mask, 1],
            mode="markers",
            marker=dict(size=9, color=colour_map[cid], line=dict(width=0.5, color="white")),
            name=label if cid != -1 else "Unclustered",
            text=hover_texts,
            hoverinfo="text",
        ))

    fig.update_layout(
        title=title,
        template="plotly_white",
        width=1100, height=750,
        legend=dict(font=dict(size=10), yanchor="top", y=0.99, xanchor="left", x=1.02),
        xaxis=dict(showticklabels=False, title=""),
        yaxis=dict(showticklabels=False, title=""),
        margin=dict(r=250),
    )

    _write_figure_outputs(fig, output_path, width=1100, height=750)
    logger.info("UMAP scatter: %s", output_path)


def generate_search_cluster_heatmap(
    df: pd.DataFrame,
    topics: list[int],
    labels: dict[int, str],
    count_col: str | None,
    title: str,
    output_path: Path,
    embeddings: np.ndarray | None = None,
) -> None:
    """Generate search x cluster heatmap with similarity-ordered axes."""
    from scipy.cluster.hierarchy import leaves_list, linkage

    df = df.copy()
    df["cluster_id"] = topics
    df["search_short"] = df["Project Title"].apply(shorten_search)

    cluster_ids = sorted(set(t for t in topics if t != -1))
    if not cluster_ids:
        logger.info("Skipping %s -- no non-outlier clusters", output_path.name)
        return

    search_names = sorted(df["search_short"].unique())

    if count_col and _has_doc_categories(df):
        matrix = _build_deduped_heatmap_matrix(df, "search_short", "cluster_id", cluster_ids, search_names)
    else:
        matrix = _build_heatmap_matrix(df, "search_short", "cluster_id", cluster_ids, search_names, count_col)

    # Order columns by embedding similarity
    if embeddings is not None and len(cluster_ids) > 2:
        cluster_centroids = np.array([
            embeddings[[i for i, t in enumerate(topics) if t == cid]].mean(axis=0)
            for cid in cluster_ids
        ])
        col_order = leaves_list(linkage(cluster_centroids, method="ward", metric="euclidean"))
        cluster_ids = [cluster_ids[i] for i in col_order]
        matrix = matrix[:, col_order]

    # Order rows by coverage profile similarity
    if len(search_names) > 2 and matrix.shape[1] > 0:
        row_order = leaves_list(linkage(matrix, method="ward", metric="euclidean"))
        search_names = [search_names[i] for i in row_order]
        matrix = matrix[row_order, :]

    col_labels = [labels.get(cid, f"Cluster {cid}") for cid in cluster_ids]
    _render_heatmap(matrix, col_labels, search_names, title, output_path)


def generate_themed_heatmap(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
    count_col: str | None,
    title: str,
    output_path: Path,
    verdict_filter: set[str] | None = None,
    emergent_themes: set[str] | None = None,
) -> None:
    """Generate search x meta-theme heatmap, optionally filtering by verdict."""
    df = df.copy()
    df["cluster_id"] = topics
    df["search_short"] = df["Project Title"].apply(shorten_search)
    df["meta_theme"] = df["cluster_id"].map(meta_map).fillna("Unclustered")

    if verdict_filter and "Verdict" in df.columns:
        before = len(df)
        df = df[df["Verdict"].str.strip().str.lower().isin(verdict_filter)].copy()
        logger.debug("Verdict filter: %d -> %d rows (kept %s)", before, len(df), verdict_filter)
        if df.empty:
            logger.info("Skipping %s -- no rows after filtering", output_path.name)
            return

    df = df[df["meta_theme"] != "Unclustered"]
    if df.empty:
        logger.info("Skipping %s -- no meta-themes to plot", output_path.name)
        return

    theme_names = sorted(df["meta_theme"].unique())
    search_names = sorted(df["search_short"].unique())

    # Tag emergent themes with [NEW] in display labels
    emergent = emergent_themes or set()
    display_theme_names = [
        f"{t} [NEW]" if t in emergent else t for t in theme_names
    ]

    if count_col and _has_doc_categories(df):
        matrix = _build_deduped_heatmap_matrix(df, "search_short", "meta_theme", theme_names, search_names)
    else:
        matrix = _build_heatmap_matrix(df, "search_short", "meta_theme", theme_names, search_names, count_col)
    _render_heatmap(matrix, display_theme_names, search_names, title, output_path, width=1100)


def _parse_evidence_breakdown(breakdown_str: str) -> dict[str, int]:
    """Parse 'Category A (3), Category B (1)' into {category: count}."""
    import re
    result: dict[str, int] = {}
    if not breakdown_str or breakdown_str == "None":
        return result
    for match in re.finditer(r"(.+?)\s*\((\d+)\)", breakdown_str):
        category = match.group(1).strip().lstrip(",").strip()
        count = int(match.group(2))
        result[category] = result.get(category, 0) + count
    return result


def _ordered_items(
    all_items: set[str], reference_order: list[str],
) -> list[str]:
    """Return items ordered by reference_order first, then alphabetically."""
    ordered = [item for item in reference_order if item in all_items]
    ordered += sorted(all_items - set(ordered))
    return ordered


def _add_stacked_category_bars(
    fig,
    group_order: list[str],
    display_names: list[str],
    group_cat_counts: dict[str, dict[str, int]],
    color_map: dict[str, str],
    reference_order: list[str],
) -> None:
    """Add stacked bar traces for categorised counts (evidence or verdict)."""
    import plotly.graph_objects as go

    all_cats: set[str] = set()
    for cats in group_cat_counts.values():
        all_cats.update(cats.keys())

    for cat in _ordered_items(all_cats, reference_order):
        values = [group_cat_counts[g].get(cat, 0) for g in group_order]
        if sum(values) == 0:
            continue
        display_name = cat.replace("_", " ").title() if cat == cat.lower() else cat
        fig.add_trace(go.Bar(
            x=display_names,
            y=values,
            name=display_name,
            marker_color=color_map.get(cat, "#CCCCCC"),
        ))
    fig.update_layout(barmode="stack")


def _count_verdicts(
    df: pd.DataFrame, group_col: str, group_order: list[str],
) -> dict[str, dict[str, int]]:
    """Count verdicts per group from a DataFrame with a Verdict column."""
    counts: dict[str, dict[str, int]] = {g: {} for g in group_order}
    for _, row in df.iterrows():
        group = row[group_col]
        if group not in counts:
            continue
        verdict = str(row.get("Verdict") or "").strip().lower() or "insufficient_evidence"
        counts[group][verdict] = counts[group].get(verdict, 0) + 1
    return counts


def generate_meta_theme_barchart(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
    count_col: str | None,
    title: str,
    output_path: Path,
    verdict_filter: set[str] | None = None,
    emergent_themes: set[str] | None = None,
) -> None:
    """Generate a stacked horizontal bar chart of counts per meta-theme.

    If 'Evidence Category Breakdown' column exists, bars are stacked by
    evidence category with the canonical colour scheme. Otherwise falls
    back to a simple blue bar.
    """
    import plotly.graph_objects as go

    df = df.copy()
    df["cluster_id"] = topics
    df["meta_theme"] = df["cluster_id"].map(meta_map).fillna("Unclustered")

    if verdict_filter and "Verdict" in df.columns:
        before = len(df)
        df = df[df["Verdict"].str.strip().str.lower().isin(verdict_filter)].copy()
        logger.debug("Verdict filter (bar): %d -> %d rows", before, len(df))
        if df.empty:
            logger.info("Skipping %s -- no rows after filtering", output_path.name)
            return

    df = df[df["meta_theme"] != "Unclustered"]

    # Check which enrichment columns are available
    has_doc_categories = _has_doc_categories(df)
    has_evidence = (
        "Evidence Category Breakdown" in df.columns
        and df["Evidence Category Breakdown"].notna().any()
        and (df["Evidence Category Breakdown"].astype(str).str.strip() != "None").any()
    )
    has_verdict = "Verdict" in df.columns
    emergent = emergent_themes or set()

    # Build theme order by total count (descending left-to-right for vertical bar)
    # When doc categories are available, order by unique doc count
    if has_doc_categories:
        theme_unique: dict[str, set[str]] = {}
        raw_doc_total = 0
        for _, row in df.iterrows():
            theme = row["meta_theme"]
            if theme not in theme_unique:
                theme_unique[theme] = set()
            pairs = _parse_doc_categories(str(row.get("Source Doc Categories") or ""))
            raw_doc_total += len(pairs)
            for doc_id, _ in pairs:
                theme_unique[theme].add(doc_id)
        unique_doc_total = sum(len(ids) for ids in theme_unique.values())
        logger.debug(
            "Doc dedup: %d raw docs → %d unique docs across %d meta-themes (%d duplicates removed)",
            raw_doc_total, unique_doc_total, len(theme_unique), raw_doc_total - unique_doc_total,
        )
        theme_totals = pd.Series(
            {t: len(ids) for t, ids in theme_unique.items()}
        ).sort_values(ascending=False)
    elif count_col and count_col in df.columns:
        theme_totals = df.groupby("meta_theme")[count_col].sum().sort_values(ascending=False)
    else:
        theme_totals = df["meta_theme"].value_counts().sort_values(ascending=False)

    theme_order = list(theme_totals.index)

    display_names = [
        wrap_label(f"{t} [NEW]" if t in emergent else t) for t in theme_order
    ]

    fig = go.Figure()

    if has_doc_categories:
        # Deduplicated: collect unique (doc_id, category) per theme, count by category
        theme_cat_docs: dict[str, dict[str, set[str]]] = {t: {} for t in theme_order}
        for _, row in df.iterrows():
            theme = row["meta_theme"]
            if theme not in theme_cat_docs:
                continue
            for doc_id, cat in _parse_doc_categories(
                str(row.get("Source Doc Categories") or "")
            ):
                if cat not in theme_cat_docs[theme]:
                    theme_cat_docs[theme][cat] = set()
                theme_cat_docs[theme][cat].add(doc_id)

        theme_cat_counts: dict[str, dict[str, int]] = {
            t: {cat: len(ids) for cat, ids in cats.items()}
            for t, cats in theme_cat_docs.items()
        }
        _add_stacked_category_bars(
            fig, theme_order, display_names, theme_cat_counts,
            EVIDENCE_CATEGORY_COLORS, EVIDENCE_CATEGORY_ORDER,
        )
    elif has_evidence:
        theme_cat_counts_raw: dict[str, dict[str, int]] = {t: {} for t in theme_order}
        for _, row in df.iterrows():
            theme = row["meta_theme"]
            if theme not in theme_cat_counts_raw:
                continue
            breakdown = _parse_evidence_breakdown(
                str(row.get("Evidence Category Breakdown") or "")
            )
            for cat, count in breakdown.items():
                theme_cat_counts_raw[theme][cat] = (
                    theme_cat_counts_raw[theme].get(cat, 0) + count
                )
        _add_stacked_category_bars(
            fig, theme_order, display_names, theme_cat_counts_raw,
            EVIDENCE_CATEGORY_COLORS, EVIDENCE_CATEGORY_ORDER,
        )
    elif has_verdict:
        verdict_counts = _count_verdicts(df, "meta_theme", theme_order)
        _add_stacked_category_bars(
            fig, theme_order, display_names, verdict_counts,
            VERDICT_COLORS, VERDICT_ORDER,
        )
    else:
        fig.add_trace(go.Bar(
            x=display_names,
            y=theme_totals.values,
            marker_color="#0000FF",
            text=theme_totals.values,
            textposition="outside",
        ))

    # Landscape slide layout: 16:9 ratio, legend in right-hand white space
    chart_width = 1600
    chart_height = 700
    fig.update_layout(
        title=title,
        template="plotly_white",
        width=chart_width,
        height=chart_height,
        bargap=0.3,
        yaxis=dict(
            title="Unique Source Documents" if has_doc_categories
            else ("Count" if not count_col else count_col)
        ),
        xaxis=dict(tickangle=0, tickfont=dict(size=13)),
        legend=dict(
            font=dict(size=14),
            orientation="v",
            yanchor="top", y=0.95,
            xanchor="left", x=0.72,
            bgcolor="rgba(255,255,255,0.8)",
        ),
        margin=dict(l=60, r=40, t=60, b=180),
    )

    _write_figure_outputs(fig, output_path, width=chart_width, height=chart_height)
    logger.info("Bar chart: %s", output_path)


def generate_meta_theme_drilldown(
    df: pd.DataFrame,
    topics: list[int],
    labels: dict[int, str],
    meta_map: dict[int, str],
    output_dir: Path,
    verdict_filter: set[str] | None = None,
    emergent_themes: set[str] | None = None,
) -> None:
    """Generate a per-meta-theme bar chart showing clusters within each theme.

    Each chart has one bar per cluster label, stacked by verdict strength.
    Only meta-themes with 2+ outcomes are plotted.
    """
    import plotly.graph_objects as go

    df = df.copy()
    df["cluster_id"] = topics
    df["cluster_label"] = df["cluster_id"].map(labels).fillna("Outlier")
    df["meta_theme"] = df["cluster_id"].map(meta_map).fillna("Unclustered")

    if verdict_filter and "Verdict" in df.columns:
        df = df[df["Verdict"].str.strip().str.lower().isin(verdict_filter)].copy()
        if df.empty:
            logger.info("Drilldown: no rows after verdict filter, skipping")
            return

    df = df[df["meta_theme"] != "Unclustered"]
    if df.empty:
        return

    emergent = emergent_themes or set()

    for meta_theme, group in df.groupby("meta_theme"):
        if len(group) < 2:
            continue

        has_verdict = "Verdict" in group.columns
        cluster_counts = group["cluster_label"].value_counts().sort_values(ascending=False)
        cluster_order = list(cluster_counts.index)
        display_names = [wrap_label(c, max_chars=25) for c in cluster_order]

        fig = go.Figure()

        if has_verdict:
            verdict_counts = _count_verdicts(group, "cluster_label", cluster_order)
            _add_stacked_category_bars(
                fig, cluster_order, display_names, verdict_counts,
                VERDICT_COLORS, VERDICT_ORDER,
            )
        else:
            fig.add_trace(go.Bar(
                x=display_names,
                y=cluster_counts.values,
                marker_color="#0000FF",
                text=cluster_counts.values,
                textposition="outside",
            ))

        tag = " [NEW]" if meta_theme in emergent else ""
        chart_title = f"{meta_theme}{tag} — Outcome Clusters"
        chart_width = max(900, len(cluster_order) * 160)
        chart_height = 600

        fig.update_layout(
            title=chart_title,
            template="plotly_white",
            width=chart_width,
            height=chart_height,
            bargap=0.3,
            yaxis=dict(title="Count"),
            xaxis=dict(tickangle=0, tickfont=dict(size=12)),
            legend=dict(
                font=dict(size=13),
                orientation="v",
                yanchor="top", y=0.95,
                xanchor="left", x=0.75,
                bgcolor="rgba(255,255,255,0.8)",
            ),
            margin=dict(l=60, r=40, t=60, b=160),
        )

        out_path = output_dir / f"outcome_drilldown_{slugify(meta_theme)}.png"
        _write_figure_outputs(fig, out_path, width=chart_width, height=chart_height)
        logger.debug("Drilldown: %s", out_path.name)

