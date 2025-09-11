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
    OutcomeTheme,
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

    # Separate issues, interventions, and results
    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]
    result_themes = [t for t in themes if t["theme_type"] == "result"]

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

    outcome_themes = []
    for theme in result_themes:
        src_doc_ids: List[str] = []
        uuid_array = theme.get("source_document_ids") or []
        if uuid_array:
            src_doc_ids = [
                uuid_to_docid.get(str(u), "")
                for u in uuid_array
                if uuid_to_docid.get(str(u))
            ]
        outcome_themes.append(
            OutcomeTheme(
                outcome_theme=theme["theme_name"],
                summary_description=theme["summary_description"] or "",
                frequency=theme["frequency"] or 0,
                source_doc_ids=src_doc_ids,
            )
        )

    return SynthesisSummary(
        executive_briefing=run["executive_briefing"] or "",
        key_issues=key_issues,
        interventions=interventions,
        outcome_themes=outcome_themes,
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
            "total_results": len(final_state.get("aggregated_outcome_themes", [])),
        },
        "state_after_clustering": {
            "issue_clusters": final_state.get("issue_clusters", {}),
            "intervention_clusters": final_state.get("intervention_clusters", {}),
            "result_clusters": final_state.get("result_clusters", {}),
            "issue_theme_names": final_state.get("issue_theme_names", {}),
            "intervention_theme_names": final_state.get("intervention_theme_names", {}),
            "result_theme_names": final_state.get("result_theme_names", {}),
        },
        "state_after_critique": {
            "theme_critique": final_state.get("theme_critique"),
            "aggregated_issues": [
                issue.dict() for issue in final_state.get("aggregated_issues", [])
            ],
            "aggregated_interventions": [
                intv.dict() for intv in final_state.get("aggregated_interventions", [])
            ],
            "aggregated_outcome_themes": [
                outcome.dict()
                for outcome in final_state.get("aggregated_outcome_themes", [])
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

    result_theme_to_ex_ids: Dict[str, List[str]] = {}
    for ft in final_state.get("final_result_themes", []) or []:
        try:
            name = ft["name"] if isinstance(ft, dict) else ft.name
            concepts = ft["concepts"] if isinstance(ft, dict) else ft.concepts
            ex_ids = []
            for c in concepts or []:
                ex_ids.append(c["id"] if isinstance(c, dict) else c.id)
            seen3: Set[str] = set()
            uniq3: List[str] = []
            for x in ex_ids:
                if x and x not in seen3:
                    seen3.add(x)
                    uniq3.append(x)
            result_theme_to_ex_ids[name] = uniq3
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

    # Process result themes
    for outcome in final_state.get("aggregated_outcome_themes", []):
        theme_id = str(uuid.uuid4())
        theme_data = {
            "id": theme_id,
            "synthesis_run_id": run_id,
            "theme_type": "result",
            "theme_name": outcome.outcome_theme,
            "summary_description": outcome.summary_description,
            "frequency": outcome.frequency,
            "source_doc_ids": outcome.source_doc_ids,
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.table("synthesis_themes").insert(theme_data).execute()

        # Create assignments for this theme
        mapped_ids = result_theme_to_ex_ids.get(outcome.outcome_theme, [])
        if not mapped_ids:
            finding_to_theme_map = final_state.get("finding_to_theme_map", {})
            mapped_ids = [
                ex_id
                for ex_id, mapping in finding_to_theme_map.items()
                if mapping.get("result_theme") == outcome.outcome_theme
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

    # Create intervention-result connections
    await _create_intervention_result_connections(supabase, project_id, run_id)


async def _create_intervention_result_connections(
    supabase, project_id: str, run_id: str
) -> None:
    """
    Create connections between intervention and result themes based on extraction relationships.

    Links intervention themes to outcome themes via:
    Intervention theme <- intervention extraction <-> result extraction -> outcome theme
    """
    try:
        # Get all theme assignments for this run to map extractions to themes
        assignments_res = (
            supabase.table("theme_assignments")
            .select("extraction_id, synthesis_theme_id")
            .eq("synthesis_run_id", run_id)
            .execute()
        )

        if not assignments_res.data:
            return

        # Build extraction_id -> theme_id mapping
        extraction_to_theme = {
            str(a["extraction_id"]): str(a["synthesis_theme_id"])
            for a in assignments_res.data
        }

        # Get all extractions that have theme assignments
        extraction_ids = list(extraction_to_theme.keys())
        if not extraction_ids:
            return

        # Fetch extraction records to get raw_data and analysis_document_id
        # Process in chunks to avoid URL length limits
        CHUNK_SIZE = 500
        all_extractions = []

        for i in range(0, len(extraction_ids), CHUNK_SIZE):
            chunk = extraction_ids[i : i + CHUNK_SIZE]
            exts_res = (
                supabase.table("analysis_extractions")
                .select("id, analysis_document_id, extraction_type, raw_data")
                .in_("id", chunk)
                .execute()
            )
            all_extractions.extend(exts_res.data or [])

        # Separate interventions and results
        interventions_by_doc_and_idx = {}  # doc_id -> idx -> extraction
        results_by_doc = {}  # doc_id -> [result_extractions]

        for ext in all_extractions:
            doc_id = str(ext.get("analysis_document_id", ""))
            ext_type = str(ext.get("extraction_type", ""))
            raw_data = ext.get("raw_data") or {}

            if ext_type == "intervention":
                idx = raw_data.get("idx")
                if idx is not None:
                    if doc_id not in interventions_by_doc_and_idx:
                        interventions_by_doc_and_idx[doc_id] = {}
                    interventions_by_doc_and_idx[doc_id][int(idx)] = ext

            elif ext_type == "result":
                if doc_id not in results_by_doc:
                    results_by_doc[doc_id] = []
                results_by_doc[doc_id].append(ext)

        # Create connections
        connections = []

        for doc_id, result_extractions in results_by_doc.items():
            intervention_map = interventions_by_doc_and_idx.get(doc_id, {})

            for result_ext in result_extractions:
                raw_data = result_ext.get("raw_data") or {}
                intervention_idx = raw_data.get("intervention_idx")

                if (
                    intervention_idx is not None
                    and int(intervention_idx) in intervention_map
                ):
                    intervention_ext = intervention_map[int(intervention_idx)]

                    # Get theme IDs for both extractions
                    result_theme_id = extraction_to_theme.get(str(result_ext["id"]))
                    intervention_theme_id = extraction_to_theme.get(
                        str(intervention_ext["id"])
                    )

                    if result_theme_id and intervention_theme_id:
                        connections.append(
                            {
                                "id": str(uuid.uuid4()),
                                "synthesis_run_id": run_id,
                                "analysis_project_id": project_id,
                                "analysis_document_id": doc_id,
                                "intervention_extraction_id": str(
                                    intervention_ext["id"]
                                ),
                                "result_extraction_id": str(result_ext["id"]),
                                "intervention_theme_id": intervention_theme_id,
                                "result_theme_id": result_theme_id,
                                "created_at": datetime.utcnow().isoformat(),
                            }
                        )

        # Batch insert connections
        if connections:
            # Deduplicate by unique constraint (synthesis_run_id, intervention_extraction_id, result_extraction_id)
            seen_keys: Set[str] = set()
            unique_connections = []
            for conn in connections:
                k = f"{conn['synthesis_run_id']}::{conn['intervention_extraction_id']}::{conn['result_extraction_id']}"
                if k not in seen_keys:
                    seen_keys.add(k)
                    unique_connections.append(conn)

            if unique_connections:
                supabase.table("intervention_result_connections").insert(
                    unique_connections
                ).execute()
                print(
                    f"Created {len(unique_connections)} intervention-result connections"
                )

    except Exception as e:
        print(f"Warning: Failed to create intervention-result connections: {e}")
        # Don't fail the entire synthesis process if connection creation fails


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


async def get_intervention_result_network(project_id: str) -> Dict:
    """
    Get intervention-result network data for a project using full theme matrix approach.

    Creates connections between ALL intervention and result themes based on document co-occurrence.
    Returns data in format compatible with NetworkVisualizer component.
    """
    supabase = get_supabase()

    # Get the latest completed synthesis run
    runs_res = (
        supabase.table("synthesis_runs")
        .select("id")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return {
            "csv_data": [],
            "summary": {
                "total_intervention_themes": 0,
                "total_result_themes": 0,
                "total_connections": 0,
            },
        }

    run_id = runs_res.data[0]["id"]

    # Get all themes for this run (intervention and result only)
    themes_res = (
        supabase.table("synthesis_themes")
        .select(
            "id, theme_type, theme_name, summary_description, frequency, source_doc_ids"
        )
        .eq("synthesis_run_id", run_id)
        .in_("theme_type", ["intervention", "result"])
        .execute()
    )

    themes = themes_res.data or []
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]
    result_themes = [t for t in themes if t["theme_type"] == "result"]

    # Get total number of documents in project for sample size
    docs_res = (
        supabase.table("analysis_documents")
        .select("id", count="exact")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    total_documents = docs_res.count or 0

    # Create full theme matrix - connect ALL intervention themes to ALL result themes
    csv_data = []

    for intervention_theme in intervention_themes:
        intervention_docs = set(intervention_theme.get("source_doc_ids") or [])

        for result_theme in result_themes:
            result_docs = set(result_theme.get("source_doc_ids") or [])

            # Calculate raw co-occurrence count
            co_occurrence_count = len(intervention_docs.intersection(result_docs))

            # Calculate standardised effect size (0-1 range)
            max_possible_overlap = min(len(intervention_docs), len(result_docs))
            standardised_effect = (
                co_occurrence_count / max_possible_overlap
                if max_possible_overlap > 0
                else 0
            )

            # Create CSV-compatible record
            csv_record = {
                "Predictor": intervention_theme["theme_name"],
                "Outcome": result_theme["theme_name"],
                "Effect size": co_occurrence_count,
                "Standardised effect size": round(standardised_effect, 3),
                "Effect size type": "Document co-occurrence",
                "Study type": "Theme analysis",
                "Sample size": total_documents,
                "Location": "Project-wide",
                "URL": f"/synthesis/{project_id}/{run_id}",
            }

            csv_data.append(csv_record)

    return {
        "csv_data": csv_data,
        "summary": {
            "total_intervention_themes": len(intervention_themes),
            "total_result_themes": len(result_themes),
            "total_connections": len(csv_data),
            "total_documents": total_documents,
        },
    }
