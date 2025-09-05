"""
Supabase-based caching for synthesis agent runs.

This module handles reading from and writing to the synthesis caching tables:
- synthesis_runs: Main run records with executive briefing
- synthesis_themes: Theme definitions (issues and interventions)  
- theme_assignments: Mappings from extraction_id to theme_id
"""

import uuid
from datetime import datetime
from typing import Dict, Optional

from app.core.config import settings
from app.services.synthesis.schemas import (
    SynthesisSummary,
    KeyIssue,
    PolicyIntervention,
)
from supabase import create_client


def get_supabase():
    """Get Supabase client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


async def read_cached_summary(project_id: str) -> Optional[SynthesisSummary]:
    """
    Read cached synthesis summary for a project.

    Returns None if no cached result exists, otherwise returns populated SynthesisSummary.
    """
    supabase = get_supabase()

    # Get most recent completed synthesis run
    runs_res = (
        supabase.table("synthesis_runs")
        .select("*")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return None

    run = runs_res.data[0]
    run_id = run["id"]

    # Get all themes for this run
    themes_res = (
        supabase.table("synthesis_themes")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    if not themes_res.data:
        return None

    themes = themes_res.data

    # Separate issues and interventions
    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]

    # Convert to Pydantic models
    key_issues = []
    for theme in issue_themes:
        key_issues.append(
            KeyIssue(
                issue_theme=theme["theme_name"],
                summary_description=theme["summary_description"] or "",
                frequency=theme["frequency"] or 0,
                source_doc_ids=theme["source_doc_ids"] or [],
                justification=theme["justification"] or "",
            )
        )

    interventions = []
    for theme in intervention_themes:
        interventions.append(
            PolicyIntervention(
                intervention_name=theme["theme_name"],
                brief_description=theme["summary_description"] or "",
                impact_summary=theme["impact_summary"] or "",
                frequency=theme["frequency"] or 0,
                supporting_doc_ids=theme["source_doc_ids"] or [],
                justification=theme["justification"] or "",
            )
        )

    return SynthesisSummary(
        executive_briefing=run["executive_briefing"] or "",
        key_issues=key_issues,
        interventions=interventions,
    )


async def write_run_from_state(project_id: str, final_state: Dict) -> None:
    """
    Write synthesis agent final state to cache tables.

    Creates records in synthesis_runs, synthesis_themes, and theme_assignments
    based on the agent's final state.
    """
    supabase = get_supabase()

    # Create synthesis run record
    run_id = str(uuid.uuid4())
    run_data = {
        "id": run_id,
        "analysis_project_id": project_id,
        "status": "completed",
        "version": 2,
        "executive_briefing": final_state.get("executive_briefing", ""),
        "model_info": {
            "theme_iteration": final_state.get("theme_iteration", 0),
            "total_issues": len(final_state.get("aggregated_issues", [])),
            "total_interventions": len(final_state.get("aggregated_interventions", [])),
        },
        "state_after_clustering": {
            "issue_clusters": final_state.get("issue_clusters", {}),
            "intervention_clusters": final_state.get("intervention_clusters", {}),
            "issue_theme_names": final_state.get("issue_theme_names", {}),
            "intervention_theme_names": final_state.get("intervention_theme_names", {}),
        },
        "state_after_critique": {
            "theme_critique": final_state.get("theme_critique"),
            "aggregated_issues": [
                issue.dict() for issue in final_state.get("aggregated_issues", [])
            ],
            "aggregated_interventions": [
                intv.dict() for intv in final_state.get("aggregated_interventions", [])
            ],
        },
    }

    supabase.table("synthesis_runs").upsert(
        run_data, on_conflict="analysis_project_id"
    ).execute()

    # Create theme records and collect assignments
    theme_assignments = []

    # Process issue themes
    for issue in final_state.get("aggregated_issues", []):
        theme_id = str(uuid.uuid4())
        theme_data = {
            "id": theme_id,
            "synthesis_run_id": run_id,
            "theme_type": "issue",
            "theme_name": issue.issue_theme,
            "summary_description": issue.summary_description,
            "frequency": issue.frequency,
            "source_doc_ids": issue.source_doc_ids,
            "justification": issue.justification,
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.table("synthesis_themes").insert(theme_data).execute()

        # Create assignments for this theme
        # Get extraction IDs that were assigned to this theme
        finding_to_theme_map = final_state.get("finding_to_theme_map", {})
        for extraction_id, theme_mapping in finding_to_theme_map.items():
            if theme_mapping.get("issue_theme") == issue.issue_theme:
                theme_assignments.append(
                    {
                        "id": str(uuid.uuid4()),
                        "synthesis_run_id": run_id,
                        "synthesis_theme_id": theme_id,
                        "extraction_id": extraction_id,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                )

    # Process intervention themes
    for intervention in final_state.get("aggregated_interventions", []):
        theme_id = str(uuid.uuid4())
        theme_data = {
            "id": theme_id,
            "synthesis_run_id": run_id,
            "theme_type": "intervention",
            "theme_name": intervention.intervention_name,
            "summary_description": intervention.brief_description,
            "impact_summary": intervention.impact_summary,
            "frequency": intervention.frequency,
            "source_doc_ids": intervention.supporting_doc_ids,
            "justification": intervention.justification,
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.table("synthesis_themes").insert(theme_data).execute()

        # Create assignments for this theme
        for extraction_id, theme_mapping in finding_to_theme_map.items():
            if (
                theme_mapping.get("intervention_theme")
                == intervention.intervention_name
            ):
                theme_assignments.append(
                    {
                        "id": str(uuid.uuid4()),
                        "synthesis_run_id": run_id,
                        "synthesis_theme_id": theme_id,
                        "extraction_id": extraction_id,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                )

    # Batch insert theme assignments
    if theme_assignments:
        supabase.table("theme_assignments").insert(theme_assignments).execute()


async def invalidate_cache(project_id: str) -> None:
    """
    Invalidate cached synthesis results for a project.

    Marks all synthesis runs as 'invalidated' for the given project.
    """
    supabase = get_supabase()

    supabase.table("synthesis_runs").update({"status": "invalidated"}).eq(
        "analysis_project_id", project_id
    ).eq("status", "completed").execute()


async def get_cache_stats(project_id: str) -> Dict:
    """
    Get cache statistics for a project.

    Returns information about cached runs, themes, and assignments.
    """
    supabase = get_supabase()

    # Count runs
    runs_res = (
        supabase.table("synthesis_runs")
        .select("id", count="exact")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    # Get latest run details
    latest_res = (
        supabase.table("synthesis_runs")
        .select("created_at, status, metadata")
        .eq("analysis_project_id", project_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    stats = {
        "total_runs": runs_res.count or 0,
        "has_cached_result": bool(latest_res.data),
        "latest_run": latest_res.data[0] if latest_res.data else None,
    }

    return stats
