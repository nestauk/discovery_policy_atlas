"""
Supabase-based caching for synthesis agent runs.

This module handles reading from and writing to the synthesis caching tables:
- synthesis_runs: Main run records with executive briefing
- synthesis_themes: Theme definitions (issues and interventions)  
- theme_assignments: Mappings from extraction_id to theme_id
"""

import uuid
from datetime import datetime
from typing import Dict, Optional, List, Set

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

    # Map analysis_document_id (uuid) -> external doc_id for display
    docs_res = (
        supabase.table("analysis_documents")
        .select("id, doc_id")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    uuid_to_docid = {
        str(d["id"]): str(d.get("doc_id") or "") for d in (docs_res.data or [])
    }

    # Convert to Pydantic models
    key_issues = []
    for theme in issue_themes:
        src_doc_ids: List[str] = []
        uuid_array = theme.get("source_document_ids") or []
        if uuid_array:
            src_doc_ids = [
                uuid_to_docid.get(str(u), "")
                for u in uuid_array
                if uuid_to_docid.get(str(u))
            ]
        key_issues.append(
            KeyIssue(
                issue_theme=theme["theme_name"],
                summary_description=theme["summary_description"] or "",
                frequency=theme["frequency"] or 0,
                source_doc_ids=src_doc_ids,
            )
        )

    interventions = []
    for theme in intervention_themes:
        supp_doc_ids: List[str] = []
        uuid_array = theme.get("source_document_ids") or []
        if uuid_array:
            supp_doc_ids = [
                uuid_to_docid.get(str(u), "")
                for u in uuid_array
                if uuid_to_docid.get(str(u))
            ]
        interventions.append(
            PolicyIntervention(
                intervention_name=theme["theme_name"],
                brief_description=theme["summary_description"] or "",
                impact_summary=theme["impact_summary"] or "",
                frequency=theme["frequency"] or 0,
                supporting_doc_ids=supp_doc_ids,
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

    # Insert a new run record (keep history). If you prefer 1-per-project, add
    # a UNIQUE constraint on analysis_project_id and switch back to upsert.
    supabase.table("synthesis_runs").insert(run_data).execute()

    # Create theme records and collect assignments
    theme_assignments = []

    # Build extraction-id assignments from final themes if available
    issue_theme_to_ex_ids: Dict[str, List[str]] = {}
    for ft in final_state.get("final_issue_themes", []) or []:
        try:
            name = ft["name"] if isinstance(ft, dict) else ft.name
            concepts = ft["concepts"] if isinstance(ft, dict) else ft.concepts
            ex_ids = []
            for c in concepts or []:
                ex_ids.append(c["id"] if isinstance(c, dict) else c.id)
            # Deduplicate while preserving order
            seen: Set[str] = set()
            uniq: List[str] = []
            for x in ex_ids:
                if x and x not in seen:
                    seen.add(x)
                    uniq.append(x)
            issue_theme_to_ex_ids[name] = uniq
        except Exception:
            continue

    intr_theme_to_ex_ids: Dict[str, List[str]] = {}
    for ft in final_state.get("final_intervention_themes", []) or []:
        try:
            name = ft["name"] if isinstance(ft, dict) else ft.name
            concepts = ft["concepts"] if isinstance(ft, dict) else ft.concepts
            ex_ids = []
            for c in concepts or []:
                ex_ids.append(c["id"] if isinstance(c, dict) else c.id)
            seen2: Set[str] = set()
            uniq2: List[str] = []
            for x in ex_ids:
                if x and x not in seen2:
                    seen2.add(x)
                    uniq2.append(x)
            intr_theme_to_ex_ids[name] = uniq2
        except Exception:
            continue

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
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.table("synthesis_themes").insert(theme_data).execute()

        # Create assignments for this theme
        # Prefer mapping from final themes; fallback to finding_to_theme_map
        mapped_ids = issue_theme_to_ex_ids.get(issue.issue_theme, [])
        if not mapped_ids:
            finding_to_theme_map = final_state.get("finding_to_theme_map", {})
            mapped_ids = [
                ex_id
                for ex_id, mapping in finding_to_theme_map.items()
                if mapping.get("issue_theme") == issue.issue_theme
            ]
        for extraction_id in mapped_ids:
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
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.table("synthesis_themes").insert(theme_data).execute()

        # Create assignments for this theme
        mapped_ids = intr_theme_to_ex_ids.get(intervention.intervention_name, [])
        if not mapped_ids:
            finding_to_theme_map = final_state.get("finding_to_theme_map", {})
            mapped_ids = [
                ex_id
                for ex_id, mapping in finding_to_theme_map.items()
                if mapping.get("intervention_theme") == intervention.intervention_name
            ]
        for extraction_id in mapped_ids:
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
        # Deduplicate by (theme, extraction_id)
        seen_keys: Set[str] = set()
        unique_assignments = []
        for a in theme_assignments:
            k = f"{a['synthesis_theme_id']}::{a['extraction_id']}"
            if k in seen_keys:
                continue
            seen_keys.add(k)
            unique_assignments.append(a)
        supabase.table("theme_assignments").insert(unique_assignments).execute()


async def get_synthesis_status(project_id: str) -> str:
    """
    Get current synthesis status for a project.

    Returns:
        'none': No synthesis runs exist
        'running': Synthesis is currently running
        'completed': Synthesis has completed successfully
        'failed': Synthesis has failed
    """
    supabase = get_supabase()

    # Get most recent synthesis run
    runs_res = (
        supabase.table("synthesis_runs")
        .select("status")
        .eq("analysis_project_id", project_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return "none"

    status = runs_res.data[0].get("status", "none")
    return status


async def create_synthesis_run_placeholder(project_id: str) -> str:
    """
    Create a 'running' synthesis run to prevent duplicates.

    Returns:
        run_id: The ID of the created synthesis run
    """
    supabase = get_supabase()

    run_id = str(uuid.uuid4())
    run_data = {
        "id": run_id,
        "analysis_project_id": project_id,
        "status": "running",
        "version": 2,
        "executive_briefing": "",
        "model_info": {},
        "state_after_clustering": {},
        "state_after_critique": {},
        "created_at": datetime.utcnow().isoformat(),
    }

    supabase.table("synthesis_runs").insert(run_data).execute()
    return run_id


async def update_synthesis_run_status(
    run_id: str, status: str, final_state: Optional[Dict] = None
) -> None:
    """
    Update synthesis run status and optionally store results.

    Args:
        run_id: The synthesis run ID to update
        status: New status ('completed', 'failed', etc.)
        final_state: Optional final state data for completed runs
    """
    supabase = get_supabase()

    update_data = {
        "status": status,
    }

    if status == "completed" and final_state:
        # Update with full synthesis results
        update_data.update(
            {
                "executive_briefing": final_state.get("executive_briefing", ""),
                "model_info": {
                    "theme_iteration": final_state.get("theme_iteration", 0),
                    "total_issues": len(final_state.get("aggregated_issues", [])),
                    "total_interventions": len(
                        final_state.get("aggregated_interventions", [])
                    ),
                },
                "state_after_clustering": {
                    "issue_clusters": final_state.get("issue_clusters", {}),
                    "intervention_clusters": final_state.get(
                        "intervention_clusters", {}
                    ),
                    "issue_theme_names": final_state.get("issue_theme_names", {}),
                    "intervention_theme_names": final_state.get(
                        "intervention_theme_names", {}
                    ),
                },
                "state_after_critique": {
                    "theme_critique": final_state.get("theme_critique"),
                    "aggregated_issues": [
                        issue.dict()
                        for issue in final_state.get("aggregated_issues", [])
                    ],
                    "aggregated_interventions": [
                        intv.dict()
                        for intv in final_state.get("aggregated_interventions", [])
                    ],
                },
            }
        )

    supabase.table("synthesis_runs").update(update_data).eq("id", run_id).execute()


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
