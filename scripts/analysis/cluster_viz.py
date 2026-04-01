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


# ---------------------------------------------------------------------------
# Author & Institution analysis
# ---------------------------------------------------------------------------

MIN_AUTHOR_PAPERS = 2
TOP_N_AUTHORS = 5

# Cross-theme thresholds for the all-themes bar charts
CROSS_THEME_AUTHOR_MIN = 4
CROSS_THEME_INSTITUTION_MIN = 6

# Semantic colour mapping for meta-themes in cross-theme bar charts.
# Falls back to _NESTA_THEME_OVERFLOW for themes not in this map.
META_THEME_COLOURS: dict[str, str] = {
    # Reference themes
    "Climate & place-based adaptation": "#18A48C",       # Green (Nesta) — nature/environment
    "Community resilience & social capital": "#0F294A",   # Navy (Nesta) — trust/foundations
    "Mental health, behaviour & individual capability": "#A59BEE",  # Violet (Nesta) — wellbeing
    "Early years & family foundations": "#FDB633",        # Yellow (Nesta) — warmth/nurture
    "Digital & information resilience": "#97D9E3",        # Aqua (Nesta) — digital/tech
    "Institutional & governance reform": "#D2C9C0",       # Sand (Nesta) — institutions/neutral
    # Common emergent themes
    "Economic security & livelihoods": "#E07B54",         # Muted terracotta — economic warmth
    "Community safety & emergency resilience": "#EB003B", # Red (Nesta) — safety/emergency
    "Economic systems & market reform": "#7A9CC6",        # Steel blue — systems/markets
}

# Overflow colours for any themes not in the semantic map above
_NESTA_THEME_OVERFLOW = [
    "#F6A4B7",  # Pink (Nesta)
    "#646363",  # Dark Grey (Nesta)
    "#8BB174",  # Sage green
    "#C490B0",  # Dusty rose
    "#9A1BBE",  # Purple (Nesta)
    "#FF6E47",  # Orange (Nesta)
]


def _parse_doc_entities(raw: str) -> list[tuple[str, str]]:
    """Parse 'doc_id::entity | ...' into (doc_id, entity) pairs.

    Works for both author and institution columns which share the same format.
    """
    if not raw or raw.strip() == "":
        return []
    pairs = []
    for part in raw.split(" | "):
        part = part.strip()
        if "::" in part:
            doc_id, entity = part.split("::", 1)
            pairs.append((doc_id.strip(), entity.strip()))
    return pairs


def _has_column_data(df: pd.DataFrame, col: str) -> bool:
    """Check whether a DataFrame column exists and has non-empty data."""
    return (
        col in df.columns
        and df[col].notna().any()
        and (df[col].astype(str).str.strip() != "").any()
    )


def _collect_institution_names(df: pd.DataFrame) -> set[str]:
    """Collect all institution names from the DataFrame for author dedup."""
    names: set[str] = set()
    col = "Source Doc Institutions"
    if col not in df.columns:
        return names
    for raw in df[col].dropna():
        for _, institution in _parse_doc_entities(str(raw)):
            if institution:
                names.add(institution)
    return names


def _build_entity_theme_data(
    df: pd.DataFrame,
    entity_col: str,
    category_col: str = "Source Doc Categories",
    exclude_names: set[str] | None = None,
) -> dict[str, dict[str, dict[str, set[str]]]]:
    """Build {meta_theme: {entity_name: {category: {doc_ids}}}} from the DataFrame.

    Counts distinct papers per entity per meta-theme, tracking evidence category.
    If exclude_names is provided, any entity whose name appears in the set is skipped
    (used to filter organisational authors that also appear as institutions).
    """
    result: dict[str, dict[str, dict[str, set[str]]]] = {}
    missing_count = 0
    excluded_count = 0
    skip = exclude_names or set()

    for _, row in df.iterrows():
        meta_theme = row.get("meta_theme", "")
        if not meta_theme or meta_theme == "Unclustered":
            continue

        entity_pairs = _parse_doc_entities(str(row.get(entity_col) or ""))
        if not entity_pairs:
            missing_count += 1
            continue

        cat_pairs = _parse_doc_categories(str(row.get(category_col) or ""))
        doc_to_cat = {doc_id: cat for doc_id, cat in cat_pairs}

        if meta_theme not in result:
            result[meta_theme] = {}

        for doc_id, entity_name in entity_pairs:
            if not entity_name:
                continue
            if entity_name in skip:
                excluded_count += 1
                continue
            if entity_name not in result[meta_theme]:
                result[meta_theme][entity_name] = {}
            cat = doc_to_cat.get(doc_id, "Unknown / Insufficient information")
            if cat not in result[meta_theme][entity_name]:
                result[meta_theme][entity_name][cat] = set()
            result[meta_theme][entity_name][cat].add(doc_id)

    if missing_count:
        logger.warning(
            "Author/institution analysis: %d intervention rows had no %s data",
            missing_count, entity_col,
        )
    if excluded_count:
        logger.info(
            "Author dedup: excluded %d author-document entries that matched institution names",
            excluded_count,
        )

    return result


def _top_entities_for_theme(
    theme_data: dict[str, dict[str, set[str]]],
    min_papers: int = MIN_AUTHOR_PAPERS,
    top_n: int = TOP_N_AUTHORS,
) -> list[tuple[str, int, dict[str, int]]]:
    """Return top entities for a theme as [(name, total_papers, {cat: count}), ...].

    Filters to entities with >= min_papers distinct papers, takes top_n.
    """
    entity_totals: list[tuple[str, int, dict[str, int]]] = []
    for entity_name, cat_docs in theme_data.items():
        total = sum(len(docs) for docs in cat_docs.values())
        if total < min_papers:
            continue
        cat_counts = {cat: len(docs) for cat, docs in cat_docs.items()}
        entity_totals.append((entity_name, total, cat_counts))

    entity_totals.sort(key=lambda x: (-x[1], x[0]))
    return entity_totals[:top_n]


def generate_author_charts(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
    output_dir: Path,
    emergent_themes: set[str] | None = None,
    min_papers: int = MIN_AUTHOR_PAPERS,
    top_n: int = TOP_N_AUTHORS,
) -> None:
    """Generate per-meta-theme horizontal bar charts of top authors.

    Excludes organisational authors (names that also appear as institutions).
    """
    institution_names = _collect_institution_names(df)
    _generate_entity_charts(
        df, topics, meta_map, output_dir,
        entity_col="Source Doc Authors",
        entity_label="Authors",
        file_prefix="top_authors",
        emergent_themes=emergent_themes,
        exclude_names=institution_names,
        min_papers=min_papers,
        top_n=top_n,
    )


def generate_institution_charts(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
    output_dir: Path,
    emergent_themes: set[str] | None = None,
    min_papers: int = MIN_AUTHOR_PAPERS,
    top_n: int = TOP_N_AUTHORS,
) -> None:
    """Generate per-meta-theme horizontal bar charts of top institutions."""
    _generate_entity_charts(
        df, topics, meta_map, output_dir,
        entity_col="Source Doc Institutions",
        entity_label="Institutions",
        file_prefix="top_institutions",
        emergent_themes=emergent_themes,
        min_papers=min_papers,
        top_n=top_n,
    )


def _generate_entity_charts(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
    output_dir: Path,
    entity_col: str,
    entity_label: str,
    file_prefix: str,
    emergent_themes: set[str] | None = None,
    exclude_names: set[str] | None = None,
    min_papers: int = MIN_AUTHOR_PAPERS,
    top_n: int = TOP_N_AUTHORS,
) -> None:
    """Generate per-meta-theme horizontal stacked bar charts for an entity type."""
    import plotly.graph_objects as go

    if not _has_column_data(df, entity_col):
        logger.info("Skipping %s charts — no %s data available", entity_label, entity_col)
        return

    df = df.copy()
    df["cluster_id"] = topics
    df["meta_theme"] = df["cluster_id"].map(meta_map).fillna("Unclustered")
    df = df[df["meta_theme"] != "Unclustered"]

    if df.empty:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    emergent = emergent_themes or set()

    entity_data = _build_entity_theme_data(df, entity_col, exclude_names=exclude_names)

    charts_generated = 0
    for meta_theme in sorted(entity_data.keys()):
        top = _top_entities_for_theme(entity_data[meta_theme], min_papers=min_papers, top_n=top_n)
        if not top:
            continue

        # Reverse for horizontal bar (top entity at top)
        top = list(reversed(top))
        names = [wrap_label(t[0], max_chars=40) for t in top]

        # Collect all categories present
        all_cats: set[str] = set()
        for _, _, cat_counts in top:
            all_cats.update(cat_counts.keys())
        ordered_cats = _ordered_items(all_cats, EVIDENCE_CATEGORY_ORDER)

        fig = go.Figure()
        for cat in ordered_cats:
            values = [t[2].get(cat, 0) for t in top]
            if sum(values) == 0:
                continue
            fig.add_trace(go.Bar(
                y=names,
                x=values,
                name=cat,
                marker_color=EVIDENCE_CATEGORY_COLORS.get(cat, "#CCCCCC"),
                orientation="h",
            ))

        tag = " [NEW]" if meta_theme in emergent else ""
        chart_width = 1000
        chart_height = max(400, len(top) * 60 + 150)
        fig.update_layout(
            title=f"{meta_theme}{tag} — Top {entity_label} (by distinct papers)",
            template="plotly_white",
            barmode="stack",
            width=chart_width,
            height=chart_height,
            xaxis=dict(title="Distinct Papers"),
            yaxis=dict(tickfont=dict(size=10)),
            legend=dict(
                font=dict(size=10),
                orientation="v",
                yanchor="top", y=0.99,
                xanchor="left", x=1.02,
            ),
            margin=dict(l=250, r=40, t=60, b=60),
        )

        out_path = output_dir / f"{file_prefix}_{slugify(meta_theme)}.png"
        _write_figure_outputs(fig, out_path, width=chart_width, height=chart_height)
        charts_generated += 1

    logger.info("%s charts: %d generated in %s", entity_label, charts_generated, output_dir)


def generate_cross_theme_entity_barchart(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
    output_dir: Path,
    entity_col: str,
    entity_label: str,
    output_filename: str,
    min_papers: int,
    emergent_themes: set[str] | None = None,
    exclude_names: set[str] | None = None,
) -> None:
    """Generate a cross-theme stacked bar chart for authors or institutions.

    Each bar = one entity, stacked by meta-theme (Nesta colours).
    Only entities with >= min_papers total distinct papers across all themes are shown.
    """
    import plotly.graph_objects as go

    if not _has_column_data(df, entity_col):
        logger.info("Skipping %s cross-theme bar chart — no data", entity_label)
        return

    df = df.copy()
    df["cluster_id"] = topics
    df["meta_theme"] = df["cluster_id"].map(meta_map).fillna("Unclustered")
    df = df[df["meta_theme"] != "Unclustered"]

    if df.empty:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    emergent = emergent_themes or set()

    entity_data = _build_entity_theme_data(df, entity_col, exclude_names=exclude_names)

    # Count total distinct papers per entity across all themes
    entity_totals: dict[str, int] = {}
    entity_theme_counts: dict[str, dict[str, int]] = {}
    for theme, theme_data in entity_data.items():
        for entity_name, cat_docs in theme_data.items():
            paper_count = len({doc for docs in cat_docs.values() for doc in docs})
            if entity_name not in entity_totals:
                entity_totals[entity_name] = 0
                entity_theme_counts[entity_name] = {}
            entity_totals[entity_name] += paper_count
            entity_theme_counts[entity_name][theme] = paper_count

    # Filter to entities meeting the threshold
    qualifying = {
        name: total for name, total in entity_totals.items() if total >= min_papers
    }

    if not qualifying:
        logger.info(
            "No %s met the %d-paper threshold for cross-theme bar chart",
            entity_label, min_papers,
        )
        return

    # Sort by total descending, then reverse for horizontal bar (top at top)
    sorted_entities = sorted(qualifying.keys(), key=lambda n: qualifying[n])
    display_names = [wrap_label(n, max_chars=45) for n in sorted_entities]

    # Determine theme order by total papers across all qualifying entities
    theme_totals: dict[str, int] = {}
    for entity in sorted_entities:
        for theme, count in entity_theme_counts[entity].items():
            theme_totals[theme] = theme_totals.get(theme, 0) + count
    theme_order = sorted(theme_totals.keys(), key=lambda t: -theme_totals[t])

    # Assign colours: use semantic map first, overflow for unknown themes
    overflow_idx = 0
    theme_colours: dict[str, str] = {}
    for theme in theme_order:
        if theme in META_THEME_COLOURS:
            theme_colours[theme] = META_THEME_COLOURS[theme]
        else:
            theme_colours[theme] = _NESTA_THEME_OVERFLOW[
                overflow_idx % len(_NESTA_THEME_OVERFLOW)
            ]
            overflow_idx += 1

    fig = go.Figure()
    for theme in theme_order:
        values = [entity_theme_counts[e].get(theme, 0) for e in sorted_entities]
        if sum(values) == 0:
            continue
        tag = " [NEW]" if theme in emergent else ""
        fig.add_trace(go.Bar(
            y=display_names,
            x=values,
            name=f"{theme}{tag}",
            marker_color=theme_colours[theme],
            orientation="h",
        ))

    chart_width = 1200
    chart_height = max(500, len(sorted_entities) * 45 + 200)
    fig.update_layout(
        title=f"{entity_label} Across Meta-Themes ({min_papers}+ distinct papers)",
        template="plotly_white",
        barmode="stack",
        width=chart_width,
        height=chart_height,
        xaxis=dict(title="Distinct Papers"),
        yaxis=dict(tickfont=dict(size=10)),
        legend=dict(
            font=dict(size=10),
            orientation="v",
            yanchor="top", y=0.99,
            xanchor="left", x=1.02,
        ),
        margin=dict(l=280, r=40, t=60, b=60),
    )

    out_path = output_dir / output_filename
    _write_figure_outputs(fig, out_path, width=chart_width, height=chart_height)
    logger.info("Cross-theme %s bar chart: %s", entity_label.lower(), out_path)


def build_author_summary_table(
    df: pd.DataFrame,
    topics: list[int],
    meta_map: dict[int, str],
) -> pd.DataFrame:
    """Build a summary table of authors/institutions per meta-theme for xlsx export."""
    df = df.copy()
    df["cluster_id"] = topics
    df["meta_theme"] = df["cluster_id"].map(meta_map).fillna("Unclustered")
    df = df[df["meta_theme"] != "Unclustered"]

    rows: list[dict[str, object]] = []
    institution_names = _collect_institution_names(df)

    for entity_col, entity_type, exclude in [
        ("Source Doc Authors", "Author", institution_names),
        ("Source Doc Institutions", "Institution", None),
    ]:
        if not _has_column_data(df, entity_col):
            continue

        entity_data = _build_entity_theme_data(df, entity_col, exclude_names=exclude)

        for meta_theme in sorted(entity_data.keys()):
            for entity_name, cat_docs in entity_data[meta_theme].items():
                total = sum(len(docs) for docs in cat_docs.values())
                if total < MIN_AUTHOR_PAPERS:
                    continue
                cat_breakdown = ", ".join(
                    f"{count} {cat}"
                    for cat, count in sorted(
                        ((c, len(d)) for c, d in cat_docs.items()),
                        key=lambda x: -x[1],
                    )
                )
                rows.append({
                    "Meta-Theme": meta_theme,
                    "Entity Type": entity_type,
                    "Name": entity_name,
                    "Paper Count": total,
                    "Evidence Categories": cat_breakdown,
                })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(
            ["Meta-Theme", "Entity Type", "Paper Count"],
            ascending=[True, True, False],
        ).reset_index(drop=True)

    return result

