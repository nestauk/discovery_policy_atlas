#!/usr/bin/env python3
"""Cluster intervention and outcome themes from Agency & Resilience data.

Entry point that orchestrates:
1. Data loading and filtering
2. BERTopic clustering with LLM labelling (via clustering.py)
3. Visualisation generation (via cluster_viz.py)
4. Spreadsheet and console output
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("cluster_themes")

# Avoid noisy Hugging Face tokenizer fork warnings during local script runs.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from clustering import (
    POSITIVE_VERDICTS,
    REFERENCE_META_THEMES,
    SIMILARITY_THRESHOLD,
    assign_meta_themes,
    build_intervention_cluster_report,
    build_member_detail_table,
    build_outcome_cluster_report,
    compute_cross_cluster_similarity,
    find_cross_search_duplicates,
    generate_llm_labels,
    get_tfidf_label,
    llm_merge_review,
    run_bertopic,
    shorten_search,
    slugify,
)
from cluster_viz import (
    generate_meta_theme_barchart,
    generate_meta_theme_drilldown,
    generate_search_cluster_heatmap,
    generate_themed_heatmap,
    generate_umap_scatter,
)

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DEFAULT = SCRIPTS_ROOT / "output" / "ar_bottom_up"
XLSX_DEFAULT = OUTPUT_DEFAULT / "data" / "qa_review.xlsx"
ENV_PATH = Path(__file__).resolve().parents[2] / "backend" / ".env"

SHABEER = "Shabeer Rauf"
CACHE_VERSION = 1


# ---------------------------------------------------------------------------
# CLI and data loading
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster intervention & outcome themes")
    parser.add_argument("--input", type=Path, default=XLSX_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument(
        "--intv-min-cluster-size", type=int, default=3,
        help="HDBSCAN min_cluster_size for interventions (default 3)",
    )
    parser.add_argument(
        "--outcome-min-cluster-size", type=int, default=4,
        help="HDBSCAN min_cluster_size for outcomes (default 4)",
    )
    parser.add_argument(
        "--similarity-threshold", type=float, default=SIMILARITY_THRESHOLD,
        help="Cosine similarity threshold for duplicate detection (default 0.7)",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip LLM-based topic labelling (use TF-IDF keywords instead)",
    )
    parser.add_argument(
        "--no-viz", action="store_true",
        help="Skip visualisation generation",
    )
    parser.add_argument(
        "--no-merge", action="store_true",
        help="Skip LLM-based cluster merge review",
    )
    parser.add_argument(
        "--from-cache", action="store_true",
        help="Load cached clustering results (skip clustering/LLM, regenerate outputs only).",
    )
    return parser.parse_args()


def load_filtered_data(
    xlsx_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load xlsx and filter to Shabeer's searches only."""
    projects = pd.read_excel(xlsx_path, sheet_name="Projects")
    interventions = pd.read_excel(xlsx_path, sheet_name="Intervention Themes")
    outcomes = pd.read_excel(xlsx_path, sheet_name="Outcome Themes")

    shabeer_titles = set(projects[projects["Run By"] == SHABEER]["Project Title"])

    interventions = interventions[interventions["Project Title"].isin(shabeer_titles)].copy()
    outcomes = outcomes[outcomes["Project Title"].isin(shabeer_titles)].copy()

    interventions["_intervention_key"] = _build_intervention_key_series(
        interventions, "Intervention Name"
    )
    outcomes["_linked_intervention_key"] = _build_intervention_key_series(
        outcomes, "Linked Intervention"
    )

    # Keep only interventions with a comparable or matching geography context
    geo_col = "Geography Context Fit"
    valid_geo = {"comparable", "match"}
    before_geo = len(interventions)
    interventions = interventions[
        interventions[geo_col].str.lower().str.strip().isin(valid_geo)
    ].copy()
    logger.info("Geography filter: kept %d/%d interventions (required %s in %s)",
                len(interventions), before_geo, geo_col, valid_geo)

    # Drop outcomes linked to filtered-out interventions
    surviving_interventions = set(interventions["_intervention_key"])
    before_out = len(outcomes)
    outcomes = outcomes[
        outcomes["_linked_intervention_key"].isin(surviving_interventions)
    ].copy()
    logger.info("Geography filter: kept %d/%d outcomes (linked to surviving interventions)",
                len(outcomes), before_out)

    interventions = interventions.reset_index(drop=True)
    outcomes = outcomes.reset_index(drop=True)

    logger.info("Loaded %d interventions, %d outcomes (Shabeer only)", len(interventions), len(outcomes))
    return projects, interventions, outcomes


def _normalise_key_part(series: pd.Series) -> pd.Series:
    """Normalise string key components used for row/link identities."""
    return series.fillna("").astype(str).str.strip()


def _build_intervention_key_series(df: pd.DataFrame, name_col: str) -> pd.Series:
    """Build a stable per-project intervention key."""
    project = _normalise_key_part(df["Project Title"])
    name = _normalise_key_part(df[name_col])
    return project + "||" + name


def _build_row_signature(series: pd.Series) -> str:
    """Hash an ordered sequence of row identifiers for cache validation."""
    digest = hashlib.sha256()
    for value in series.tolist():
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _build_cache_metadata(
    input_path: Path,
    interventions: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> dict[str, object]:
    """Capture the filtered dataset identity used to produce cached outputs."""
    input_path = input_path.resolve()
    stat = input_path.stat()

    intervention_rows = (
        _build_intervention_key_series(interventions, "Intervention Name")
        + "||"
        + _normalise_key_part(interventions["Summary Description"])
    )
    outcome_rows = (
        _normalise_key_part(outcomes["Project Title"])
        + "||"
        + _normalise_key_part(outcomes["Outcome Name"])
        + "||"
        + _normalise_key_part(outcomes["Linked Intervention"])
        + "||"
        + _normalise_key_part(outcomes["Outcome Description"])
    )

    return {
        "cache_version": CACHE_VERSION,
        "input_path": str(input_path),
        "input_mtime_ns": stat.st_mtime_ns,
        "intervention_count": len(interventions),
        "outcome_count": len(outcomes),
        "intervention_signature": _build_row_signature(intervention_rows),
        "outcome_signature": _build_row_signature(outcome_rows),
    }


def _validate_cache_metadata(
    cached_metadata: dict[str, object] | None,
    current_metadata: dict[str, object],
    cache_file: Path,
) -> None:
    """Reject cache reuse when the filtered input data no longer matches."""
    if not cached_metadata:
        raise ValueError(
            f"Cache at {cache_file} has no metadata. Run without --from-cache first."
        )

    mismatches: list[str] = []
    for key in (
        "cache_version",
        "input_path",
        "input_mtime_ns",
        "intervention_count",
        "outcome_count",
        "intervention_signature",
        "outcome_signature",
    ):
        if cached_metadata.get(key) != current_metadata.get(key):
            mismatches.append(key)

    if mismatches:
        mismatch_str = ", ".join(mismatches)
        raise ValueError(
            f"Cache at {cache_file} does not match the current filtered input "
            f"({mismatch_str}). Run without --from-cache first."
        )


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def write_detailed_report(
    log_path: Path,
    intv_report: pd.DataFrame,
    out_cross_cutting: pd.DataFrame,
    out_single_search: pd.DataFrame,
    intv_dupes: pd.DataFrame,
    outcome_dupes: pd.DataFrame,
) -> None:
    """Write detailed cluster report to a log file."""
    with open(log_path, "w") as f:
        # Intervention families
        f.write("=" * 70 + "\n")
        f.write("INTERVENTION FAMILIES\n")
        f.write("=" * 70 + "\n")
        for _, row in intv_report.iterrows():
            cid = row["Cluster ID"]
            tag = " (outliers)" if cid == -1 else ""
            f.write(f"\n  [{cid}{tag}] {row['Cluster Label']}\n")
            f.write(f"    {row['Member Count']} interventions across {row['Search Count']} searches | "
                    f"{row['Total Source Documents']} source docs\n")
            f.write(f"    Effect: {row['Effect Consensus']} | Geo: {row['Geography Fit']}\n")
            for m in row["Member Interventions"].split(" | "):
                f.write(f"      - {m}\n")

        # Outcome families
        f.write(f"\n{'=' * 70}\n")
        f.write("OUTCOME FAMILIES — CROSS-CUTTING (2+ searches)\n")
        f.write("=" * 70 + "\n")
        for _, row in out_cross_cutting.iterrows():
            f.write(f"\n  [{row['Cluster ID']}] {row['Cluster Label']}\n")
            f.write(f"    {row['Member Count']} outcomes across {row['Search Count']} searches\n")
            f.write(f"    Verdicts: {row['Verdict Distribution']}\n")
            f.write(f"    Magnitudes: {row['Magnitude Distribution']}\n")
            for m in row["Member Outcomes"].split(" | "):
                f.write(f"      - {m}\n")
        if not out_single_search.empty:
            f.write(f"\n  ({len(out_single_search)} single-search/outlier clusters omitted)\n")

        # Duplicates
        for dupes, label in [(intv_dupes, "INTERVENTIONS"), (outcome_dupes, "OUTCOMES")]:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"CROSS-SEARCH DUPLICATES — {label}\n")
            f.write(f"{'=' * 70}\n")
            if dupes.empty:
                f.write("  No cross-search pairs above threshold.\n")
                continue
            seen: set[tuple[str, str]] = set()
            for _, row in dupes.iterrows():
                key = tuple(sorted([row["Item A"], row["Item B"]]))
                if key in seen:
                    continue
                seen.add(key)
                f.write(f"\n  [{row['Cosine Similarity']:.3f}] {row['Item A']}\n")
                f.write(f"      ({shorten_search(row['Search A'])})\n")
                f.write(f"    ≈ {row['Item B']}\n")
                f.write(f"      ({shorten_search(row['Search B'])})\n")

    logger.info("Detailed report: %s", log_path)


# ---------------------------------------------------------------------------
# Per-meta-theme CSV export
# ---------------------------------------------------------------------------


def export_meta_theme_csvs(
    df: pd.DataFrame,
    topics: list[int],
    labels: dict[int, str],
    meta_map: dict[int, str],
    output_dir: Path,
    verdict_filter: set[str] | None = None,
) -> None:
    """Write one CSV per meta-theme with outcome-level detail."""
    df = df.copy()
    df["Cluster ID"] = topics
    df["Cluster Label"] = df["Cluster ID"].map(labels).fillna("Outlier")
    df["Meta-Theme"] = df["Cluster ID"].map(meta_map).fillna("Unclustered")

    if verdict_filter and "Verdict" in df.columns:
        df = df[df["Verdict"].str.strip().str.lower().isin(verdict_filter)].copy()

    df = df[df["Meta-Theme"] != "Unclustered"]
    if df.empty:
        logger.info("No outcomes to export after filtering.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Columns to include in each CSV
    detail_cols = [
        "Cluster Label", "Outcome Name", "Outcome Description",
        "Linked Intervention", "Project Title", "Verdict",
        "Predicted Magnitude", "Effect Direction", "Causal Mechanism",
        "Source Studies",
    ]
    detail_cols = [c for c in detail_cols if c in df.columns]

    for meta_theme, group in df.groupby("Meta-Theme"):
        out = group[detail_cols].sort_values(
            ["Cluster Label", "Outcome Name"]
        ).reset_index(drop=True)
        path = output_dir / f"{slugify(meta_theme)}.csv"
        out.to_csv(path, index=False)
        logger.debug("%s (%d outcomes)", path.name, len(out))


# ---------------------------------------------------------------------------
# Emergent meta-theme log
# ---------------------------------------------------------------------------


def _write_emergent_themes_log(
    output_dir: Path,
    intv_new_themes: dict[str, dict[str, str]],
    intv_emergent: set[str],
    out_new_themes: dict[str, dict[str, str]],
    out_emergent: set[str],
) -> None:
    """Write definitions of [NEW] emergent meta-themes to a log file."""
    if not intv_emergent and not out_emergent:
        return

    sections = [
        ("Intervention Meta-Themes", intv_emergent, intv_new_themes),
        ("Outcome Meta-Themes", out_emergent, out_new_themes),
    ]

    log_path = output_dir / "emergent_meta_themes.log"
    with open(log_path, "a") as f:
        f.write(f"\n{'=' * 70}\n")
        f.write(f"Emergent Meta-Themes — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 70}\n")

        for heading, emergent, new_themes in sections:
            if not emergent:
                continue
            f.write(f"\n--- {heading} ---\n")
            for theme in sorted(emergent):
                detail = new_themes.get(theme, {})
                f.write(f"\n  [NEW] {theme}\n")
                f.write(f"    Definition: {detail.get('definition', 'N/A')}\n")
                f.write(f"    Reasoning:  {detail.get('reasoning', 'N/A')}\n")

        f.write("\n")

    logger.info("Emergent meta-theme definitions logged to: %s", log_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _configure_logging() -> None:
    """Set readable defaults for local script runs."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Keep the pipeline logs visible while suppressing noisy library request logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(data, f)
    logger.debug("Cache saved: %s", path)


def _load_cache(path: Path) -> dict:
    with open(path, "rb") as f:
        data = pickle.load(f)
    logger.debug("Cache loaded: %s", path)
    return data


def main() -> None:
    args = parse_args()

    _configure_logging()

    # Set up output subdirectories
    data_dir = args.output / "data"
    viz_dir = args.output / "viz"
    intv_viz_dir = viz_dir / "interventions"
    out_viz_dir = viz_dir / "outcomes"
    drilldown_dir = out_viz_dir / "drilldowns"
    logs_dir = args.output / "logs"
    cache_dir = args.output / ".cache"
    for d in [data_dir, intv_viz_dir, out_viz_dir, drilldown_dir, logs_dir, cache_dir]:
        d.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "cluster_cache.pkl"

    # Load OpenAI key from backend .env
    load_dotenv(ENV_PATH)
    if not args.no_llm and not os.environ.get("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not found, falling back to TF-IDF labels")
        args.no_llm = True

    _, interventions, outcomes = load_filtered_data(args.input)
    cache_metadata = _build_cache_metadata(args.input, interventions, outcomes)

    if args.from_cache:
        if not cache_file.exists():
            raise FileNotFoundError(
                f"No cache found at {cache_file}. Run without --from-cache first."
            )
        cache = _load_cache(cache_file)
        _validate_cache_metadata(cache.get("metadata"), cache_metadata, cache_file)
        intervention_embeddings = cache["intervention_embeddings"]
        outcome_embeddings = cache["outcome_embeddings"]
        intv_topics = cache["intv_topics"]
        intv_labels = cache["intv_labels"]
        intv_cluster_sim = cache["intv_cluster_sim"]
        out_topics = cache["out_topics"]
        out_labels = cache["out_labels"]
        out_cluster_sim = cache["out_cluster_sim"]
        intv_meta_map = cache.get("intv_meta_map", {})
        out_meta_map = cache.get("out_meta_map", {})
        intv_emergent = cache.get("intv_emergent", set())
        out_emergent = cache.get("out_emergent", set())
    else:
        logger.info("Loading embedding model...")
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        intervention_docs = interventions["Summary Description"].fillna("").tolist()
        outcome_docs = outcomes["Outcome Description"].fillna("").tolist()

        logger.info("Encoding texts...")
        intervention_embeddings = embedding_model.encode(intervention_docs, show_progress_bar=False)
        outcome_embeddings = embedding_model.encode(outcome_docs, show_progress_bar=False)

        use_llm = not args.no_llm

        # --- Intervention clustering ---
        logger.info("Clustering interventions...")
        intv_model, intv_topics = run_bertopic(
            intervention_docs, embedding_model,
            min_cluster_size=args.intv_min_cluster_size,
            label="Interventions",
        )

        if use_llm:
            logger.info("Generating LLM labels for intervention clusters...")
            intv_labels = generate_llm_labels(
                intv_model, intv_topics, intervention_docs,
                interventions["Intervention Name"].tolist(),
            )
        else:
            intv_labels = {cid: get_tfidf_label(intv_model, cid) for cid in set(intv_topics)}

        intv_cluster_sim = compute_cross_cluster_similarity(intv_topics, intervention_embeddings)

        if use_llm and not args.no_merge:
            logger.info("Reviewing intervention clusters for merges...")
            intv_topics, intv_labels = llm_merge_review(
                intv_topics, interventions["Intervention Name"].tolist(),
                intervention_docs, intv_labels, intv_cluster_sim,
            )
            intv_cluster_sim = compute_cross_cluster_similarity(intv_topics, intervention_embeddings)

        # --- Outcome clustering ---
        logger.info("Clustering outcomes...")
        out_model, out_topics = run_bertopic(
            outcome_docs, embedding_model,
            min_cluster_size=args.outcome_min_cluster_size,
            label="Outcomes",
        )

        if use_llm:
            logger.info("Generating LLM labels for outcome clusters...")
            out_labels = generate_llm_labels(
                out_model, out_topics, outcome_docs,
                outcomes["Outcome Name"].tolist(),
            )
        else:
            out_labels = {cid: get_tfidf_label(out_model, cid) for cid in set(out_topics)}

        out_cluster_sim = compute_cross_cluster_similarity(out_topics, outcome_embeddings)

        if use_llm and not args.no_merge:
            logger.info("Reviewing outcome clusters for merges...")
            out_topics, out_labels = llm_merge_review(
                out_topics, outcomes["Outcome Name"].tolist(),
                outcome_docs, out_labels, out_cluster_sim,
            )
            out_cluster_sim = compute_cross_cluster_similarity(out_topics, outcome_embeddings)

        # --- Meta-theme assignment ---
        intv_meta_map: dict[int, str] = {}
        out_meta_map: dict[int, str] = {}
        intv_emergent: set[str] = set()
        out_emergent: set[str] = set()
        if use_llm:
            logger.info("Assigning meta-themes...")
            logger.info("Interventions:")
            intv_meta_map, intv_new_theme_details = assign_meta_themes(
                intv_labels, intv_topics, intervention_docs,
                interventions["Intervention Name"].tolist(),
            )
            ref_names = set(REFERENCE_META_THEMES.keys())
            intv_emergent = {
                t for t in set(intv_meta_map.values()) if t not in ref_names
            }
            logger.info("Outcomes:")
            out_meta_map, out_new_theme_details = assign_meta_themes(
                out_labels, out_topics, outcome_docs,
                outcomes["Outcome Name"].tolist(),
            )
            out_emergent = {
                t for t in set(out_meta_map.values()) if t not in ref_names
            }

            # Log emergent meta-theme definitions
            _write_emergent_themes_log(
                logs_dir,
                intv_new_theme_details, intv_emergent,
                out_new_theme_details, out_emergent,
            )

        # Save cache for future --from-cache runs
        _save_cache(cache_file, {
            "metadata": cache_metadata,
            "intervention_embeddings": intervention_embeddings,
            "outcome_embeddings": outcome_embeddings,
            "intv_topics": intv_topics,
            "intv_labels": intv_labels,
            "intv_cluster_sim": intv_cluster_sim,
            "out_topics": out_topics,
            "out_labels": out_labels,
            "out_cluster_sim": out_cluster_sim,
            "intv_meta_map": intv_meta_map,
            "out_meta_map": out_meta_map,
            "intv_emergent": intv_emergent,
            "out_emergent": out_emergent,
        })

    # --- Reports (always rebuilt from current data + cached cluster assignments) ---
    intv_cluster_report = build_intervention_cluster_report(
        interventions, intv_topics, intv_labels,
    )
    intv_detail = build_member_detail_table(
        interventions, intv_topics, "Intervention Name", "Summary Description"
    )
    out_cross_cutting, out_single_search = build_outcome_cluster_report(
        outcomes, out_topics, out_labels, min_searches=2,
    )
    out_detail = build_member_detail_table(
        outcomes, out_topics, "Outcome Name", "Outcome Description"
    )

    # --- Pairwise cross-search duplicate detection ---
    logger.info("Finding cross-search duplicates...")
    intv_dupes = find_cross_search_duplicates(
        interventions, intervention_embeddings, "Intervention Name",
        args.similarity_threshold,
    )
    logger.info("Interventions: %d pairs above %s", len(intv_dupes), args.similarity_threshold)

    outcome_dupes = find_cross_search_duplicates(
        outcomes, outcome_embeddings, "Outcome Name",
        args.similarity_threshold,
    )
    logger.info("Outcomes: %d pairs above %s", len(outcome_dupes), args.similarity_threshold)

    # --- Write spreadsheet ---
    xlsx_out = data_dir / "theme_clusters.xlsx"
    with pd.ExcelWriter(xlsx_out, engine="openpyxl") as writer:
        intv_cluster_report.to_excel(writer, sheet_name="Intervention Families", index=False)
        intv_detail.to_excel(writer, sheet_name="Intervention Detail", index=False)
        intv_cluster_sim.to_excel(writer, sheet_name="Intervention Cluster Sim", index=False)
        intv_dupes.to_excel(writer, sheet_name="Intervention Duplicates", index=False)
        out_cross_cutting.to_excel(writer, sheet_name="Outcome Families (cross-cut)", index=False)
        out_single_search.to_excel(writer, sheet_name="Outcome Families (single)", index=False)
        out_detail.to_excel(writer, sheet_name="Outcome Detail", index=False)
        out_cluster_sim.to_excel(writer, sheet_name="Outcome Cluster Sim", index=False)
        outcome_dupes.to_excel(writer, sheet_name="Outcome Duplicates", index=False)

    logger.info("Spreadsheet: %s", xlsx_out)

    # --- Visualisations ---
    if not args.no_viz:
        logger.info("Generating visualisations...")

        generate_umap_scatter(
            intervention_embeddings, intv_topics,
            interventions["Intervention Name"].tolist(),
            interventions["Project Title"].tolist(),
            intv_labels,
            "Intervention Themes — UMAP Clusters",
            intv_viz_dir / "umap.png",
        )

        generate_umap_scatter(
            outcome_embeddings, out_topics,
            outcomes["Outcome Name"].tolist(),
            outcomes["Project Title"].tolist(),
            out_labels,
            "Outcome Themes — UMAP Clusters",
            out_viz_dir / "umap.png",
        )

        generate_search_cluster_heatmap(
            interventions, intv_topics, intv_labels,
            count_col="Source Documents",
            title="Interventions: Search Query × Cluster (source doc count)",
            output_path=intv_viz_dir / "cluster_heatmap.png",
            embeddings=intervention_embeddings,
        )

        generate_search_cluster_heatmap(
            outcomes, out_topics, out_labels,
            count_col=None,
            title="Outcomes: Search Query × Cluster (count)",
            output_path=out_viz_dir / "cluster_heatmap.png",
            embeddings=outcome_embeddings,
        )

        # Meta-theme heatmaps and bar charts (requires LLM assignment)
        if intv_meta_map and out_meta_map:
            logger.info("Generating meta-theme heatmaps...")

            generate_themed_heatmap(
                interventions, intv_topics, intv_meta_map,
                count_col="Source Documents",
                title="Interventions: Search Query × Meta-Theme (source doc count)",
                output_path=intv_viz_dir / "themed_heatmap.png",
                emergent_themes=intv_emergent,
            )

            generate_themed_heatmap(
                outcomes, out_topics, out_meta_map,
                count_col=None,
                title="Outcomes: Search Query × Meta-Theme (all verdicts)",
                output_path=out_viz_dir / "themed_heatmap.png",
                emergent_themes=out_emergent,
            )

            generate_themed_heatmap(
                outcomes, out_topics, out_meta_map,
                count_col=None,
                title="Outcomes: Search Query × Meta-Theme (positive verdicts only)",
                output_path=out_viz_dir / "themed_positive_heatmap.png",
                verdict_filter=POSITIVE_VERDICTS,
                emergent_themes=out_emergent,
            )

            logger.info("Generating meta-theme bar charts...")

            generate_meta_theme_barchart(
                interventions, intv_topics, intv_meta_map,
                count_col="Source Documents",
                title="Interventions by Meta-Theme (source doc count)",
                output_path=intv_viz_dir / "themed_bar.png",
                emergent_themes=intv_emergent,
            )

            generate_meta_theme_barchart(
                outcomes, out_topics, out_meta_map,
                count_col=None,
                title="Outcomes by Meta-Theme (all verdicts)",
                output_path=out_viz_dir / "themed_bar.png",
                emergent_themes=out_emergent,
            )

            generate_meta_theme_barchart(
                outcomes, out_topics, out_meta_map,
                count_col=None,
                title="Outcomes by Meta-Theme (positive verdicts only)",
                output_path=out_viz_dir / "themed_positive_bar.png",
                verdict_filter=POSITIVE_VERDICTS,
                emergent_themes=out_emergent,
            )

            logger.info("Generating per-meta-theme drilldown charts...")
            generate_meta_theme_drilldown(
                outcomes, out_topics, out_labels, out_meta_map,
                output_dir=drilldown_dir,
                verdict_filter=POSITIVE_VERDICTS,
                emergent_themes=out_emergent,
            )

    # --- Per-meta-theme CSVs (positive outcomes) ---
    if out_meta_map:
        logger.info("Exporting per-meta-theme outcome CSVs...")
        csv_dir = data_dir / "outcome_by_meta_theme"
        export_meta_theme_csvs(
            outcomes, out_topics, out_labels, out_meta_map,
            output_dir=csv_dir,
            verdict_filter=POSITIVE_VERDICTS,
        )

    # --- Detailed report (to file) and console summary ---
    write_detailed_report(
        logs_dir / "cluster_report.log",
        intv_cluster_report, out_cross_cutting, out_single_search,
        intv_dupes, outcome_dupes,
    )

    n_intv_clusters = len(intv_cluster_report[intv_cluster_report["Cluster ID"] != -1])
    n_out_cross = len(out_cross_cutting)
    n_out_single = len(out_single_search)
    logger.info(
        "Summary: %d intervention families, %d cross-cutting outcome families "
        "(%d single-search), %d intervention duplicate pairs, %d outcome duplicate pairs",
        n_intv_clusters, n_out_cross, n_out_single, len(intv_dupes), len(outcome_dupes),
    )


if __name__ == "__main__":
    main()
