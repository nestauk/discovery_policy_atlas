"""Public API endpoints that don't require authentication.

These endpoints serve read-only project data for projects marked as public.
"""

from fastapi import APIRouter, HTTPException

from app.services.vectorization import vectorization_service
from app.services.synthesis.schemas import SynthesisSummary
from app.services.synthesis.logbook import get_synthesis_status
from app.utils.project_data import (
    get_project_documents_data,
    get_project_charts_data,
    get_project_interventions_data,
    get_navigator_data,
    get_summary_with_counts,
    get_outcome_contributions_data,
)

router = APIRouter(prefix="/api/public", tags=["public"])


def get_public_project(project_id: str, select: str = "*") -> dict:
    """Fetch a project and verify it is public.

    Raises:
        HTTPException: 404 if not found, 403 if not public
    """
    if select != "*" and "is_public" not in select:
        select = f"{select}, is_public"

    result = (
        vectorization_service.supabase.table("analysis_projects")
        .select(select)
        .eq("id", project_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = result.data[0]

    if not project.get("is_public"):
        raise HTTPException(status_code=403, detail="This project is not public")

    return project


@router.get("/projects/{project_id}")
async def get_public_project_details(project_id: str):
    """Get basic details of a public project."""
    project = get_public_project(project_id)

    return {
        "project": {
            "id": str(project["id"]),
            "run_id": project.get("run_id"),
            "title": project["title"],
            "description": project.get("description"),
            "query": project.get("query"),
            "total_references": project.get("total_references", 0),
            "relevant_references": project.get("relevant_references", 0),
            "status": project.get("status", "unknown"),
            "created_at": project["created_at"],
            "created_by_name": project.get("created_by_name"),
        }
    }


@router.get("/projects/{project_id}/summary", response_model=SynthesisSummary)
async def get_public_project_summary(project_id: str):
    """Get synthesis summary for a public project."""
    project = get_public_project(project_id, "status, is_public")
    project_status = project.get("status")

    cached, _, _ = await get_summary_with_counts(project_id)
    if cached:
        return cached

    if project_status in ["running", "synthesising"]:
        synthesis_status = await get_synthesis_status(project_id)
        if synthesis_status == "running":
            raise HTTPException(status_code=202, detail="Synthesis is running")
        elif synthesis_status == "none":
            raise HTTPException(status_code=202, detail="Analysis is still running")

    synthesis_status = await get_synthesis_status(project_id)
    if synthesis_status == "failed":
        raise HTTPException(status_code=500, detail="Synthesis failed")

    raise HTTPException(status_code=404, detail="Summary not available")


@router.get("/projects/{project_id}/documents")
async def get_public_project_documents(project_id: str):
    """Get all documents for a public project."""
    get_public_project(project_id, "id, is_public")
    return get_project_documents_data(project_id)


@router.get("/projects/{project_id}/interventions")
async def get_public_project_interventions(project_id: str):
    """Get aggregated interventions for a public project."""
    get_public_project(project_id, "id, is_public")
    return get_project_interventions_data(project_id)


@router.get("/projects/{project_id}/charts-data")
async def get_public_project_charts_data(project_id: str):
    """Get aggregated chart data for a public project."""
    get_public_project(project_id, "id, is_public")
    return get_project_charts_data(project_id)


@router.get("/projects/{project_id}/issue-intervention-navigator")
async def get_public_issue_intervention_navigator(project_id: str):
    """Get issue-intervention navigator data for a public project."""
    get_public_project(project_id, "id, is_public")
    return get_navigator_data(project_id)


@router.get(
    "/projects/{project_id}/synthesis/outcome-themes/{outcome_theme_id}/contributions"
)
async def get_public_outcome_contributions(project_id: str, outcome_theme_id: str):
    """Get contributing outcome extractions for a synthesis outcome theme."""
    get_public_project(project_id, "id, is_public")
    return get_outcome_contributions_data(project_id, outcome_theme_id)
