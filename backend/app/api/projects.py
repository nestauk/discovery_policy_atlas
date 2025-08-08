from fastapi import APIRouter, HTTPException, Depends
import logging
from datetime import datetime
import uuid

from app.core.auth import get_current_user, CurrentUser
from app.core.models import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectList
from app.services.vectorization import vectorization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=ProjectList)
async def get_projects(current_user: CurrentUser = Depends(get_current_user)):
    """Get all projects for the current user"""
    try:
        # For now, get all projects (later can filter by user)
        result = vectorization_service.supabase.table("projects").select("*").execute()

        projects = []
        for project_data in result.data:
            projects.append(
                ProjectResponse(
                    id=str(project_data["id"]),
                    name=project_data["name"],
                    description=project_data.get("description"),
                    evidence_count=project_data.get("evidence_count", 0),
                    last_search_date=project_data.get("last_search_date"),
                    last_search_query=project_data.get("last_search_query"),
                    key_insights=project_data.get("key_insights"),
                    policy_recommendations=project_data.get("policy_recommendations"),
                    executive_brief=project_data.get("executive_brief"),
                    created_at=project_data["created_at"],
                    updated_at=project_data["updated_at"],
                )
            )

        return ProjectList(projects=projects, total=len(projects))

    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch projects")


@router.post("/", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate, current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new project"""
    try:
        project_data = {
            "id": str(uuid.uuid4()),
            "name": project.name,
            "description": project.description,
            "evidence_count": 0,
            "last_search_date": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        result = (
            vectorization_service.supabase.table("projects")
            .insert(project_data)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create project")

        created_project = result.data[0]
        return ProjectResponse(
            id=str(created_project["id"]),
            name=created_project["name"],
            description=created_project.get("description"),
            evidence_count=created_project.get("evidence_count", 0),
            last_search_date=created_project.get("last_search_date"),
            created_at=created_project["created_at"],
            updated_at=created_project["updated_at"],
        )

    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail="Failed to create project")


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get a specific project by ID"""
    try:
        result = (
            vectorization_service.supabase.table("projects")
            .select("*")
            .eq("id", project_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        project_data = result.data[0]
        return ProjectResponse(
            id=str(project_data["id"]),
            name=project_data["name"],
            description=project_data.get("description"),
            evidence_count=project_data.get("evidence_count", 0),
            last_search_date=project_data.get("last_search_date"),
            last_search_query=project_data.get("last_search_query"),
            key_insights=project_data.get("key_insights"),
            policy_recommendations=project_data.get("policy_recommendations"),
            executive_brief=project_data.get("executive_brief"),
            created_at=project_data["created_at"],
            updated_at=project_data["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project: ProjectUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a project"""
    try:
        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if project.name is not None:
            update_data["name"] = project.name
        if project.description is not None:
            update_data["description"] = project.description

        result = (
            vectorization_service.supabase.table("projects")
            .update(update_data)
            .eq("id", project_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        updated_project = result.data[0]
        return ProjectResponse(
            id=str(updated_project["id"]),
            name=updated_project["name"],
            description=updated_project.get("description"),
            evidence_count=updated_project.get("evidence_count", 0),
            last_search_date=updated_project.get("last_search_date"),
            last_search_query=updated_project.get("last_search_query"),
            key_insights=updated_project.get("key_insights"),
            policy_recommendations=updated_project.get("policy_recommendations"),
            executive_brief=updated_project.get("executive_brief"),
            created_at=updated_project["created_at"],
            updated_at=updated_project["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update project")


@router.delete("/{project_id}")
async def delete_project(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a project and all its associated documents"""
    try:
        # First delete all documents associated with this project
        vectorization_service.supabase.table("documents").delete().eq(
            "project_id", project_id
        ).execute()
        vectorization_service.supabase.table("chunks").delete().eq(
            "project_id", project_id
        ).execute()

        # Then delete the project
        result = (
            vectorization_service.supabase.table("projects")
            .delete()
            .eq("id", project_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        return {"message": "Project deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete project")


@router.get("/{project_id}/documents")
async def get_project_documents(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get all documents for a project"""
    try:
        documents = vectorization_service.get_project_documents(project_id)
        return {"documents": documents, "total": len(documents)}

    except Exception as e:
        logger.error(f"Error fetching documents for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project documents")


@router.post("/{project_id}/update-stats")
async def update_project_stats(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Update project statistics (evidence count, last search date)"""
    try:
        # Count documents for this project
        result = (
            vectorization_service.supabase.table("documents")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .execute()
        )
        evidence_count = result.count if hasattr(result, "count") else len(result.data)

        # Update project stats
        update_data = {
            "evidence_count": evidence_count,
            "last_search_date": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        result = (
            vectorization_service.supabase.table("projects")
            .update(update_data)
            .eq("id", project_id)
            .execute()
        )

        return {"message": "Project stats updated", "evidence_count": evidence_count}

    except Exception as e:
        logger.error(f"Error updating project stats for {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update project stats")
