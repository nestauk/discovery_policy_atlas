#!/usr/bin/env python3
"""Compare UK vs Global evidence for Agency & Resilience (ar_top_down).

Generates side-by-side visualisations of intervention themes, evidence
category composition, semantic gap analysis, and outcome verdict comparison.

This is a standalone comparison script — distinct from the BERTopic clustering
analysis in cluster_themes.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from clustering import (
    EVIDENCE_CATEGORY_COLORS,
    EVIDENCE_CATEGORY_ORDER,
    VERDICT_COLORS,
    VERDICT_ORDER,
    wrap_label,
)
from cluster_viz import _parse_evidence_breakdown, _write_figure_outputs

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GAP_THRESHOLD = 0.5  # cosine similarity below this = "unmatched" global theme

# Nesta brand colours
NESTA_BLUE = "#0000FF"
NESTA_YELLOW = "#FDB633"


VALID_GEO_FITS = {"match", "comparable"}


def load_data(xlsx_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    interventions = pd.read_excel(xlsx_path, sheet_name="Intervention Themes")
    outcomes = pd.read_excel(xlsx_path, sheet_name="Outcome Themes")

    # Filter to interventions with match/comparable geography context fit
    before = len(interventions)
    interventions = interventions[
        interventions["Geography Context Fit"]
        .str.strip()
        .str.lower()
        .isin(VALID_GEO_FITS)
    ].copy()
    dropped = before - len(interventions)
    if dropped:
        logger.info(
            "Filtered %d intervention(s) with mismatched geography context fit",
            dropped,
        )

    # Keep only outcomes linked to surviving interventions
    valid_interventions = set(interventions["Intervention Name"])
    before_out = len(outcomes)
    outcomes = outcomes[
        outcomes["Linked Intervention"].isin(valid_interventions)
    ].copy()
    dropped_out = before_out - len(outcomes)
    if dropped_out:
        logger.info(
            "Filtered %d outcome(s) linked to dropped interventions", dropped_out
        )

    return interventions, outcomes


# ---------------------------------------------------------------------------
# Viz 1: Stacked evidence bar charts per geography
# ---------------------------------------------------------------------------


def _build_evidence_cat_counts(
    df: pd.DataFrame,
) -> tuple[list[str], list[str], dict[str, dict[str, int]]]:
    """Parse evidence breakdowns and return theme order + category counts."""
    theme_totals: dict[str, int] = {}
    theme_cats: dict[str, dict[str, int]] = {}

    for _, row in df.iterrows():
        name = row["Intervention Name"]
        breakdown = _parse_evidence_breakdown(
            str(row.get("Evidence Category Breakdown") or "")
        )
        total = sum(breakdown.values())
        theme_totals[name] = total
        theme_cats[name] = breakdown

    # Sort descending by total docs
    theme_order = sorted(theme_totals, key=lambda t: theme_totals[t], reverse=True)
    display_names = [wrap_label(t, max_chars=25) for t in theme_order]
    return theme_order, display_names, theme_cats


def generate_intervention_evidence_chart(
    df: pd.DataFrame, geography: str, output_path: Path
) -> None:
    """Stacked bar chart of intervention themes by evidence category."""
    subset = df[df["Search Geography"] == geography].copy()
    if subset.empty:
        logger.warning("No interventions for geography=%s", geography)
        return

    theme_order, display_names, theme_cats = _build_evidence_cat_counts(subset)

    fig = go.Figure()

    # Collect all categories present
    all_cats = set()
    for cats in theme_cats.values():
        all_cats.update(cats.keys())

    ordered_cats = [c for c in EVIDENCE_CATEGORY_ORDER if c in all_cats]
    ordered_cats += sorted(all_cats - set(ordered_cats))

    for cat in ordered_cats:
        values = [theme_cats[t].get(cat, 0) for t in theme_order]
        if sum(values) == 0:
            continue
        fig.add_trace(
            go.Bar(
                x=display_names,
                y=values,
                name=cat,
                marker_color=EVIDENCE_CATEGORY_COLORS.get(cat, "#CCCCCC"),
            )
        )

    geo_label = "UK" if geography == "UK" else "Global"
    fig.update_layout(
        barmode="stack",
        title=f"Intervention Themes by Evidence Category ({geo_label})",
        template="plotly_white",
        width=1600,
        height=700,
        yaxis=dict(title="Source Documents"),
        xaxis=dict(tickangle=0, tickfont=dict(size=13)),
        legend=dict(
            font=dict(size=14),
            orientation="v",
            yanchor="top",
            y=0.95,
            xanchor="left",
            x=0.72,
            bgcolor="rgba(255,255,255,0.8)",
        ),
        margin=dict(l=60, r=40, t=60, b=180),
        bargap=0.3,
    )

    _write_figure_outputs(fig, output_path, width=1600, height=700)
    logger.info("Wrote %s", output_path)


# ---------------------------------------------------------------------------
# Viz 2: Evidence category composition comparison
# ---------------------------------------------------------------------------


def generate_evidence_composition_chart(
    df: pd.DataFrame, output_path: Path
) -> None:
    """Grouped bar chart comparing evidence category totals UK vs Global."""
    records: list[dict[str, object]] = []
    for geography in ["UK", "All"]:
        subset = df[df["Search Geography"] == geography]
        combined: dict[str, int] = {}
        for _, row in subset.iterrows():
            for cat, count in _parse_evidence_breakdown(
                str(row.get("Evidence Category Breakdown") or "")
            ).items():
                combined[cat] = combined.get(cat, 0) + count
        for cat, count in combined.items():
            records.append(
                {"Geography": "UK" if geography == "UK" else "Global",
                 "Category": cat, "Count": count}
            )

    comp_df = pd.DataFrame(records)
    if comp_df.empty:
        return

    # Order categories by EVIDENCE_CATEGORY_ORDER
    all_cats = set(comp_df["Category"])
    cat_order = [c for c in EVIDENCE_CATEGORY_ORDER if c in all_cats]
    cat_order += sorted(all_cats - set(cat_order))
    display_cats = [wrap_label(c, max_chars=22) for c in cat_order]

    fig = go.Figure()
    for geo, color in [("UK", NESTA_BLUE), ("Global", NESTA_YELLOW)]:
        geo_data = comp_df[comp_df["Geography"] == geo]
        values = []
        for cat in cat_order:
            match = geo_data[geo_data["Category"] == cat]
            values.append(int(match["Count"].sum()) if not match.empty else 0)
        fig.add_trace(
            go.Bar(x=display_cats, y=values, name=geo, marker_color=color)
        )

    fig.update_layout(
        barmode="group",
        title="Evidence Category Composition: UK vs Global",
        template="plotly_white",
        width=1600,
        height=700,
        yaxis=dict(title="Total Source Documents"),
        xaxis=dict(tickangle=0, tickfont=dict(size=13)),
        legend=dict(font=dict(size=14)),
        margin=dict(l=60, r=40, t=60, b=180),
        bargap=0.3,
    )

    _write_figure_outputs(fig, output_path, width=1600, height=700)
    logger.info("Wrote %s", output_path)


# ---------------------------------------------------------------------------
# Viz 3: Semantic gap heatmap
# ---------------------------------------------------------------------------


def _build_embedding_text(row: pd.Series) -> str:
    """Combine intervention name + description for richer embeddings."""
    name = str(row.get("Intervention Name") or "")
    desc = str(row.get("Summary Description") or "")
    return f"{name}: {desc}" if desc and desc != "nan" else name


def generate_gap_heatmap(
    df: pd.DataFrame, output_dir: Path
) -> pd.DataFrame:
    """Cosine similarity heatmap: Global interventions vs UK interventions.

    Returns the gap summary DataFrame for downstream use (LLM assessment).
    """
    uk_df = df[df["Search Geography"] == "UK"].reset_index(drop=True)
    glb_df = df[df["Search Geography"] == "All"].reset_index(drop=True)

    uk_names = uk_df["Intervention Name"].tolist()
    glb_names = glb_df["Intervention Name"].tolist()

    if not uk_names or not glb_names:
        logger.warning("Need both UK and Global interventions for gap analysis")
        return pd.DataFrame()

    # Embed using name + description for richer semantic comparison
    uk_texts = [_build_embedding_text(row) for _, row in uk_df.iterrows()]
    glb_texts = [_build_embedding_text(row) for _, row in glb_df.iterrows()]

    logger.info("Loading sentence-transformers model for gap analysis...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    uk_emb = model.encode(uk_texts)
    glb_emb = model.encode(glb_texts)

    sim_matrix = cosine_similarity(glb_emb, uk_emb)  # (n_global, n_uk)

    uk_labels = [wrap_label(n, max_chars=25) for n in uk_names]
    glb_labels = [wrap_label(n, max_chars=30) for n in glb_names]

    fig = go.Figure(
        data=go.Heatmap(
            z=sim_matrix,
            x=uk_labels,
            y=glb_labels,
            colorscale="RdYlGn",
            zmin=0,
            zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in sim_matrix],
            texttemplate="%{text}",
            textfont=dict(size=11),
            colorbar=dict(title="Cosine<br>Similarity"),
        )
    )

    fig.update_layout(
        title="Semantic Similarity: Global Interventions vs UK Interventions",
        template="plotly_white",
        width=1400,
        height=800,
        xaxis=dict(title="UK Intervention Themes", tickangle=45, tickfont=dict(size=11)),
        yaxis=dict(title="Global Intervention Themes", tickfont=dict(size=11)),
        margin=dict(l=300, r=40, t=60, b=250),
    )

    heatmap_path = output_dir / "gap_similarity_heatmap.png"
    _write_figure_outputs(fig, heatmap_path, width=1400, height=800)
    logger.info("Wrote %s", heatmap_path)

    # Gap summary CSV
    gap_rows = []
    for i, name in enumerate(glb_names):
        max_sim = float(sim_matrix[i].max())
        best_uk_idx = int(sim_matrix[i].argmax())
        gap_rows.append({
            "Global Intervention": name,
            "Max Similarity to UK": round(max_sim, 3),
            "Best UK Match": uk_names[best_uk_idx],
            "Gap Flag": "UNMATCHED" if max_sim < GAP_THRESHOLD else "",
        })
    gap_df = pd.DataFrame(gap_rows).sort_values("Max Similarity to UK")
    gap_csv = output_dir / "gap_summary.csv"
    gap_df.to_csv(gap_csv, index=False)
    logger.info("Wrote %s", gap_csv)

    # Log unmatched themes
    unmatched = gap_df[gap_df["Gap Flag"] == "UNMATCHED"]
    if not unmatched.empty:
        logger.info(
            "Unmatched global themes (similarity < %.2f):\n%s",
            GAP_THRESHOLD,
            unmatched[["Global Intervention", "Max Similarity to UK", "Best UK Match"]].to_string(index=False),
        )
    else:
        logger.info("All global themes matched a UK theme above threshold %.2f", GAP_THRESHOLD)

    return gap_df


# ---------------------------------------------------------------------------
# LLM gap assessment
# ---------------------------------------------------------------------------


def _format_intervention_context(row: pd.Series) -> str:
    """Format a single intervention row into rich context for the LLM."""
    parts = [
        f"**{row['Intervention Name']}**",
        f"Description: {row.get('Summary Description', 'N/A')}",
        f"Source Documents: {row.get('Source Documents', 'N/A')}",
        f"Evidence Categories: {row.get('Evidence Category Breakdown', 'N/A')}",
        f"Effect Consensus: {row.get('Effect Consensus', 'N/A')}",
        f"Positive/Negative/Null: {row.get('Positive / Negative / Null', 'N/A')}",
        f"Outcome Verdicts: {row.get('Outcome Verdicts & Magnitudes', 'N/A')}",
        f"Geography Fit: {row.get('Geography Context Fit', 'N/A')}",
        f"Countries: {row.get('Countries', 'N/A')}",
        f"Study Types: {row.get('Study Types', 'N/A')}",
    ]
    return "\n".join(parts)


def generate_llm_gap_report(
    interventions_df: pd.DataFrame,
    outcomes_df: pd.DataFrame,
    gap_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Use LLM to assess evidence gaps and recommend next steps."""
    import openai

    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    uk_df = interventions_df[interventions_df["Search Geography"] == "UK"]
    glb_df = interventions_df[interventions_df["Search Geography"] == "All"]

    # Build rich context blocks
    uk_context = "\n\n".join(
        _format_intervention_context(row) for _, row in uk_df.iterrows()
    )
    global_context = "\n\n".join(
        _format_intervention_context(row) for _, row in glb_df.iterrows()
    )

    # Outcome context
    uk_outcomes = outcomes_df[outcomes_df["Search Geography"] == "UK"]
    global_outcomes = outcomes_df[outcomes_df["Search Geography"] == "All"]

    uk_outcome_summary = "\n".join(
        f"- {row['Outcome Name']}: {row['Verdict']} ({row['Predicted Magnitude']}) "
        f"linked to '{row['Linked Intervention']}'"
        for _, row in uk_outcomes.iterrows()
    )
    global_outcome_summary = "\n".join(
        f"- {row['Outcome Name']}: {row['Verdict']} ({row['Predicted Magnitude']}) "
        f"linked to '{row['Linked Intervention']}'"
        for _, row in global_outcomes.iterrows()
    )

    # Gap table
    gap_table = gap_df.to_string(index=False)

    prompt = f"""You are a policy research analyst. You have been given the results of two Policy Atlas
searches on "Interventions to strengthen agency and resilience" — one filtered to UK evidence only,
and one searching globally. Your task is to analyse the evidence gaps between UK and Global results.

## COSINE SIMILARITY GAP ANALYSIS

The following table shows each Global intervention theme, its maximum cosine similarity to any UK
intervention theme (using intervention name + description embeddings), and the best UK match.
Themes flagged UNMATCHED (similarity < {GAP_THRESHOLD}) have no close UK equivalent.

{gap_table}

## UK INTERVENTION THEMES ({len(uk_df)} themes, from UK-filtered search)

{uk_context}

## UK OUTCOME THEMES ({len(uk_outcomes)} outcomes)

{uk_outcome_summary}

## GLOBAL INTERVENTION THEMES ({len(glb_df)} themes, from global search)

{global_context}

## GLOBAL OUTCOME THEMES ({len(global_outcomes)} outcomes)

{global_outcome_summary}

## YOUR ANALYSIS

Please produce a structured markdown report with the following sections:

### 1. Executive Summary
A 3-4 sentence overview of the key evidence gaps between UK and Global results.

### 2. Gap-by-Gap Assessment
For each UNMATCHED global theme (sorted by similarity, lowest first):
- **Theme name** (cosine similarity score)
- **What the global evidence shows**: summarise the intervention, its evidence base, and outcomes
- **Is this a real UK evidence gap or a query artifact?**: Your assessment of whether:
  (a) The UK genuinely lacks research/policy evidence in this area
  (b) The evidence likely exists in the UK but the search query framing didn't surface it
  (c) The topic may not be relevant to the UK context
- **Justification**: Why you think this, based on the evidence context provided
- **Suggested next steps**: Specific search queries or approaches to test whether UK evidence exists

### 3. Themes with Partial Overlap
For matched themes (similarity > {GAP_THRESHOLD}) where the UK evidence is notably thinner
or lower-quality than the global evidence — highlight any significant disparities.

### 4. Overall Evidence Quality Comparison
Comment on the systematic differences in evidence rigour between UK and Global results
(e.g. the UK's heavy reliance on qualitative/contextual evidence vs global RCTs and systematic reviews).

### 5. Recommended Priority Actions
Rank the top 3-5 evidence gaps by importance for a UK funder interested in agency & resilience,
and suggest concrete next steps (refined search queries, specific databases to check, expert networks to consult).

Be analytical and honest. If a gap looks like a query artifact rather than a real gap, say so.
"""

    logger.info("Calling LLM for gap assessment (gpt-5.4-mini)...")
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    report_content = response.choices[0].message.content

    # Wrap with metadata header
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    full_report = (
        f"# UK vs Global Evidence Gap Analysis\n\n"
        f"Generated: {timestamp}\n"
        f"Model: gpt-4.1-mini\n"
        f"Gap threshold: cosine similarity < {GAP_THRESHOLD}\n"
        f"Embedding model: all-MiniLM-L6-v2 (name + description)\n\n"
        f"---\n\n"
        f"{report_content}\n"
    )

    report_path = output_dir / "gap_analysis_report.md"
    report_path.write_text(full_report, encoding="utf-8")
    logger.info("Wrote %s", report_path)


# ---------------------------------------------------------------------------
# Viz 4: Outcome verdict comparison
# ---------------------------------------------------------------------------


def generate_verdict_comparison(
    outcomes_df: pd.DataFrame, output_path: Path
) -> None:
    """Grouped bar chart of outcome verdict distributions UK vs Global."""
    records: list[dict[str, object]] = []
    for geography in ["UK", "All"]:
        subset = outcomes_df[outcomes_df["Search Geography"] == geography]
        counts = subset["Verdict"].str.strip().str.lower().value_counts()
        for verdict, count in counts.items():
            records.append({
                "Geography": "UK" if geography == "UK" else "Global",
                "Verdict": verdict,
                "Count": count,
            })

    vdf = pd.DataFrame(records)
    if vdf.empty:
        return

    all_verdicts = set(vdf["Verdict"])
    verdict_order = [v for v in VERDICT_ORDER if v in all_verdicts]
    verdict_order += sorted(all_verdicts - set(verdict_order))
    display_verdicts = [v.replace("_", " ").title() for v in verdict_order]

    fig = go.Figure()
    for geo, color in [("UK", NESTA_BLUE), ("Global", NESTA_YELLOW)]:
        geo_data = vdf[vdf["Geography"] == geo]
        values = []
        for v in verdict_order:
            match = geo_data[geo_data["Verdict"] == v]
            values.append(int(match["Count"].sum()) if not match.empty else 0)
        fig.add_trace(go.Bar(x=display_verdicts, y=values, name=geo, marker_color=color))

    fig.update_layout(
        barmode="group",
        title="Outcome Verdict Distribution: UK vs Global",
        template="plotly_white",
        width=1200,
        height=600,
        yaxis=dict(title="Number of Outcomes"),
        xaxis=dict(tickangle=0, tickfont=dict(size=13)),
        legend=dict(font=dict(size=14)),
        margin=dict(l=60, r=40, t=60, b=120),
        bargap=0.3,
    )

    _write_figure_outputs(fig, output_path, width=1200, height=600)
    logger.info("Wrote %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UK vs Global evidence comparison")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("../output/ar_top_down/data/qa_review.xlsx"),
        help="Path to qa_review.xlsx",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../output/ar_top_down/comparison"),
        help="Output directory for comparison visualisations",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM gap assessment (useful if no OpenAI key available)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    logger.info("Loading data from %s", args.input)
    interventions, outcomes = load_data(args.input)

    logger.info(
        "Interventions: %d UK, %d Global",
        len(interventions[interventions["Search Geography"] == "UK"]),
        len(interventions[interventions["Search Geography"] == "All"]),
    )

    # 1. Intervention evidence bar charts (one per geography)
    generate_intervention_evidence_chart(
        interventions, "UK", args.output / "intervention_evidence_uk.png"
    )
    generate_intervention_evidence_chart(
        interventions, "All", args.output / "intervention_evidence_global.png"
    )

    # 2. Evidence category composition comparison
    generate_evidence_composition_chart(
        interventions, args.output / "evidence_category_comparison.png"
    )

    # 3. Semantic gap heatmap
    gap_df = generate_gap_heatmap(interventions, args.output)

    # 4. Outcome verdict comparison
    generate_verdict_comparison(
        outcomes, args.output / "outcome_verdict_comparison.png"
    )

    # 5. LLM gap assessment
    if not args.no_llm and not gap_df.empty:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
        load_dotenv(env_path)
        generate_llm_gap_report(interventions, outcomes, gap_df, args.output)
    elif args.no_llm:
        logger.info("Skipping LLM gap assessment (--no-llm)")

    logger.info("Done. Outputs in %s", args.output)


if __name__ == "__main__":
    main()
