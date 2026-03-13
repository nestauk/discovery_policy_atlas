from __future__ import annotations

import logging
from datetime import datetime, timedelta
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


def map_synthesis_stage_to_step(stage_name: Optional[str]) -> int:
    """Map granular synthesis stage keys to consolidated user-facing steps."""
    key = (stage_name or "").strip()
    if not key:
        return 1

    if key.startswith("briefing/"):
        if key in {
            "briefing/core_answer",
            "briefing/recommendations",
            "briefing/build_structured",
        }:
            return 4
        return 3

    if key == "generate_briefing":
        return 3

    step_one_keys = {
        "create_canonical_concepts",
        "process_issue_themes",
        "process_intervention_themes",
        "process_outcome_themes",
        "process_risk_themes",
    }
    if key in step_one_keys:
        return 1

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
        return 2

    return 2


def _parse_iso_datetime(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _estimate_stage_started_at_iso(timing_row: dict) -> Optional[str]:
    created_at = _parse_iso_datetime(timing_row.get("created_at"))
    if created_at is None:
        return None

    duration_seconds_raw = timing_row.get("duration_seconds")
    try:
        duration_seconds = (
            float(duration_seconds_raw) if duration_seconds_raw is not None else 0.0
        )
    except (TypeError, ValueError):
        duration_seconds = 0.0

    estimated_started_at = created_at - timedelta(seconds=max(0.0, duration_seconds))
    return estimated_started_at.isoformat()


def _get_latest_synthesis_stage_timing(project_id: str) -> Optional[dict]:
    """Fetch the latest persisted synthesis timing row for a project."""
    try:
        timing_res = (
            vectorization_service.supabase.table("pipeline_timings")
            .select("stage_name,created_at,duration_seconds")
            .eq("project_id", project_id)
            .eq("pipeline_type", "synthesis")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not timing_res.data:
            return None
        return timing_res.data[0]
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

    latest_stage_timing = _get_latest_synthesis_stage_timing(project_id) or {}
    latest_stage_name = latest_stage_timing.get("stage_name")
    stage_started_at = _estimate_stage_started_at_iso(latest_stage_timing)
    step_index = map_synthesis_stage_to_step(latest_stage_name)

    return AnalysisProjectProgress(
        stage_label=SYNTHESIS_STEP_LABELS[step_index],
        step_index=step_index,
        stage_started_at=stage_started_at,
    )
