#!/usr/bin/env python3
"""Export Agency & Resilience cross-project outputs.

This script queries Supabase for completed projects with description
"Agency & Resilience" and generates:
1) A QA spreadsheet with 3 tabs.
2) NotebookLM-ready markdown source files.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client


BASE_PUBLIC_PROJECT_URL = (
    "https://discoverypolicyatlas-production.up.railway.app/public/projects"
)
TARGET_DESCRIPTION = "Agency & Resilience"
INSUFFICIENT_VERDICTS = {"insufficient_evidence", "insufficient evidence"}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Export completed Agency & Resilience projects to QA spreadsheet "
            "and NotebookLM markdown sources."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root path (defaults to script-discovered root).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (defaults to scripts/exports/output).",
    )
    return parser.parse_args()


def load_config(repo_root: Path) -> Client:
    """Load env vars and create Supabase client.

    Args:
        repo_root: Path to repository root.

    Returns:
        Initialised Supabase client.

    Raises:
        ValueError: If required Supabase env vars are missing.
    """
    env_path = repo_root / "backend" / ".env"
    load_dotenv(env_path)

    import os

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url:
        raise ValueError("Missing SUPABASE_URL in backend/.env")
    if not key:
        raise ValueError("Missing SUPABASE_KEY in backend/.env")

    return create_client(url, key)


def _as_list(value: Any) -> list[Any]:
    """Normalise unknown values into lists."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    """Normalise unknown values into dictionaries."""
    if isinstance(value, dict):
        return value
    return {}


def _is_sufficient_outcome(outcome: dict[str, Any]) -> bool:
    """Return whether an outcome theme has sufficient evidence."""
    verdict = str(outcome.get("verdict_label") or "").strip().lower()
    return verdict and verdict not in INSUFFICIENT_VERDICTS


def _safe_int(value: Any) -> int:
    """Convert unknown numeric values to integer safely."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except Exception:
        return 0


def _slugify(value: str, max_len: int = 60) -> str:
    """Create a safe filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        slug = "project"
    return slug[:max_len].rstrip("_")


def _project_link(project_id: str) -> str:
    """Build public project URL from project id."""
    return f"{BASE_PUBLIC_PROJECT_URL}/{project_id}"


def _parse_iso_date(value: Any) -> str:
    """Format ISO datetime values as YYYY-MM-DD where possible."""
    if not value:
        return ""
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except Exception:
        return text[:10]


def _format_count_map(value: Any, top_n: int | None = None) -> str:
    """Format dict[str, count] as readable comma-separated string."""
    data = _as_dict(value)
    if not data:
        return "None"
    items = sorted(
        data.items(),
        key=lambda kv: (_safe_int(kv[1]), str(kv[0]).lower()),
        reverse=True,
    )
    if top_n is not None:
        items = items[:top_n]
    return ", ".join(f"{k} ({_safe_int(v)})" for k, v in items)


def _format_simple_list(value: Any) -> str:
    """Format values that may be list/scalar into display text."""
    items = [str(v).strip() for v in _as_list(value) if str(v).strip()]
    if not items:
        return "None"
    return ", ".join(items)


def _format_search_filters(search_query: dict[str, Any]) -> str:
    """Format population/setting/outcome filters into one concise field."""
    population = _as_list(search_query.get("population"))
    setting = _as_list(search_query.get("inner_setting"))
    outcome = _as_list(search_query.get("outcome"))

    parts: list[str] = []
    if population:
        parts.append(f"Population: {', '.join(map(str, population))}")
    if setting:
        parts.append(f"Setting: {', '.join(map(str, setting))}")
    if outcome:
        parts.append(f"Outcome: {', '.join(map(str, outcome))}")

    if not parts:
        return "None"
    return "; ".join(parts)


def _format_time_filter(search_query: dict[str, Any]) -> str:
    """Format time filter from search query."""
    preset = search_query.get("time_preset")
    time_from = search_query.get("time_from")
    time_to = search_query.get("time_to")

    if preset and (time_from or time_to):
        return f"{preset} ({time_from or '?'} to {time_to or '?'})"
    if preset:
        return str(preset)
    if time_from or time_to:
        return f"{time_from or '?'} to {time_to or '?'}"
    return "None"


def _markdown_escape(text: Any) -> str:
    """Escape markdown table-breaking characters."""
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").strip()
    return s.replace("|", "\\|")


def _to_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Convert rows into markdown table text."""
    if not rows:
        return "_No rows._"

    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = [
        "| " + " | ".join(_markdown_escape(row.get(col, "")) for col in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def fetch_projects(client: Client) -> list[dict[str, Any]]:
    """Fetch completed Agency & Resilience projects."""
    response = (
        client.table("analysis_projects")
        .select(
            "id,title,description,status,created_at,created_by_name,"
            "relevant_references,search_query"
        )
        .eq("description", TARGET_DESCRIPTION)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def fetch_project_data(client: Client, project: dict[str, Any]) -> dict[str, Any]:
    """Fetch all required data for one project."""
    project_id = project["id"]

    runs = (
        client.table("synthesis_runs")
        .select(
            "id,analysis_project_id,status,version,created_at,"
            "evidence_coverage,structured_briefing_data,executive_briefing,total_outcomes"
        )
        .eq("analysis_project_id", project_id)
        .order("version", desc=True)
        .execute()
        .data
        or []
    )
    run = runs[0] if runs else None

    themes: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    if run:
        run_id = run["id"]
        themes = (
            client.table("synthesis_themes")
            .select(
                "id,synthesis_run_id,theme_type,theme_name,summary_description,"
                "frequency,effect_consensus,positive_count,negative_count,null_count,"
                "countries,study_types,has_harm_warning,"
                "transferability_breakdown,linked_intervention_theme_id"
            )
            .eq("synthesis_run_id", run_id)
            .execute()
            .data
            or []
        )

        outcomes = (
            client.table("synthesis_outcome_themes")
            .select(
                "id,synthesis_run_id,outcome_name,outcome_description,"
                "effect_consensus,positive_count,negative_count,null_count,"
                "frequency,verdict_label,predicted_magnitude,"
                "primary_causal_mechanism,intervention_theme_id"
            )
            .eq("synthesis_run_id", run_id)
            .execute()
            .data
            or []
        )

    documents = (
        client.table("analysis_documents")
        .select(
            "id,analysis_project_id,title,authors,year,evidence_category,"
            "top_line,doi,citation_count,source_country,is_relevant"
        )
        .eq("analysis_project_id", project_id)
        .eq("is_relevant", True)
        .execute()
        .data
        or []
    )

    intervention_lookup = {
        t["id"]: t["theme_name"] for t in themes if t.get("theme_type") == "intervention"
    }

    return {
        "project": project,
        "run": run,
        "themes": themes,
        "outcomes": outcomes,
        "documents": documents,
        "intervention_lookup": intervention_lookup,
    }


def build_projects_tab(project_payloads: list[dict[str, Any]]) -> pd.DataFrame:
    """Build Tab 1 dataframe."""
    rows: list[dict[str, Any]] = []
    for payload in project_payloads:
        project = payload["project"]
        run = payload["run"] or {}
        themes = payload["themes"]
        outcomes = payload["outcomes"]

        evidence_coverage = _as_dict(run.get("evidence_coverage"))
        years_map = _as_dict(evidence_coverage.get("years"))
        countries_map = _as_dict(evidence_coverage.get("countries"))
        source_types_map = _as_dict(evidence_coverage.get("source_types"))
        evidence_categories_map = _as_dict(evidence_coverage.get("evidence_categories"))
        search_query = _as_dict(project.get("search_query"))

        year_keys: list[int] = []
        for k in years_map.keys():
            try:
                year_keys.append(int(str(k)))
            except Exception:
                continue
        if year_keys:
            year_range = f"{min(year_keys)}-{max(year_keys)}"
        else:
            year_range = "Unknown"

        intervention_count = sum(
            1 for t in themes if str(t.get("theme_type") or "") == "intervention"
        )
        sufficient_outcome_count = sum(1 for o in outcomes if _is_sufficient_outcome(o))

        rows.append(
            {
                "Project Title": project.get("title") or "",
                "Project Link": _project_link(project["id"]),
                "Date Run": _parse_iso_date(project.get("created_at")),
                "Run By": project.get("created_by_name") or "Unknown",
                "Relevant References": _safe_int(project.get("relevant_references")),
                "Evidence Year Range": year_range,
                "Countries Covered": len(countries_map),
                "Top 3 Countries": _format_count_map(countries_map, top_n=3),
                "Source Type Breakdown": _format_count_map(source_types_map),
                "Top Evidence Categories": _format_count_map(
                    evidence_categories_map, top_n=4
                ),
                "Intervention Theme Count": intervention_count,
                "Outcome Theme Count (sufficient evidence)": sufficient_outcome_count,
                "Search Filters": _format_search_filters(search_query),
                "Geography Filter": _format_simple_list(search_query.get("geography")),
                "Time Filter": _format_time_filter(search_query),
            }
        )

    return pd.DataFrame(rows)


def _theme_outcomes(
    outcomes: list[dict[str, Any]], intervention_theme_id: str
) -> list[dict[str, Any]]:
    """Get sufficient-evidence outcomes linked to a given intervention theme."""
    return [
        o
        for o in outcomes
        if _is_sufficient_outcome(o)
        and str(o.get("intervention_theme_id") or "") == intervention_theme_id
    ]


def _format_outcome_verdicts_and_magnitudes(outcomes: list[dict[str, Any]]) -> str:
    """Format outcome verdict+magnitude string for intervention row."""
    if not outcomes:
        return "No sufficient-evidence outcomes linked"

    parts = []
    for outcome in outcomes:
        name = str(outcome.get("outcome_name") or "Unnamed outcome")
        verdict = str(outcome.get("verdict_label") or "unknown")
        magnitude = str(outcome.get("predicted_magnitude") or "unknown")
        parts.append(f"{name}: {verdict} ({magnitude})")
    return "; ".join(parts)


def _format_pos_neg_null(item: dict[str, Any]) -> str:
    """Format positive/negative/null count fields."""
    return (
        f"{_safe_int(item.get('positive_count'))} / "
        f"{_safe_int(item.get('negative_count'))} / "
        f"{_safe_int(item.get('null_count'))}"
    )


def _extract_geo_fit_and_note(theme: dict[str, Any]) -> tuple[str, str]:
    """Extract geography context fit and explanation from transferability breakdown."""
    breakdown = _as_dict(theme.get("transferability_breakdown"))
    notes = _as_dict(breakdown.get("notes"))
    geography_fit = str(breakdown.get("geography") or "unknown")
    geography_note = str(notes.get("geography") or "No geography context note available.")
    return geography_fit, geography_note


def build_interventions_tab(project_payloads: list[dict[str, Any]]) -> pd.DataFrame:
    """Build Tab 2 dataframe."""
    rows: list[dict[str, Any]] = []

    for payload in project_payloads:
        project_title = payload["project"].get("title") or ""
        themes = payload["themes"]
        outcomes = payload["outcomes"]

        for theme in themes:
            if str(theme.get("theme_type") or "") != "intervention":
                continue

            linked_outcomes = _theme_outcomes(outcomes, str(theme["id"]))
            geography_fit, geography_note = _extract_geo_fit_and_note(theme)

            rows.append(
                {
                    "Project Title": project_title,
                    "Intervention Name": theme.get("theme_name") or "",
                    "Summary Description": theme.get("summary_description") or "",
                    "Source Documents": _safe_int(theme.get("frequency")),
                    "Effect Consensus": theme.get("effect_consensus") or "unknown",
                    "Positive / Negative / Null": _format_pos_neg_null(theme),
                    "Outcome Verdicts & Magnitudes": _format_outcome_verdicts_and_magnitudes(
                        linked_outcomes
                    ),
                    "Geography Context Fit": geography_fit,
                    "Geography Context Explanation": geography_note,
                    "Countries": _format_simple_list(theme.get("countries")),
                    "Study Types": _format_count_map(theme.get("study_types")),
                }
            )

    return pd.DataFrame(rows)


def build_outcomes_tab(project_payloads: list[dict[str, Any]]) -> pd.DataFrame:
    """Build Tab 3 dataframe."""
    rows: list[dict[str, Any]] = []
    for payload in project_payloads:
        project_title = payload["project"].get("title") or ""
        intervention_lookup = payload["intervention_lookup"]

        for outcome in payload["outcomes"]:
            if not _is_sufficient_outcome(outcome):
                continue
            linked_theme_name = intervention_lookup.get(
                str(outcome.get("intervention_theme_id") or ""), "Unknown intervention"
            )
            rows.append(
                {
                    "Project Title": project_title,
                    "Outcome Name": outcome.get("outcome_name") or "",
                    "Outcome Description": outcome.get("outcome_description") or "",
                    "Linked Intervention": linked_theme_name,
                    "Verdict": outcome.get("verdict_label") or "",
                    "Predicted Magnitude": outcome.get("predicted_magnitude") or "unknown",
                    "Effect Direction": outcome.get("effect_consensus") or "unknown",
                    "Positive / Negative / Null": _format_pos_neg_null(outcome),
                    "Causal Mechanism": outcome.get("primary_causal_mechanism") or "",
                }
            )

    return pd.DataFrame(rows)


def _autosize_excel_columns(writer: pd.ExcelWriter, sheet_names: list[str]) -> None:
    """Auto-size worksheet columns for readability."""
    for name in sheet_names:
        ws = writer.sheets[name]
        for column_cells in ws.columns:
            max_len = 0
            col_letter = column_cells[0].column_letter
            for cell in column_cells:
                value = cell.value
                if value is None:
                    continue
                max_len = max(max_len, len(str(value)))
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 80)


def generate_qa_spreadsheet(
    projects_df: pd.DataFrame,
    interventions_df: pd.DataFrame,
    outcomes_df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Generate QA spreadsheet with 3 tabs."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        projects_df.to_excel(writer, sheet_name="Projects", index=False)
        interventions_df.to_excel(writer, sheet_name="Intervention Themes", index=False)
        outcomes_df.to_excel(writer, sheet_name="Outcome Themes", index=False)
        _autosize_excel_columns(
            writer, ["Projects", "Intervention Themes", "Outcome Themes"]
        )


def _render_core_answer(structured: dict[str, Any]) -> str:
    """Render core answer section."""
    core = _as_dict(structured.get("core_answer"))
    if not core:
        return "## Core Findings\n\n_No core answer available._\n"

    answer = core.get("answer") or "_No answer available._"
    directive = core.get("directive") or "_No directive available._"
    return (
        "## Core Findings\n\n"
        f"{answer}\n\n"
        "## Recommended Direction\n\n"
        f"{directive}\n"
    )


def _render_recommendations(structured: dict[str, Any]) -> str:
    """Render recommendations section."""
    recommendations = _as_list(structured.get("recommendations"))
    if not recommendations:
        return "## Recommendations\n\n_No recommendations available._\n"

    lines = ["## Recommendations", ""]
    for idx, rec in enumerate(recommendations, start=1):
        rec_dict = _as_dict(rec)
        title = rec_dict.get("title") or f"Recommendation {idx}"
        description = rec_dict.get("description") or ""
        implementation = rec_dict.get("implementation_option") or ""
        lines.append(f"### {idx}. {title}")
        if description:
            lines.append(description)
            lines.append("")
        if implementation:
            lines.append(f"Implementation option: {implementation}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_background(structured: dict[str, Any]) -> str:
    """Render policy background section."""
    background = _as_dict(structured.get("background_section"))
    paragraphs = _as_list(background.get("paragraphs"))
    if not paragraphs:
        return "## Policy Background and Context\n\n_No background section available._\n"
    lines = ["## Policy Background and Context", ""]
    for paragraph in paragraphs:
        lines.append(str(paragraph))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_synthesis_sections(structured: dict[str, Any]) -> str:
    """Render synthesis sections from structured briefing."""
    sections = _as_list(structured.get("synthesis_sections"))
    if not sections:
        return "## Synthesis Sections\n\n_No synthesis sections available._\n"

    lines = ["## Synthesis Sections", ""]
    for section in sections:
        sec = _as_dict(section)
        title = sec.get("title") or "Untitled section"
        bullets = _as_list(sec.get("bullets"))
        paragraphs = _as_list(sec.get("paragraphs"))
        lines.append(f"### {title}")
        lines.append("")
        for bullet in bullets:
            lines.append(f"- {bullet}")
        if bullets:
            lines.append("")
        for paragraph in paragraphs:
            lines.append(str(paragraph))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_structured_interventions(structured: dict[str, Any]) -> str:
    """Render flattened interventions table section."""
    interventions = _as_list(structured.get("interventions_table"))
    if not interventions:
        return "## Interventions Table (Narrative)\n\n_No interventions table available._\n"

    lines = ["## Interventions Table (Narrative)", ""]
    for idx, entry in enumerate(interventions, start=1):
        item = _as_dict(entry)
        name = item.get("intervention_name") or f"Intervention {idx}"
        context = item.get("context") or ""
        impact = item.get("impact_narrative") or ""
        key_study = item.get("key_study_description") or ""
        lines.append(f"### {idx}. {name}")
        lines.append("")
        if context:
            lines.append(f"Context: {context}")
            lines.append("")
        if impact:
            lines.append(f"Impact narrative: {impact}")
            lines.append("")
        if key_study:
            lines.append(f"Key study: {key_study}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_theme_list(
    themes: list[dict[str, Any]], theme_type: str, title: str, include_harm: bool = False
) -> str:
    """Render issue/risk theme lists."""
    filtered = [t for t in themes if str(t.get("theme_type") or "") == theme_type]
    if not filtered:
        return f"## {title}\n\n_No {theme_type} themes available._\n"

    filtered.sort(key=lambda t: _safe_int(t.get("frequency")), reverse=True)
    lines = [f"## {title}", ""]
    for item in filtered:
        lines.append(f"### {item.get('theme_name') or 'Unnamed theme'}")
        lines.append("")
        lines.append(item.get("summary_description") or "No description available.")
        lines.append("")
        lines.append(f"Frequency: {_safe_int(item.get('frequency'))}")
        if include_harm:
            lines.append(
                f"Harm warning: {'Yes' if bool(item.get('has_harm_warning')) else 'No'}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _project_intro_block(payload: dict[str, Any]) -> str:
    """Build common project metadata block for markdown files."""
    project = payload["project"]
    run = payload["run"] or {}
    evidence = _as_dict(run.get("evidence_coverage"))
    year_map = _as_dict(evidence.get("years"))
    years: list[int] = []
    for key in year_map:
        try:
            years.append(int(str(key)))
        except Exception:
            continue
    year_range = f"{min(years)}-{max(years)}" if years else "Unknown"

    return (
        f"- Project link: {_project_link(project['id'])}\n"
        f"- Date run: {_parse_iso_date(project.get('created_at'))}\n"
        f"- Run by: {project.get('created_by_name') or 'Unknown'}\n"
        f"- Relevant references: {_safe_int(project.get('relevant_references'))}\n"
        f"- Evidence year range: {year_range}\n"
    )


def generate_notebooklm_sources(
    project_payloads: list[dict[str, Any]],
    output_dir: Path,
    projects_df: pd.DataFrame,
    interventions_df: pd.DataFrame,
    outcomes_df: pd.DataFrame,
) -> None:
    """Generate all NotebookLM markdown source files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 00 overview
    aggregate_projects = projects_df.to_dict(orient="records")
    total_relevant = sum(_safe_int(row.get("Relevant References")) for row in aggregate_projects)
    overview_lines = [
        "# Cross-Project Overview",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Total completed projects: {len(project_payloads)}",
        f"Total relevant references across projects: {total_relevant}",
        "",
        "## Project Listing",
        "",
        _to_markdown_table(
            aggregate_projects,
            [
                "Project Title",
                "Project Link",
                "Date Run",
                "Run By",
                "Relevant References",
                "Evidence Year Range",
                "Countries Covered",
                "Top 3 Countries",
                "Source Type Breakdown",
                "Top Evidence Categories",
                "Search Filters",
                "Geography Filter",
                "Time Filter",
            ],
        ),
        "",
    ]
    (output_dir / "00_cross_project_overview.md").write_text(
        "\n".join(overview_lines), encoding="utf-8"
    )

    # 01..NN per project files
    for idx, payload in enumerate(project_payloads, start=1):
        project = payload["project"]
        run = payload["run"] or {}
        themes = payload["themes"]
        structured = _as_dict(run.get("structured_briefing_data"))

        file_name = f"{idx:02d}_{_slugify(project.get('title') or 'project')}.md"
        lines = [
            f"# {project.get('title') or 'Untitled project'}",
            "",
            _project_intro_block(payload),
            "",
            _render_core_answer(structured),
            "",
            _render_recommendations(structured),
            "",
            _render_background(structured),
            "",
            _render_synthesis_sections(structured),
            "",
            _render_structured_interventions(structured),
            "",
            _render_theme_list(themes, "issue", "Issue Themes"),
            "",
            _render_theme_list(themes, "risk", "Risk Themes", include_harm=True),
            "",
        ]
        (output_dir / file_name).write_text("\n".join(lines), encoding="utf-8")

    # 12 source registry
    registry_lines = ["# Source Documents Registry", ""]
    for payload in project_payloads:
        project_title = payload["project"].get("title") or ""
        registry_lines.append(f"## {project_title}")
        registry_lines.append("")
        docs = payload["documents"]
        if not docs:
            registry_lines.append("_No relevant source documents available._")
            registry_lines.append("")
            continue
        for doc in docs:
            authors = _as_list(doc.get("authors"))
            authors_text = ", ".join(str(a) for a in authors) if authors else "Unknown"
            registry_lines.extend(
                [
                    f"- **Title:** {doc.get('title') or 'Untitled'}",
                    f"  - Authors: {authors_text}",
                    f"  - Year: {doc.get('year') or 'Unknown'}",
                    f"  - Evidence category: {doc.get('evidence_category') or 'Unknown'}",
                    f"  - Top line: {doc.get('top_line') or 'N/A'}",
                    f"  - DOI: {doc.get('doi') or 'N/A'}",
                    f"  - Citation count: {_safe_int(doc.get('citation_count'))}",
                    f"  - Source country: {doc.get('source_country') or 'Unknown'}",
                ]
            )
        registry_lines.append("")
    (output_dir / "12_source_documents_registry.md").write_text(
        "\n".join(registry_lines), encoding="utf-8"
    )

    # 13 intervention evidence analysis
    interventions_lines = ["# Intervention Evidence Analysis", ""]
    for row in interventions_df.to_dict(orient="records"):
        interventions_lines.extend(
            [
                f"## {row.get('Intervention Name')}",
                "",
                f"- Project: {row.get('Project Title')}",
                f"- Source documents: {row.get('Source Documents')}",
                f"- Effect consensus: {row.get('Effect Consensus')}",
                f"- Positive / Negative / Null: {row.get('Positive / Negative / Null')}",
                f"- Geography context fit: {row.get('Geography Context Fit')}",
                f"- Geography context explanation: {row.get('Geography Context Explanation')}",
                f"- Countries: {row.get('Countries')}",
                f"- Study types: {row.get('Study Types')}",
                "",
                "### Description",
                "",
                str(row.get("Summary Description") or "No description available."),
                "",
                "### Outcome Verdicts and Magnitudes",
                "",
                str(
                    row.get("Outcome Verdicts & Magnitudes")
                    or "No sufficient-evidence outcomes linked"
                ),
                "",
            ]
        )
    (output_dir / "13_intervention_evidence_analysis.md").write_text(
        "\n".join(interventions_lines), encoding="utf-8"
    )

    # 14 issues
    issues_lines = ["# Issues and Problem Space", ""]
    for payload in project_payloads:
        project_title = payload["project"].get("title") or ""
        issues = [
            t for t in payload["themes"] if str(t.get("theme_type") or "") == "issue"
        ]
        issues.sort(key=lambda x: _safe_int(x.get("frequency")), reverse=True)
        issues_lines.append(f"## {project_title}")
        issues_lines.append("")
        if not issues:
            issues_lines.append("_No issue themes available._")
            issues_lines.append("")
            continue
        for issue in issues:
            issues_lines.extend(
                [
                    f"### {issue.get('theme_name') or 'Unnamed issue'}",
                    "",
                    issue.get("summary_description") or "No description available.",
                    "",
                    f"Frequency: {_safe_int(issue.get('frequency'))}",
                    "",
                ]
            )
    (output_dir / "14_issues_and_problem_space.md").write_text(
        "\n".join(issues_lines), encoding="utf-8"
    )

    # 15 outcomes as dimensions
    outcomes_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes_df.to_dict(orient="records"):
        outcomes_by_name[str(row.get("Outcome Name") or "Unnamed outcome")].append(row)

    outcomes_lines = ["# Outcomes as Dimensions", ""]
    for outcome_name in sorted(outcomes_by_name.keys()):
        outcome_rows = outcomes_by_name[outcome_name]
        outcomes_lines.append(f"## {outcome_name}")
        outcomes_lines.append("")
        outcomes_lines.append(
            _to_markdown_table(
                outcome_rows,
                [
                    "Linked Intervention",
                    "Project Title",
                    "Verdict",
                    "Predicted Magnitude",
                    "Effect Direction",
                    "Positive / Negative / Null",
                    "Causal Mechanism",
                ],
            )
        )
        outcomes_lines.append("")
        outcomes_lines.append(
            f"Instances across projects/interventions: {len(outcome_rows)}"
        )
        outcomes_lines.append("")
    (output_dir / "15_outcomes_as_dimensions.md").write_text(
        "\n".join(outcomes_lines), encoding="utf-8"
    )

    # 16 risks and implementation, organised by project > intervention
    risks_lines = ["# Risks and Implementation", ""]
    for payload in project_payloads:
        project = payload["project"]
        project_title = project.get("title") or ""
        intervention_lookup = payload["intervention_lookup"]
        themes = payload["themes"]

        risk_themes = [t for t in themes if str(t.get("theme_type") or "") == "risk"]
        if not risk_themes:
            continue

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for risk in risk_themes:
            linked = str(risk.get("linked_intervention_theme_id") or "").strip()
            key = linked if linked else "__UNLINKED__"
            grouped[key].append(risk)

        risks_lines.extend(
            [
                f"## {project_title}",
                "",
                f"Project link: {_project_link(project['id'])}",
                "",
            ]
        )

        sorted_keys = sorted(
            grouped.keys(),
            key=lambda k: (
                1 if k == "__UNLINKED__" else 0,
                intervention_lookup.get(k, "Unlinked risks").lower(),
            ),
        )
        for key in sorted_keys:
            if key == "__UNLINKED__":
                heading = "Unlinked Risks"
            else:
                heading = intervention_lookup.get(key, f"Unknown intervention ({key})")
            risks_lines.append(f"### {heading}")
            risks_lines.append("")

            items = grouped[key]
            items.sort(
                key=lambda r: (
                    0 if bool(r.get("has_harm_warning")) else 1,
                    -_safe_int(r.get("frequency")),
                )
            )
            for risk in items:
                risks_lines.append(f"- **{risk.get('theme_name') or 'Unnamed risk'}**")
                risks_lines.append(
                    f"  - Description: {risk.get('summary_description') or 'No description available.'}"
                )
                risks_lines.append(f"  - Frequency: {_safe_int(risk.get('frequency'))}")
                risks_lines.append(
                    f"  - Harm warning: {'Yes' if bool(risk.get('has_harm_warning')) else 'No'}"
                )
            risks_lines.append("")

    (output_dir / "16_risks_and_implementation.md").write_text(
        "\n".join(risks_lines), encoding="utf-8"
    )


def main() -> None:
    """Run export workflow."""
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else (repo_root / "scripts" / "exports" / "output")
    )
    notebook_dir = output_dir / "notebooklm_sources"
    qa_path = output_dir / "qa_review.xlsx"

    client = load_config(repo_root)
    projects = fetch_projects(client)
    if not projects:
        raise RuntimeError(
            "No completed Agency & Resilience projects were found to export."
        )

    payloads: list[dict[str, Any]] = []
    for project in projects:
        payloads.append(fetch_project_data(client, project))

    projects_df = build_projects_tab(payloads)
    interventions_df = build_interventions_tab(payloads)
    outcomes_df = build_outcomes_tab(payloads)

    generate_qa_spreadsheet(projects_df, interventions_df, outcomes_df, qa_path)
    generate_notebooklm_sources(
        payloads, notebook_dir, projects_df, interventions_df, outcomes_df
    )

    print(f"Export complete. QA spreadsheet: {qa_path}")
    print(f"NotebookLM sources: {notebook_dir}")


if __name__ == "__main__":
    main()
