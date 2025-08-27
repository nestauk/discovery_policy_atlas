from fastapi import APIRouter, HTTPException, Depends
import logging
from datetime import datetime
import uuid
from typing import Optional

from app.core.auth import get_current_user, CurrentUser
from app.services.vectorization import vectorization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis-projects", tags=["analysis-projects"])


@router.get("/")
async def get_analysis_projects(current_user: CurrentUser = Depends(get_current_user)):
    """Get all analysis projects"""
    try:
        result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        projects = []
        for project_data in result.data:
            projects.append(
                {
                    "id": str(project_data["id"]),
                    "run_id": project_data.get("run_id"),
                    "title": project_data["title"],
                    "description": project_data.get("description"),
                    "query": project_data["query"],
                    "total_references": project_data.get("total_references", 0),
                    "relevant_references": project_data.get("relevant_references", 0),
                    "status": project_data.get("status", "created"),
                    "created_at": project_data["created_at"],
                }
            )

        return {"projects": projects, "total": len(projects)}

    except Exception as e:
        logger.error(f"Error fetching analysis projects: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis projects")


@router.post("/")
async def create_analysis_project(
    request: dict, current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new analysis project"""
    try:
        title = request.get("title", "").strip()
        query = request.get("query", "").strip() if request.get("query") else None

        if not title:
            raise HTTPException(status_code=400, detail="Title is required")

        project_data = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": request.get("description", "").strip() or None,
            "query": query,
            "total_references": 0,
            "relevant_references": 0,
            "status": "created",
            "created_at": datetime.utcnow().isoformat(),
        }

        result = (
            vectorization_service.supabase.table("analysis_projects")
            .insert(project_data)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=500, detail="Failed to create analysis project"
            )

        created_project = result.data[0]
        return {
            "id": str(created_project["id"]),
            "title": created_project["title"],
            "description": created_project.get("description"),
            "query": created_project["query"],
            "total_references": created_project.get("total_references", 0),
            "relevant_references": created_project.get("relevant_references", 0),
            "status": created_project.get("status", "created"),
            "created_at": created_project["created_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating analysis project: {e}")
        raise HTTPException(status_code=500, detail="Failed to create analysis project")


@router.get("/{project_id}")
async def get_analysis_project(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get a specific analysis project with documents and extractions"""
    try:
        # Get project
        project_result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("*")
            .eq("id", project_id)
            .execute()
        )

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        project = project_result.data[0]

        # Get documents
        docs_result = (
            vectorization_service.supabase.table("analysis_documents")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )

        # Get extractions
        extractions_result = (
            vectorization_service.supabase.table("analysis_extractions")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )

        return {
            "project": {
                "id": str(project["id"]),
                "run_id": project.get("run_id"),
                "title": project["title"],
                "description": project.get("description"),
                "query": project["query"],
                "total_references": project.get("total_references", 0),
                "relevant_references": project.get("relevant_references", 0),
                "status": project.get("status", "unknown"),
                "created_at": project["created_at"],
            },
            "documents": docs_result.data,
            "extractions": extractions_result.data,
            "document_count": len(docs_result.data),
            "extraction_count": len(extractions_result.data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analysis project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis project")


@router.put("/{project_id}")
async def update_analysis_project(
    project_id: str,
    request: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an analysis project"""
    try:
        # Build update data
        update_data = {}

        if "title" in request and request["title"].strip():
            update_data["title"] = request["title"].strip()
        if "description" in request:
            update_data["description"] = request["description"].strip() or None
        if "query" in request and request["query"].strip():
            update_data["query"] = request["query"].strip()
        if "status" in request:
            update_data["status"] = request["status"]
        if "run_id" in request:
            update_data["run_id"] = request["run_id"]
        if "total_references" in request:
            update_data["total_references"] = request["total_references"]
        if "relevant_references" in request:
            update_data["relevant_references"] = request["relevant_references"]

        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        result = (
            vectorization_service.supabase.table("analysis_projects")
            .update(update_data)
            .eq("id", project_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        updated_project = result.data[0]
        return {
            "id": str(updated_project["id"]),
            "run_id": updated_project.get("run_id"),
            "title": updated_project["title"],
            "description": updated_project.get("description"),
            "query": updated_project["query"],
            "total_references": updated_project.get("total_references", 0),
            "relevant_references": updated_project.get("relevant_references", 0),
            "status": updated_project.get("status", "unknown"),
            "created_at": updated_project["created_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating analysis project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update analysis project")


@router.delete("/{project_id}")
async def delete_analysis_project(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Delete an analysis project and all its data"""
    try:
        # Check if project exists
        project_result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("id")
            .eq("id", project_id)
            .execute()
        )

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Delete project (cascading delete will handle documents and extractions)
        vectorization_service.supabase.table("analysis_projects").delete().eq(
            "id", project_id
        ).execute()

        return {"message": "Analysis project deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting analysis project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete analysis project")


@router.post("/{project_id}/run-analysis")
async def run_analysis_for_project(
    project_id: str,
    request: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Run analysis service for a specific project"""
    try:
        from app.services.analysis.service import AnalysisService
        from app.services.analysis.schemas import RunConfig
        from app.core.config import settings

        # Check if project exists
        project_result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("*")
            .eq("id", project_id)
            .execute()
        )

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Build run config from request (query comes from search, not from project)
        query = request.get("query", "").strip()
        if not query:
            raise HTTPException(
                status_code=400, detail="Query is required for analysis"
            )

        config = RunConfig(
            query=query,
            sources=request.get("sources", ["openalex", "overton"]),
            date_from=request.get("since"),
            date_to=request.get("until"),
            limit=int(request.get("limit", 200)),
            screening_enabled=bool(request.get("screening", False)),
            relevance_enabled=bool(request.get("relevance_enabled", True)),
            retrieval_mode=request.get("mode", "semantic"),
            boolean_query=request.get("boolean_query"),
            use_abstracts_only=bool(request.get("use_abstracts_only", False)),
        )

        # Update project status to running
        vectorization_service.supabase.table("analysis_projects").update(
            {"status": "running"}
        ).eq("id", project_id).execute()

        # Run analysis
        service = AnalysisService(export_dir=settings.EXPORT_FILES_DIR)
        result = await service.run(config, project_id=project_id)

        # Update project with results
        vectorization_service.supabase.table("analysis_projects").update(
            {
                "run_id": result.run_id,
                "total_references": result.total_references,
                "relevant_references": result.relevant_references,
                "status": "completed",
            }
        ).eq("id", project_id).execute()

        return {
            "project_id": project_id,
            "run_id": result.run_id,
            "total_references": result.total_references,
            "relevant_references": result.relevant_references,
            "references_csv_path": result.references_csv_path,
            "extractions_json_path": result.extractions_json_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running analysis for project {project_id}: {e}")
        # Mark project as failed
        try:
            vectorization_service.supabase.table("analysis_projects").update(
                {"status": "failed"}
            ).eq("id", project_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to run analysis: {str(e)}")


@router.get("/{project_id}/documents")
async def get_project_documents(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get all documents for an analysis project"""
    try:
        docs_result = (
            vectorization_service.supabase.table("analysis_documents")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        return {"documents": docs_result.data, "total": len(docs_result.data)}

    except Exception as e:
        logger.error(f"Error fetching documents for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project documents")


@router.get("/{project_id}/extractions")
async def get_project_extractions(
    project_id: str,
    extraction_type: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all extractions for an analysis project, optionally filtered by type"""
    try:
        query = (
            vectorization_service.supabase.table("analysis_extractions")
            .select("*")
            .eq("analysis_project_id", project_id)
        )

        if extraction_type:
            query = query.eq("extraction_type", extraction_type)

        extractions_result = query.execute()
        return {
            "extractions": extractions_result.data,
            "total": len(extractions_result.data),
        }

    except Exception as e:
        logger.error(f"Error fetching extractions for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch project extractions"
        )


@router.get("/{project_id}/documents/{document_id}/extraction")
async def get_document_extraction(
    project_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get detailed extraction results for a specific document"""
    try:
        # First verify the document belongs to this project
        doc_result = (
            vectorization_service.supabase.table("analysis_documents")
            .select("*")
            .eq("id", document_id)
            .eq("analysis_project_id", project_id)
            .execute()
        )

        if not doc_result.data:
            raise HTTPException(
                status_code=404, detail="Document not found in this project"
            )

        document = doc_result.data[0]

        # Get the extraction results from the JSONB field
        extraction_results = document.get("extraction_results")

        if not extraction_results:
            return {
                "document": {
                    "id": document["id"],
                    "doc_id": document["doc_id"],
                    "title": document["title"],
                    "source": document["source"],
                    "year": document.get("year"),
                    "abstract_or_summary": document.get("abstract_or_summary"),
                    "is_relevant": document.get("is_relevant"),
                },
                "extraction": None,
                "message": "No extraction results available for this document",
            }

        # Parse and organize the extraction data
        issues = extraction_results.get("issues", [])
        interventions = extraction_results.get("interventions", [])
        mappings = extraction_results.get("mappings", [])
        results = extraction_results.get("results", [])
        conclusion = extraction_results.get("conclusion")

        # Group results by intervention for easier display
        results_by_intervention = {}
        for result in results:
            intervention_idx = result.get("intervention_idx")
            if intervention_idx is not None:
                if intervention_idx not in results_by_intervention:
                    results_by_intervention[intervention_idx] = []
                results_by_intervention[intervention_idx].append(result)

        # Add results to interventions and map issues
        enhanced_interventions = []
        for intervention in interventions:
            intervention_copy = intervention.copy()
            intervention_idx = intervention.get("idx")

            # Add results for this intervention
            intervention_copy["results"] = results_by_intervention.get(
                intervention_idx, []
            )

            # Find which issues this intervention addresses
            intervention_copy["addresses_issues"] = [
                mapping.get("issue_idx")
                for mapping in mappings
                if mapping.get("intervention_idx") == intervention_idx
            ]

            enhanced_interventions.append(intervention_copy)

        return {
            "document": {
                "id": document["id"],
                "doc_id": document["doc_id"],
                "title": document["title"],
                "source": document["source"],
                "year": document.get("year"),
                "abstract_or_summary": document.get("abstract_or_summary"),
                "is_relevant": document.get("is_relevant"),
                "extraction_status": document.get("extraction_status"),
            },
            "extraction": {
                "issues": issues,
                "interventions": enhanced_interventions,
                "mappings": mappings,
                "conclusion": conclusion,
                "metadata": extraction_results.get("extraction_metadata", {}),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching document extraction {document_id} for project {project_id}: {e}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to fetch document extraction"
        )
