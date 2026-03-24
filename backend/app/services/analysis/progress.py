from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.services.analysis.schemas import AnalysisProjectProgress
from app.services.vectorization import vectorization_service

logger = logging.getLogger(__name__)

# User-facing synthesis steps (1–4) from map_synthesis_stage_to_step. ETA durations for the
# same steps live in frontend/lib/analysisTimingHeuristic.ts (SYNTHESIS_STEP_SECONDS); keep in sync
# if this model or ordering changes.
SYNTHESIS_STEP_LABELS = {
    1: "Identifying themes",
    2: "Preparing evidence for synthesis",
    3: "Writing executive briefing",
    4: "Finalising recommendations",
}

STEP_ONE_STAGE_KEYS = frozenset(
    {
        "create_canonical_concepts",
        "process_issue_themes",
        "process_intervention_themes",
        "process_outcome_themes",
        "process_risk_themes",
    }
)

STEP_FOUR_BRIEFING_KEYS = frozenset(
    {
        "briefing/core_answer",
        "briefing/recommendations",
        "briefing/build_structured",
    }
)


def map_synthesis_stage_to_step(stage_name: Optional[str]) -> int:
    """Map granular synthesis stage keys to consolidated user-facing steps."""
    key = (stage_name or "").strip()
    if not key:
        return 1

    if key.startswith("briefing/"):
        if key in STEP_FOUR_BRIEFING_KEYS:
            return 4
        return 3

    if key == "generate_briefing":
        return 3

    if key in STEP_ONE_STAGE_KEYS:
        return 1

    # Remaining stages map to evidence-preparation work.
    return 2


def _parse_iso_datetime(value: object) -> Optional[datetime]:
    """Safely parse an ISO timestamp string into a datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _estimate_stage_started_at_iso(timing_row: dict) -> Optional[str]:
    """Estimate when a stage started by subtracting its duration from its finish time."""
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
    normalized_status = (project_status or "").strip().lower()
    if normalized_status != "synthesising":
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
