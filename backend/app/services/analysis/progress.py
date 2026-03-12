from __future__ import annotations

import logging
from typing import Optional

from app.services.analysis.schemas import AnalysisProjectProgress
from app.services.vectorization import vectorization_service

logger = logging.getLogger(__name__)

SYNTHESIS_STEP_TOTAL = 4
SYNTHESIS_STEP_LABELS = {
    1: "Identifying themes",
    2: "Preparing evidence for synthesis",
    3: "Writing executive briefing",
    4: "Finalising recommendations",
}
SYNTHESIS_STEP_DESCRIPTIONS = {
    1: "Grouping extracted findings into coherent issue, intervention, outcome, and risk themes.",
    2: "Aggregating evidence, retrieving supporting citations, and preparing synthesis-ready context.",
    3: "Drafting the executive briefing narrative from the synthesised evidence.",
    4: "Finalising recommendations and assembling the structured final briefing output.",
}


def map_synthesis_stage_to_step(stage_name: Optional[str]) -> tuple[int, str]:
    """Map granular synthesis stage keys to consolidated user-facing steps."""
    key = (stage_name or "").strip()
    if not key:
        return 1, "synthesis/unknown"

    if key.startswith("briefing/"):
        if key in {
            "briefing/core_answer",
            "briefing/recommendations",
            "briefing/build_structured",
        }:
            return 4, key
        return 3, key

    if key == "generate_briefing":
        return 3, key

    step_one_keys = {
        "create_canonical_concepts",
        "process_issue_themes",
        "process_intervention_themes",
        "process_outcome_themes",
        "process_risk_themes",
    }
    if key in step_one_keys:
        return 1, key

    step_two_keys = {
        "load_raw_extractions",
        "compute_evidence_coverage",
        "build_aggregated_tables",
        "compute_impact_syntheses",
        "retrieve_evidence_for_themes",
        "retrieve_evidence_for_issues",
        "retrieve_evidence_for_outcomes",
        "apply_rcs_to_theme_evidence",
        "apply_rcs_to_issue_evidence",
        "apply_rcs_to_outcome_evidence",
    }
    if key in step_two_keys:
        return 2, key

    return 2, key


def _get_latest_synthesis_stage_name(project_id: str) -> Optional[str]:
    """Fetch the latest persisted synthesis stage name for a project."""
    try:
        timing_res = (
            vectorization_service.supabase.table("pipeline_timings")
            .select("stage_name")
            .eq("project_id", project_id)
            .eq("pipeline_type", "synthesis")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not timing_res.data:
            return None
        return timing_res.data[0].get("stage_name")
    except Exception as e:
        logger.warning(
            "Failed to read latest synthesis timing stage for project %s: %s",
            project_id,
            e,
        )
        return None


def get_synthesis_project_progress(
    project_id: str, project_status: str
) -> Optional[AnalysisProjectProgress]:
    """Build user-facing progress details for synthesising projects."""
    if project_status != "synthesising":
        return None

    latest_stage_name = _get_latest_synthesis_stage_name(project_id)
    step_index, stage_key = map_synthesis_stage_to_step(latest_stage_name)

    # Keep synthesis below completion state until status flips to completed.
    percent = min(95, 65 + (step_index - 1) * 10)

    return AnalysisProjectProgress(
        stage_key=stage_key,
        stage_label=SYNTHESIS_STEP_LABELS[step_index],
        stage_description=SYNTHESIS_STEP_DESCRIPTIONS[step_index],
        step_index=step_index,
        step_total=SYNTHESIS_STEP_TOTAL,
        percent=percent,
    )
