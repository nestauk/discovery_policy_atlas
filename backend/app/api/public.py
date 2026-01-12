"""Public API endpoints for sharing projects without authentication.

These endpoints provide read-only access to project data for projects
that have been marked as public (is_public = true).
"""

from fastapi import APIRouter, HTTPException
import logging

from app.services.vectorization import vectorization_service
from app.services.synthesis.schemas import SynthesisSummary
from app.services.synthesis.logbook import read_cached_summary
from app.services.project_data import (
    get_project_documents_list,
    aggregate_charts_data,
    aggregate_interventions,
    build_issue_intervention_navigator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/projects", tags=["public"])


def get_public_project(project_id: str, select: str = "*") -> dict:
    """Fetch a project and verify it is public.

    Args:
        project_id: The project UUID
        select: Columns to select (default: all)

    Returns:
        The project data dict

    Raises:
        HTTPException: 404 if not found or not public
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
        raise HTTPException(status_code=404, detail="Project not found")

    return project


@router.get("/{project_id}")
async def get_public_project_details(project_id: str):
    """Get a public project's details."""
    try:
        project = get_public_project(project_id)

        return {
            "project": {
                "id": str(project["id"]),
                "title": project["title"],
                "description": project.get("description"),
                "total_references": project.get("total_references", 0),
                "relevant_references": project.get("relevant_references", 0),
                "status": project.get("status", "unknown"),
                "created_at": project["created_at"],
                "search_query": project.get("search_query"),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@router.get("/{project_id}/summary", response_model=SynthesisSummary)
async def get_public_synthesis_summary(project_id: str):
    """Get synthesis summary for a public project."""
    try:
        project = get_public_project(project_id, "id, status, is_public")
        project_status = project.get("status")

        cached = await read_cached_summary(project_id)
        if cached:
            return cached

        if project_status in ["running", "synthesising"]:
            raise HTTPException(
                status_code=202,
                detail="Analysis is still in progress. Please check back later.",
            )

        raise HTTPException(
            status_code=404,
            detail="Summary not available for this project.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public summary for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch summary")


@router.get("/{project_id}/documents")
async def get_public_project_documents(project_id: str):
    """Get all documents for a public project."""
    try:
        get_public_project(project_id, "id, is_public")
        return get_project_documents_list(project_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching documents for public project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch documents")


@router.get("/{project_id}/charts-data")
async def get_public_project_charts_data(project_id: str):
    """Get aggregated chart data for a public project."""
    try:
        get_public_project(project_id, "id, is_public")
        return aggregate_charts_data(project_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching charts data for public project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch charts data")


@router.get("/{project_id}/interventions")
async def get_public_project_interventions(project_id: str):
    """Get aggregated interventions data for a public project."""
    try:
        get_public_project(project_id, "id, is_public")
        return aggregate_interventions(project_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching interventions for public project {project_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to fetch interventions")


@router.get("/{project_id}/issue-intervention-navigator")
async def get_public_issue_intervention_navigator(project_id: str):
    """Get issue-intervention navigator data for a public project."""
    try:
        get_public_project(project_id, "id, is_public")
        return build_issue_intervention_navigator(
            project_id, include_detailed_interventions=False
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching navigator for public project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch navigator data")
