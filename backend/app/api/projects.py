from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
from datetime import datetime
import json
import logging
import os
import time
from typing import Optional, List
import uuid
import pandas as pd

from app.core.auth import get_current_user, CurrentUser
from app.services.search_wizard import SearchWizardService
from app.services.vectorization import vectorization_service
from app.services.chatbot import ChatRequest, ChatResponse
from app.services.chatbot.chat_service import chatbot_service
from app.services.synthesis.schemas import (
    SynthesisSummary,
    EvidenceCoverageSnapshot,
    Finding,
    ThematicGroup,
    EvidenceItem,
    DocumentContextInfo,
    ChunkContextResponse,
)
from app.services.synthesis.findings import get_findings
from app.services.synthesis.logbook import read_cached_summary
from app.services.download import download_service
from app.services.analysis.schemas import (
    PopulationOptionsRequest,
    PopulationOptionsResponse,
    OutcomeOptionsRequest,
    OutcomeOptionsResponse,
    InnerSettingOptionsRequest,
    InnerSettingOptionsResponse,
    AdditionalQuestionsRequest,
    AdditionalQuestionsResponse,
)
from app.services.analysis.progress import get_synthesis_project_progress
from app.services.analysis.evidence.strength import get_or_calculate_document_evidence
from app.services.synthesis.utils import (
    normalize_source_type,
    extract_author_short,
    extract_author_display,
    extract_author_list,
    infer_source_value,
)
from app.utils.project_data import (
    filter_prevalence_only_results,
    filter_prevalence_only_extractions,
    get_project_documents_data,
    get_project_charts_data,
    get_project_interventions_data,
    get_navigator_data,
    get_navigator_overview_data,
    get_outcome_contributions_data,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/analysis-projects", tags=["analysis-projects"])

# Organization slug that has access to all projects (dev/admin org)
ADMIN_ORG_SLUG = "nesta-dev"


def can_access_all_projects(user: CurrentUser) -> bool:
    """Check if user belongs to an admin org that can see all projects."""
    return user.organization_slug == ADMIN_ORG_SLUG


def can_access_project(
    user: CurrentUser, project_org_id: str | None, project_created_by: str | None = None
) -> bool:
    """Check if user can access a specific project based on organization.

    Args:
        user: Current authenticated user
        project_org_id: Organization ID of the project
        project_created_by: User ID who created the project
    """
    # Admin org can access everything
    if can_access_all_projects(user):
        return True

    # Creators can always access their own projects (regardless of org assignment)
    if project_created_by == user.user_id:
        return True

    # Everyone can access demo org projects
    demo_org_id = os.getenv("DEMO_ORG_ID")
    if demo_org_id and project_org_id == demo_org_id:
        return True

    # User can access projects from their own org
    if user.organization_id and user.organization_id == project_org_id:
        return True

    return False


def get_project_with_auth_check(
    project_id: str, user: CurrentUser, select: str = "*"
) -> dict:
    """Fetch a project and verify the user has access to it.

    Args:
        project_id: The project UUID
        user: The current authenticated user
        select: Columns to select (default: all)

    Returns:
        The project data dict

    Raises:
        HTTPException: 404 if not found, 403 if access denied
    """
    # Always need organization_id and created_by_user_id for auth check
    if select != "*":
        if "organization_id" not in select:
            select = f"{select}, organization_id"
        if "created_by_user_id" not in select:
            select = f"{select}, created_by_user_id"

    result = (
        vectorization_service.supabase.table("analysis_projects")
        .select(select)
        .eq("id", project_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = result.data[0]

    if not can_access_project(
        user, project.get("organization_id"), project.get("created_by_user_id")
    ):
        raise HTTPException(status_code=403, detail="Access denied to this project")

    return project


# END-I - INFO REGION END


# Ψ INFO - CONTEXT NOTE
# Schemas are provided by app.services.synthesis.schemas (imported above).
# END-I - INFO REGION END


# Ψ INFO - CONTEXT NOTE
# Finding model is provided by app.services.synthesis.schemas (imported above).
# END-I - INFO REGION END


@router.get(
    "/{project_id}/summary",
    response_model=SynthesisSummary,
    summary="Get Synthesized Summary (Agentic)",
)
async def get_synthesis_summary(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get synthesis summary, handling different project states."""
    try:
        from app.services.synthesis.logbook import get_synthesis_status

        # Check project exists and user has access
        project = get_project_with_auth_check(
            project_id, current_user, "status, organization_id"
        )
        project_status = project.get("status")

        # Check if synthesis is already cached
        cached = await read_cached_summary(project_id)
        if cached:
            # Normalise evidence coverage counts to reflect screening outcomes, even for older cached runs.
            try:
                screened_res = (
                    vectorization_service.supabase.table("analysis_documents")
                    .select("id", count="exact")
                    .eq("analysis_project_id", project_id)
                    .execute()
                )
                total_screened = (
                    screened_res.count
                    if hasattr(screened_res, "count")
                    else len(screened_res.data or [])
                )
                synthesised_res = (
                    vectorization_service.supabase.table("analysis_documents")
                    .select("id", count="exact")
                    .eq("analysis_project_id", project_id)
                    .eq("is_relevant", True)
                    .execute()
                )
                total_synthesised = (
                    synthesised_res.count
                    if hasattr(synthesised_res, "count")
                    else len(synthesised_res.data or [])
                )

                if cached.evidence_coverage:
                    cached.evidence_coverage.total_screened = total_screened
                    cached.evidence_coverage.total_synthesised = total_synthesised
                else:
                    cached.evidence_coverage = EvidenceCoverageSnapshot(
                        total_screened=total_screened,
                        total_synthesised=total_synthesised,
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to compute screened/synthesised counts for project {project_id}: {e}"
                )
            return cached

        # If analysis still running or synthesising, return appropriate response
        if project_status in ["running", "synthesising"]:
            # Check synthesis status
            synthesis_status = await get_synthesis_status(project_id)

            if synthesis_status == "running":
                raise HTTPException(
                    status_code=202,
                    detail="Synthesis is running. Please wait for completion.",
                )
            elif synthesis_status == "none":
                # Analysis still running, synthesis not started yet
                if project_status == "running":
                    raise HTTPException(
                        status_code=202,
                        detail="Analysis is still running. Synthesis will start automatically when analysis completes.",
                    )
                else:  # project_status == "synthesising"
                    raise HTTPException(
                        status_code=202,
                        detail="Synthesis is starting. Please wait for completion.",
                    )

        # For completed projects without cache, try to trigger synthesis (fallback)
        if project_status == "completed":
            try:
                await trigger_synthesis_for_project(project_id)
                # Try to get cached result after synthesis
                cached = await read_cached_summary(project_id)
                if cached:
                    return cached
            except Exception as e:
                logger.error(f"Fallback synthesis failed for project {project_id}: {e}")

        # If still no cache, check synthesis status one more time
        synthesis_status = await get_synthesis_status(project_id)
        if synthesis_status == "failed":
            raise HTTPException(
                status_code=500,
                detail="Synthesis failed. Please try again or check project logs.",
            )
        elif synthesis_status == "running":
            raise HTTPException(
                status_code=202,
                detail="Synthesis is currently running. Please wait for completion.",
            )

        raise HTTPException(
            status_code=500,
            detail="Unable to generate synthesis summary. Please try again.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in synthesis summary for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get synthesis summary")


@router.get(
    "/{project_id}/chunks/{chunk_id}/context",
    response_model=ChunkContextResponse,
    summary="Get citation chunk context",
)
async def get_chunk_context(
    project_id: str,
    chunk_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get target chunk and adjacent context for citation inspection."""
    try:
        get_project_with_auth_check(project_id, current_user, "id, organization_id")

        target_res = (
            vectorization_service.supabase.table("chunks")
            .select("id, content, chunk_index, document_id, project_id")
            .eq("id", chunk_id)
            .eq("project_id", project_id)
            .limit(1)
            .execute()
        )
        if not target_res.data:
            raise HTTPException(
                status_code=404, detail="Chunk not found for this project"
            )

        target_chunk = target_res.data[0]
        target_index = int(target_chunk.get("chunk_index") or 0)
        document_id = str(target_chunk.get("document_id") or "")
        if not document_id:
            raise HTTPException(status_code=404, detail="Chunk has no source document")

        adjacent_indices = [target_index - 1, target_index + 1]
        adjacent_res = (
            vectorization_service.supabase.table("chunks")
            .select("content, chunk_index")
            .eq("document_id", document_id)
            .eq("project_id", project_id)
            .in_("chunk_index", adjacent_indices)
            .order("chunk_index")
            .execute()
        )

        previous_chunk_content: Optional[str] = None
        next_chunk_content: Optional[str] = None
        for row in adjacent_res.data or []:
            idx = int(row.get("chunk_index") or 0)
            content = str(row.get("content") or "")
            if idx == target_index - 1:
                previous_chunk_content = content
            elif idx == target_index + 1:
                next_chunk_content = content

        doc_res = (
            vectorization_service.supabase.table("analysis_documents")
            .select(
                "id, doc_id, title, authors, author_institutions, year, venue, source_country, source, document_type, evidence_category, evidence_category_reasoning, extraction_results, impact_score, impact_score_label, impact_score_breakdown, transferability_score, transferability_breakdown, pdf_url, landing_page_url, overton_url"
            )
            .eq("id", document_id)
            .eq("analysis_project_id", project_id)
            .limit(1)
            .execute()
        )
        if not doc_res.data:
            raise HTTPException(
                status_code=404, detail="Source document not found for this chunk"
            )

        doc = doc_res.data[0]
        evidence_info = get_or_calculate_document_evidence(doc)
        stars = evidence_info.get("stars")
        evidence_score = int(stars) if isinstance(stars, (int, float)) else None

        source_value = infer_source_value(doc.get("source"), doc.get("doc_id"))

        document = DocumentContextInfo(
            analysis_document_id=str(doc.get("id") or document_id),
            title=str(doc.get("title") or "Unknown source"),
            author_display=extract_author_display(doc.get("authors")),
            authors=extract_author_list(doc.get("authors")),
            author_institutions=extract_author_list(doc.get("author_institutions")),
            author_short=extract_author_short(doc.get("authors")),
            year=doc.get("year"),
            venue=doc.get("venue"),
            country=doc.get("source_country"),
            url=doc.get("pdf_url")
            or doc.get("landing_page_url")
            or doc.get("overton_url"),
            source_type=normalize_source_type(
                source_value, str(doc.get("document_type") or "")
            ),
            document_type=doc.get("document_type"),
            evidence_category=doc.get("evidence_category"),
            evidence_category_reasoning=doc.get("evidence_category_reasoning"),
            evidence_score=evidence_score,
            evidence_strength_justification=evidence_info.get("justification"),
            impact_score=doc.get("impact_score"),
            impact_score_label=doc.get("impact_score_label"),
            impact_score_breakdown=doc.get("impact_score_breakdown"),
            transferability_score=doc.get("transferability_score"),
            transferability_breakdown=doc.get("transferability_breakdown"),
        )

        return ChunkContextResponse(
            chunk_id=str(target_chunk.get("id") or chunk_id),
            chunk_content=str(target_chunk.get("content") or ""),
            chunk_index=target_index,
            previous_chunk_content=previous_chunk_content,
            next_chunk_content=next_chunk_content,
            document=document,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting chunk context project={project_id} chunk={chunk_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to get chunk context")


@router.get("")
@router.get("/")
async def get_analysis_projects(current_user: CurrentUser = Depends(get_current_user)):
    """Get analysis projects filtered by user's organization."""
    try:
        demo_org_id = os.getenv("DEMO_ORG_ID")

        # Use database function for filtering (centralizes authorization logic)
        result = vectorization_service.supabase.rpc(
            "get_user_projects",
            {
                "p_user_id": current_user.user_id,
                "p_organization_id": current_user.organization_id,
                "p_organization_slug": current_user.organization_slug,
                "p_demo_org_id": demo_org_id,
                "p_admin_org_slug": ADMIN_ORG_SLUG,
            },
        ).execute()

        projects = []
        for project_data in result.data:
            project_org_id = project_data.get("organization_id")
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
                    "created_by_user_id": project_data.get("created_by_user_id"),
                    "created_by_name": project_data.get("created_by_name"),
                    "organization_id": project_org_id,
                    "is_demo": demo_org_id is not None
                    and project_org_id == demo_org_id,
                }
            )

        return {"projects": projects, "total": len(projects)}

    except Exception as e:
        logger.error(f"Error fetching analysis projects: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis projects")


@router.post("")
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

        parent_project_id = request.get("parent_project_id")
        if parent_project_id:
            try:
                uuid.UUID(parent_project_id)
            except (ValueError, AttributeError):
                raise HTTPException(
                    status_code=400, detail="parent_project_id must be a valid UUID"
                )
            try:
                get_project_with_auth_check(parent_project_id, current_user, "id")
            except HTTPException:
                raise HTTPException(
                    status_code=400, detail="Invalid or inaccessible parent project"
                )

        project_data = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": request.get("description", "").strip() or None,
            "query": query,
            "total_references": 0,
            "relevant_references": 0,
            "status": "created",
            "created_at": datetime.utcnow().isoformat(),
            "created_by_user_id": current_user.user_id,
            "created_by_name": current_user.name,
            "organization_id": current_user.organization_id,
            "parent_project_id": parent_project_id,
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
            "created_by_user_id": created_project.get("created_by_user_id"),
            "created_by_name": created_project.get("created_by_name"),
            "organization_id": created_project.get("organization_id"),
            "parent_project_id": created_project.get("parent_project_id"),
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
    """Get a specific analysis project metadata.

    Returns only lightweight project metadata. Documents and extractions
    are available via their dedicated endpoints.
    """
    try:
        select_fields = (
            "id, run_id, title, description, query, total_references, "
            "relevant_references, status, created_at, created_by_user_id, "
            "created_by_name, organization_id, search_query, is_public, "
            "parent_project_id"
        )
        project = get_project_with_auth_check(project_id, current_user, select_fields)
        status = project.get("status", "unknown")
        progress = (
            get_synthesis_project_progress(project_id, status)
            if status == "synthesising"
            else None
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
                "status": status,
                "created_at": project["created_at"],
                "created_by_user_id": project.get("created_by_user_id"),
                "created_by_name": project.get("created_by_name"),
                "organization_id": project.get("organization_id"),
                "search_query": project.get("search_query"),
                "is_public": project.get("is_public", False),
                "parent_project_id": project.get("parent_project_id"),
                "progress": progress.model_dump() if progress else None,
            },
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
        # Check authorization first
        get_project_with_auth_check(project_id, current_user, "id, organization_id")

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
            "created_by_user_id": updated_project.get("created_by_user_id"),
            "created_by_name": updated_project.get("created_by_name"),
            "organization_id": updated_project.get("organization_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating analysis project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update analysis project")


@router.patch("/{project_id}/visibility")
async def update_project_visibility(
    project_id: str,
    request: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle public visibility for a project. Only the project creator can change this."""
    try:
        project = get_project_with_auth_check(
            project_id, current_user, "id, created_by_user_id"
        )

        if project.get("created_by_user_id") != current_user.user_id:
            raise HTTPException(
                status_code=403, detail="Only the project creator can change visibility"
            )

        is_public = request.get("is_public")
        if is_public is None:
            raise HTTPException(status_code=400, detail="is_public field is required")

        result = (
            vectorization_service.supabase.table("analysis_projects")
            .update({"is_public": bool(is_public)})
            .eq("id", project_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update visibility")

        return {"success": True, "is_public": bool(is_public)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating visibility for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to update project visibility"
        )


@router.delete("/{project_id}")
async def delete_analysis_project(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Delete an analysis project and all its data.

    Pre-deletes high-volume child tables so the final CASCADE on the
    project row is near-instant and won't hit the statement timeout.
    """
    try:
        get_project_with_auth_check(project_id, current_user, "id, organization_id")

        sb = vectorization_service.supabase

        # Collect IDs we'll need for targeted deletes
        doc_ids = [
            d["id"]
            for d in sb.table("analysis_documents")
            .select("id")
            .eq("analysis_project_id", project_id)
            .execute()
            .data
        ]
        run_ids = [
            r["id"]
            for r in sb.table("synthesis_runs")
            .select("id")
            .eq("analysis_project_id", project_id)
            .execute()
            .data
        ]
        # 1. Chunks (no CASCADE path from project)
        if doc_ids:
            sb.table("chunks").delete().in_("document_id", doc_ids).execute()
        sb.table("chunks").delete().eq("project_id", project_id).execute()

        # 2. Synthesis leaf tables → parents (by run_id)
        if run_ids:
            for table in [
                "outcome_theme_assignments",
                "theme_assignments",
                "synthesis_citations",
                "synthesis_outcome_themes",
                "synthesis_themes",
            ]:
                sb.table(table).delete().in_("synthesis_run_id", run_ids).execute()
            sb.table("synthesis_runs").delete().eq(
                "analysis_project_id", project_id
            ).execute()

        # 3. Extractions (has direct project FK)
        sb.table("analysis_extractions").delete().eq(
            "analysis_project_id", project_id
        ).execute()

        # 4. Documents
        sb.table("analysis_documents").delete().eq(
            "analysis_project_id", project_id
        ).execute()

        # 5. Delete project (CASCADE handles any remaining stragglers)
        sb.table("analysis_projects").delete().eq("id", project_id).execute()

        logger.info(f"Deleted analysis project {project_id}")
        return {"message": "Analysis project deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting analysis project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete analysis project")


async def trigger_synthesis_for_project(
    project_id: str, force: bool = False, invalidate_previous: bool = False
) -> None:
    """Trigger synthesis for a project.

    Args:
        project_id: Analysis project UUID.
        force: If True, rerun even when a completed run exists.
        invalidate_previous: If True, mark prior completed runs as invalidated.
    """
    from app.services.synthesis.logbook import (
        get_synthesis_status,
        create_synthesis_run_placeholder,
        invalidate_cache,
    )
    from app.services.synthesis.agent import SynthesisAgent

    synthesis_status = await get_synthesis_status(project_id)

    if synthesis_status == "running" and not force:
        logger.info(f"Synthesis already running for project {project_id}")
        return

    if synthesis_status == "completed" and not force:
        logger.info(f"Synthesis already completed for project {project_id}")
        # Keep marking the project completed for consistency
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: vectorization_service.supabase.table("analysis_projects")
            .update({"status": "completed"})
            .eq("id", project_id)
            .execute(),
        )
        return

    if invalidate_previous and synthesis_status in [
        "completed",
        "failed",
        "invalidated",
    ]:
        try:
            await invalidate_cache(project_id)
        except Exception as e:
            logger.warning(
                f"Failed to invalidate prior synthesis cache for {project_id}: {e}"
            )

    if force:
        try:
            # Clear prior synthesis_runs rows to satisfy unique constraint on analysis_project_id
            vectorization_service.supabase.table("synthesis_runs").delete().eq(
                "analysis_project_id", project_id
            ).execute()
        except Exception as e:
            logger.warning(
                f"Failed to clear existing synthesis_runs for forced rerun of project {project_id}: {e}"
            )

    # Create placeholder to prevent duplicate runs
    run_id = await create_synthesis_run_placeholder(project_id)

    try:
        logger.info(f"Starting synthesis for project {project_id}")

        # Mark project as synthesising (async to avoid blocking).
        # The analysis phase uses "running"; synthesis should be distinguished so
        # the frontend can render the correct progress state.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: vectorization_service.supabase.table("analysis_projects")
            .update({"status": "synthesising"})
            .eq("id", project_id)
            .execute(),
        )

        project_user_id = None
        try:
            project_row = (
                vectorization_service.supabase.table("analysis_projects")
                .select("created_by_user_id")
                .eq("id", project_id)
                .execute()
            )
            if project_row.data:
                project_user_id = project_row.data[0].get("created_by_user_id")
        except Exception:
            project_user_id = None

        # Run synthesis
        synthesis_agent = SynthesisAgent()
        synthesis_start = time.time()
        final_state = await synthesis_agent.run(project_id, user_id=project_user_id)
        synthesis_duration = time.time() - synthesis_start

        # Remove the placeholder run before creating the final one (async to avoid blocking)
        supabase = vectorization_service.supabase
        await loop.run_in_executor(
            None,
            lambda: supabase.table("synthesis_runs")
            .delete()
            .eq("id", run_id)
            .execute(),
        )

        # Write complete synthesis results (this creates the synthesis_runs record with themes)
        from app.services.synthesis.logbook import write_run_from_state

        await write_run_from_state(project_id, final_state)

        # Persist synthesis _total wall-clock timing
        try:
            from app.services.timing import persist_timing

            persist_timing(project_id, "synthesis", "_total", synthesis_duration)
        except Exception as e:
            logger.warning("Failed to persist synthesis _total timing: %s", e)

        # Mark project as completed (async to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: vectorization_service.supabase.table("analysis_projects")
            .update({"status": "completed"})
            .eq("id", project_id)
            .execute(),
        )

        logger.info(f"Synthesis completed for project {project_id}")

    except Exception as e:
        # Clean up placeholder run on failure (async to avoid blocking)
        try:
            supabase = vectorization_service.supabase
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: supabase.table("synthesis_runs")
                .delete()
                .eq("id", run_id)
                .execute(),
            )
        except Exception:
            pass  # Ignore cleanup errors

        # Still mark project as completed (analysis succeeded) (async to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: vectorization_service.supabase.table("analysis_projects")
            .update({"status": "completed"})
            .eq("id", project_id)
            .execute(),
        )

        logger.error(f"Synthesis failed for project {project_id}: {e}")
        raise


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

        # Check authorization (also verifies project exists)
        get_project_with_auth_check(project_id, current_user, "id, organization_id")

        # Build run config from request (query comes from search, not from project)
        query = request.get("query", "").strip()
        if not query:
            raise HTTPException(
                status_code=400, detail="Query is required for analysis"
            )

        # Extract search_context if provided (from new wizard)
        search_context = None
        if request.get("search_context"):
            from app.services.analysis.schemas import SearchContext

            try:
                search_context = SearchContext(**request["search_context"])
            except Exception as e:
                logger.warning(f"Failed to parse search_context: {e}")

        # Get sources - prefer from search_context, fallback to request
        sources = search_context.sources if search_context else []
        if not sources:
            sources = request.get("sources", ["openalex", "overton"])

        limit_value = request.get(
            "limit",
            search_context.max_results if search_context else 200,
        )
        if limit_value is None:
            limit_value = 200

        config = RunConfig(
            query=query,
            sources=sources,
            date_from=request.get("date_from")
            or request.get("since"),  # Support both chat and legacy formats
            date_to=request.get("date_to") or request.get("until"),
            limit=int(limit_value),
            screening_enabled=bool(request.get("screening", False)),
            relevance_enabled=bool(request.get("relevance_enabled", True)),
            retrieval_mode=request.get("mode", "semantic"),
            boolean_query=request.get("boolean_query"),
            use_abstracts_only=bool(request.get("use_abstracts_only", False)),
            # Chat interface parameters
            geography_filter=request.get("geography_filter"),
            sub_questions=request.get("sub_questions"),
            # New search wizard context
            search_context=search_context,
        )

        # Prepare search query metadata to save with the project
        if search_context:
            ctx = search_context.model_dump()
            search_query_data = {
                **ctx,
                "limit": ctx.get("max_results", config.limit),
                "mode": config.retrieval_mode,
                "relevance_enabled": config.relevance_enabled,
                "use_abstracts_only": config.use_abstracts_only,
                "boolean_queries": None,
                "semantic_query": None,
            }
            # Ensure optional fields are populated for storage consistency
            search_query_data.setdefault("sources", sources)
            search_query_data.setdefault(
                "geography", request.get("geography_filter", [])
            )
            search_query_data.setdefault("time_from", config.date_from)
            search_query_data.setdefault("time_to", config.date_to)
        else:
            # Fallback for legacy requests without search_context
            search_query_data = {
                "research_question": query,
                "population": [],
                "outcome": [],
                "screening_factors": [],
                "sources": sources,
                "geography": request.get("geography_filter", []),
                "time_preset": request.get("time_preset"),
                "time_from": config.date_from,
                "time_to": config.date_to,
                "limit": config.limit,
                "mode": config.retrieval_mode,
                "relevance_enabled": config.relevance_enabled,
                "use_abstracts_only": config.use_abstracts_only,
                "boolean_queries": None,
                "semantic_query": None,
            }

        # Update project status to running (async to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: vectorization_service.supabase.table("analysis_projects")
            .update({"status": "running", "search_query": search_query_data})
            .eq("id", project_id)
            .execute(),
        )

        # Run analysis
        service = AnalysisService(export_dir=settings.EXPORT_FILES_DIR)
        result = await service.run(
            config,
            project_id=project_id,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )

        # Update search query data with the generated queries
        search_query_data["boolean_queries"] = result.boolean_queries
        search_query_data["semantic_query"] = result.semantic_query

        # Update project with analysis results but keep status as "running" (async to avoid blocking)
        await loop.run_in_executor(
            None,
            lambda: vectorization_service.supabase.table("analysis_projects")
            .update(
                {
                    "run_id": result.run_id,
                    "total_references": result.total_references,
                    "relevant_references": result.relevant_references,
                    "search_query": search_query_data,
                    # Don't set status to "completed" yet - synthesis will do that
                }
            )
            .eq("id", project_id)
            .execute(),
        )

        # Trigger synthesis automatically
        try:
            await trigger_synthesis_for_project(project_id)
        except Exception as e:
            logger.error(f"Synthesis failed for project {project_id}: {e}")
            # Even if synthesis fails, mark analysis as completed (async to avoid blocking)
            await loop.run_in_executor(
                None,
                lambda: vectorization_service.supabase.table("analysis_projects")
                .update({"status": "completed"})
                .eq("id", project_id)
                .execute(),
            )

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


@router.post("/{project_id}/rerun-synthesis")
async def rerun_synthesis_for_project(
    project_id: str,
    request: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Manually rerun synthesis using cached analysis outputs.

    Args:
        project_id: Analysis project UUID.
        request: Payload containing rerun options.
        current_user: Authenticated user.

    Returns:
        JSON response confirming rerun initiation.
    """
    try:
        from app.services.synthesis.logbook import get_synthesis_status

        # Ensure project exists and user has access
        get_project_with_auth_check(project_id, current_user, "id, organization_id")

        force = bool(request.get("force", True))
        invalidate_previous = bool(request.get("invalidate_previous", True))

        current_status = await get_synthesis_status(project_id)
        if current_status == "running" and not force:
            raise HTTPException(
                status_code=409,
                detail="Synthesis is already running for this project; rerun with force=true to override.",
            )

        await trigger_synthesis_for_project(
            project_id, force=force, invalidate_previous=invalidate_previous
        )

        return {
            "project_id": project_id,
            "status": "started",
            "force": force,
            "invalidate_previous": invalidate_previous,
            "previous_status": current_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rerunning synthesis for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to rerun synthesis: {str(e)}"
        )


@router.get("/{project_id}/documents")
async def get_project_documents(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get all documents for an analysis project.

    Returns all documents including non-relevant and non-evidence documents.
    Each document includes:
    - is_relevant: whether it passed relevance screening
    - is_evidence: whether it's an evidence document (not "Other (Non-evidence documents)")
    - is_relevant_evidence: convenience flag combining both checks
    """
    try:
        get_project_with_auth_check(project_id, current_user, "id, organization_id")
        return get_project_documents_data(project_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching documents for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project documents")


@router.get("/{project_id}/charts-data")
async def get_charts_data_endpoint(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get aggregated chart data for an analysis project"""
    try:
        return get_project_charts_data(project_id)
    except Exception as e:
        logger.error(f"Error fetching charts data for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch charts data")


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
        extractions = filter_prevalence_only_extractions(extractions_result.data or [])
        return {
            "extractions": extractions,
            "total": len(extractions),
        }

    except Exception as e:
        logger.error(f"Error fetching extractions for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch project extractions"
        )


@router.get(
    "/{project_id}/thematic-groups",
    response_model=List[ThematicGroup],
    summary="Get thematic groups for Evidence view (Level 1)",
)
async def get_thematic_groups(
    project_id: str,
    theme_type: str = Query(..., enum=["intervention", "issue"]),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return thematic groups by type via Supabase RPC for the Evidence view."""
    try:
        response = vectorization_service.supabase.rpc(
            "get_project_thematic_groups_by_type",
            {"p_project_id": project_id, "p_theme_type": theme_type},
        ).execute()

        data = response.data or []
        return [ThematicGroup(**item) for item in data]
    except Exception as e:
        logger.error(f"Error fetching thematic groups for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch thematic groups")


@router.get(
    "/{project_id}/thematic-groups/{theme_id}/items",
    response_model=List[EvidenceItem],
    summary="Get level-2 items for a thematic group (Evidence view)",
)
async def get_thematic_group_items(
    project_id: str,
    theme_id: str,
    item_type: str = Query(
        ..., description="Type of items", pattern="^(intervention|issue)$"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return items for a thematic group via Supabase RPC.

    Uses get_theme_items_rich RPC with parameters p_theme_id and p_item_type.
    """
    try:
        response = vectorization_service.supabase.rpc(
            "get_theme_items_rich",
            {"p_theme_id": theme_id, "p_item_type": item_type},
        ).execute()

        raw_items = response.data or []
        # RPC returns JSONB array directly as response.data
        return [EvidenceItem(**item) for item in raw_items]
    except Exception as e:
        logger.error(
            f"Error fetching theme items for project {project_id}, theme {theme_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to fetch theme items")


@router.get("/{project_id}/interventions")
async def get_project_interventions(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get aggregated interventions data for an analysis project"""
    try:
        return get_project_interventions_data(project_id)
    except Exception as e:
        logger.error(f"Error fetching interventions for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch project interventions"
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
                    # Map citation_count (database) to cited_by_count (frontend)
                    "cited_by_count": document.get("citation_count"),
                },
                "extraction": None,
                "message": "No extraction results available for this document",
            }

        # Parse and organize the extraction data
        issues = extraction_results.get("issues", [])
        interventions = extraction_results.get("interventions", [])
        mappings = extraction_results.get("mappings", [])
        results = filter_prevalence_only_results(extraction_results.get("results", []))
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
                # Map citation_count (database) to cited_by_count (frontend)
                "cited_by_count": document.get("citation_count"),
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


@router.post("/{project_id}/chat")
async def chat_with_project(
    project_id: str,
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    """Chat with the analysis project using RAG over collected evidence."""
    try:
        # Check authorization
        get_project_with_auth_check(project_id, current_user, "id, organization_id")

        # Generate chat response using the chatbot service
        response = await chatbot_service.chat(project_id, request)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in chat for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Chat request failed. Please try again."
        )


@router.post("/{project_id}/chat/stream")
async def stream_chat_with_project(
    project_id: str,
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream chat activity and the final assistant response for a project."""
    try:
        get_project_with_auth_check(project_id, current_user, "id, organization_id")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error authorizing chat stream for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Chat request failed. Please try again."
        )

    async def _event_stream():
        async for event in chatbot_service.stream_chat_events(project_id, request):
            yield json.dumps(event) + "\n"

    return StreamingResponse(
        _event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/{project_id}/findings",
    response_model=List[Finding],
    summary="Get Detailed Findings for a Specific Intervention or Issue",
)
async def get_detailed_findings(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    intervention_name: Optional[str] = Query(
        None, description="Filter by intervention name"
    ),
    issue_theme: Optional[str] = Query(None, description="Filter by issue label/theme"),
):
    """Get flattened findings for an intervention or issue."""
    try:
        return await get_findings(
            project_id,
            intervention_name=intervention_name,
            issue_theme=issue_theme,
        )
    except Exception as e:
        logger.error(f"Error fetching findings for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch findings")


@router.get("/{project_id}/navigator-overview")
async def get_navigator_overview(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Lightweight overview for the interventions navigator.

    Returns theme names, impact/evidence scores, and study counts
    using parallel DB queries. Much faster than the full navigator endpoint.
    """
    try:
        return get_navigator_overview_data(project_id)
    except Exception as e:
        logger.error(f"Error fetching navigator overview for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch navigator overview"
        )


@router.get("/{project_id}/issue-intervention-navigator")
async def get_issue_intervention_navigator(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get issue-intervention navigator data using synthesis themes and assignments."""
    try:
        return get_navigator_data(project_id)
    except Exception as e:
        logger.error(
            f"Error fetching issue-intervention navigator for project {project_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to fetch navigator data")


@router.get("/{project_id}/navigator-stats")
async def get_navigator_stats(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get lightweight navigator stats (intervention theme and extraction counts).

    Much cheaper than the full navigator endpoint — queries only synthesis_themes
    and theme_assignments + analysis_extractions for distinct label counts.
    """
    try:
        sb = vectorization_service.supabase

        runs_res = (
            sb.table("synthesis_runs")
            .select("id")
            .eq("analysis_project_id", project_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not runs_res.data:
            return {"intervention_group_count": 0, "intervention_count": 0}

        run_id = runs_res.data[0]["id"]

        themes_res = (
            sb.table("synthesis_themes")
            .select("id, theme_type")
            .eq("synthesis_run_id", run_id)
            .eq("theme_type", "intervention")
            .execute()
        )
        intervention_theme_count = len(themes_res.data or [])
        intervention_theme_ids = [t["id"] for t in (themes_res.data or [])]

        if not intervention_theme_ids:
            return {
                "intervention_group_count": 0,
                "intervention_count": 0,
            }

        assignments_res = (
            sb.table("theme_assignments")
            .select("extraction_id")
            .eq("synthesis_run_id", run_id)
            .in_("synthesis_theme_id", intervention_theme_ids)
            .execute()
        )
        extraction_ids = list(
            {
                a["extraction_id"]
                for a in (assignments_res.data or [])
                if a.get("extraction_id")
            }
        )

        unique_labels: set[str] = set()
        if extraction_ids:
            extractions_res = (
                sb.table("analysis_extractions")
                .select("label")
                .in_("id", extraction_ids)
                .execute()
            )
            for e in extractions_res.data or []:
                if e.get("label"):
                    unique_labels.add(e["label"])

        return {
            "intervention_group_count": intervention_theme_count,
            "intervention_count": len(unique_labels),
        }
    except Exception as e:
        logger.error(f"Error fetching navigator stats for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch navigator stats")


@router.get("/{project_id}/synthesis/outcome-themes/{outcome_theme_id}/contributions")
async def get_outcome_theme_contributions(
    project_id: str,
    outcome_theme_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get contributing outcome extractions for a synthesis outcome theme."""
    try:
        get_project_with_auth_check(project_id, current_user, "id, organization_id")
        return get_outcome_contributions_data(project_id, outcome_theme_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching outcome theme contributions for {outcome_theme_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch outcome theme contributions",
        )


@router.get("/{project_id}/debug-themes")
async def debug_themes(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Debug endpoint to check theme data structure."""
    try:
        # Get themes via RPC (what we're currently using)
        issue_themes_response = vectorization_service.supabase.rpc(
            "get_project_thematic_groups_by_type",
            {"p_project_id": project_id, "p_theme_type": "issue"},
        ).execute()

        intervention_themes_response = vectorization_service.supabase.rpc(
            "get_project_thematic_groups_by_type",
            {"p_project_id": project_id, "p_theme_type": "intervention"},
        ).execute()

        # Also get themes directly from synthesis_themes table (what Summary tab uses)
        # Get most recent completed synthesis run
        runs_res = (
            vectorization_service.supabase.table("synthesis_runs")
            .select("*")
            .eq("analysis_project_id", project_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        direct_themes = []
        if runs_res.data:
            run_id = runs_res.data[0]["id"]
            themes_res = (
                vectorization_service.supabase.table("synthesis_themes")
                .select("*")
                .eq("synthesis_run_id", run_id)
                .execute()
            )
            direct_themes = themes_res.data or []

        return {
            "rpc_issue_themes": issue_themes_response.data or [],
            "rpc_intervention_themes": intervention_themes_response.data or [],
            "rpc_issue_count": len(issue_themes_response.data or []),
            "rpc_intervention_count": len(intervention_themes_response.data or []),
            "direct_themes": direct_themes,
            "direct_issue_themes": [
                t for t in direct_themes if t.get("theme_type") == "issue"
            ],
            "direct_intervention_themes": [
                t for t in direct_themes if t.get("theme_type") == "intervention"
            ],
        }
    except Exception as e:
        logger.error(f"Error in debug themes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_project_title(project_id: str) -> str:
    """Get project title for filename generation"""
    try:
        result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("title")
            .eq("id", project_id)
            .execute()
        )

        if result.data and len(result.data) > 0:
            title = result.data[0].get("title", "")
            # Clean title for filename: replace spaces with underscores, remove special chars
            import re

            clean_title = re.sub(
                r"[^\w\s-]", "", title
            )  # Remove special chars except spaces and hyphens
            clean_title = re.sub(
                r"[-\s]+", "_", clean_title
            )  # Replace spaces and hyphens with underscores
            clean_title = clean_title.strip("_")  # Remove leading/trailing underscores
            return clean_title[:50] if clean_title else "project"  # Limit length
        else:
            return "project"
    except Exception as e:
        logger.warning(f"Failed to get project title for {project_id}: {e}")
        return "project"


def prepare_interventions_csv_data(project_id: str) -> pd.DataFrame:
    """Prepare flattened interventions data for CSV export"""
    # Reuse the same logic as the issue-intervention-navigator endpoint
    # but flatten the nested structure into a tabular format

    # Get most recent completed synthesis run
    runs_res = (
        vectorization_service.supabase.table("synthesis_runs")
        .select("*")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return pd.DataFrame()

    run_id = runs_res.data[0]["id"]

    # Get all themes for this synthesis run
    themes_res = (
        vectorization_service.supabase.table("synthesis_themes")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    if not themes_res.data:
        return pd.DataFrame()

    themes = themes_res.data
    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]

    # Get theme assignments to link themes to extractions
    assignments_res = (
        vectorization_service.supabase.table("theme_assignments")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    assignments = assignments_res.data or []

    # Build mappings: theme_id -> [extraction_ids]
    theme_to_extractions = {}
    for assignment in assignments:
        if not assignment:
            continue
        theme_id = assignment.get("synthesis_theme_id")
        extraction_id = assignment.get("extraction_id")
        if theme_id and extraction_id:
            if theme_id not in theme_to_extractions:
                theme_to_extractions[theme_id] = []
            theme_to_extractions[theme_id].append(extraction_id)

    # Get all extractions for this project
    extractions_res = (
        vectorization_service.supabase.table("analysis_extractions")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    extractions = extractions_res.data or []
    extractions_by_id = {str(e["id"]): e for e in extractions if e and e.get("id")}

    # Get documents for metadata and scores
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    documents = docs_result.data or []
    docs_by_id = {str(d["id"]): d for d in documents if d and d.get("id")}

    # Build flattened CSV data
    csv_rows = []

    for issue_theme in issue_themes:
        issue_theme_id = issue_theme["id"]
        issue_theme_name = issue_theme["theme_name"]
        issue_theme_description = issue_theme.get("summary_description", "")
        issue_frequency = issue_theme.get("frequency", 0)

        # Get extractions assigned to this issue theme
        issue_extraction_ids = theme_to_extractions.get(issue_theme_id, [])

        for intervention_theme in intervention_themes:
            intervention_theme_id = intervention_theme["id"]
            intervention_theme_name = intervention_theme["theme_name"]
            intervention_description = intervention_theme.get("summary_description", "")

            # Get extractions assigned to this intervention theme
            intervention_extraction_ids = theme_to_extractions.get(
                intervention_theme_id, []
            )

            # Find documents that have both issue and intervention extractions
            for ext_id in intervention_extraction_ids:
                extraction = extractions_by_id.get(str(ext_id))
                if not extraction or not extraction.get("analysis_document_id"):
                    continue

                doc = docs_by_id.get(str(extraction["analysis_document_id"]))
                if not doc:
                    continue

                # Check if this document also has the issue theme
                doc_has_issue = False
                for issue_ext_id in issue_extraction_ids:
                    issue_extraction = extractions_by_id.get(str(issue_ext_id))
                    if issue_extraction and str(
                        issue_extraction.get("analysis_document_id")
                    ) == str(extraction["analysis_document_id"]):
                        doc_has_issue = True
                        break

                if not doc_has_issue:
                    continue

                raw_data = extraction.get("raw_data", {})

                extraction_results = doc.get("extraction_results", {})
                impact_score = doc.get("impact_score")
                evidence_info = get_or_calculate_document_evidence(doc)
                evidence_score = evidence_info.get("stars")

                # Extract results from document's extraction_results
                interventions_data = extraction_results.get("interventions", [])
                results_data = filter_prevalence_only_results(
                    extraction_results.get("results", [])
                )

                intervention_name = extraction.get("label", raw_data.get("name", ""))

                # Find matching intervention and its results
                intervention_results = []
                for i, intervention_data in enumerate(interventions_data):
                    if (
                        intervention_data.get("name") == intervention_name
                        or intervention_data.get("label") == intervention_name
                    ):
                        # Find results for this intervention by idx
                        for result in results_data:
                            if result.get("intervention_idx") == i:
                                intervention_results.append(result)
                        break

                # If no results found, create one empty row to show the intervention
                if not intervention_results:
                    intervention_results = [{}]

                # Create a row for each result
                for result in intervention_results:
                    csv_rows.append(
                        {
                            "Key Issue Theme": issue_theme_name,
                            "Key Issue Description": issue_theme_description,
                            "Issue Frequency": issue_frequency,
                            "Intervention Theme": intervention_theme_name,
                            "Intervention Theme Description": intervention_description,
                            "Intervention Name": intervention_name,
                            "Intervention Description": extraction.get(
                                "description", raw_data.get("description", "")
                            ),
                            "Country": raw_data.get("country", ""),
                            "Evidence Category": doc.get("evidence_category", ""),
                            "Sample Size": raw_data.get("sample_size", ""),
                            "Impact Score": impact_score,
                            "Evidence Score": evidence_score,
                            "Outcome Variable": result.get("outcome_variable", ""),
                            # Support both 'direction' (new) and 'effect_direction' (legacy)
                            "Effect Direction": result.get("direction")
                            or result.get("effect_direction", ""),
                            "Effect Size": result.get("effect_size", ""),
                            "P-Value": result.get("p_value", ""),
                            "Uncertainty": result.get("uncertainty", ""),
                            # SR-specific fields for meta-analysis results
                            "Heterogeneity I2": result.get("heterogeneity_I2", ""),
                            "Tau2": result.get("tau2", ""),
                            "Summary Statistic": result.get("summary_statistic", ""),
                            "Estimate Level": result.get("estimate_level", ""),
                            "Result Text": result.get("result_text", ""),
                            "Population Measured": result.get(
                                "population_measured", ""
                            ),
                            "Document ID": doc.get("doc_id", ""),
                            "Document Title": doc.get("title", ""),
                            "Document Source": doc.get("source", ""),
                            "Document URL": doc.get("landing_page_url", ""),
                            "Document DOI": doc.get("doi", ""),
                        }
                    )

    return pd.DataFrame(csv_rows)


def prepare_documents_csv_data(project_id: str) -> pd.DataFrame:
    """Prepare documents data for CSV export"""
    try:
        # Get all documents for this project
        docs_result = (
            vectorization_service.supabase.table("analysis_documents")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )

        documents = docs_result.data or []
        logger.info(f"Found {len(documents)} documents for project {project_id}")

        if not documents:
            logger.info(f"No documents found for project {project_id}")
            return pd.DataFrame()

        # Transform documents into flat structure
        csv_rows = []
        for i, doc in enumerate(documents):
            try:
                if not doc:  # Skip None documents
                    logger.warning(f"Skipping None document at index {i}")
                    continue

                evidence_category = doc.get("evidence_category", "")
                evidence_info = get_or_calculate_document_evidence(doc)
                evidence_score = evidence_info.get("stars")
                evidence_justification = evidence_info.get("justification") or ""

                # Handle authors field safely
                authors = doc.get("authors", [])
                if not isinstance(authors, list):
                    authors = []
                author_institutions = doc.get("author_institutions", [])
                if not isinstance(author_institutions, list):
                    author_institutions = []

                csv_rows.append(
                    {
                        "Title": doc.get("title", ""),
                        "Authors": ", ".join(authors) if authors else "",
                        "Institutions": ", ".join(author_institutions)
                        if author_institutions
                        else "",
                        "Year": doc.get("year", ""),
                        "DOI": doc.get("doi", ""),
                        "Source": doc.get("source", ""),
                        "Country": doc.get("source_country", ""),
                        "Type": doc.get("source_type", ""),
                        "Venue": doc.get("venue", ""),
                        "Relevance": "Yes" if doc.get("is_relevant", False) else "No",
                        "Relevance Reason": doc.get("relevance_reason", ""),
                        "Confidence": doc.get("relevance_confidence", ""),
                        "Evidence Category": evidence_category,
                        "Evidence Score": (
                            evidence_score if evidence_score is not None else ""
                        ),
                        "Evidence Justification": evidence_justification,
                        "Impact Score": doc.get("impact_score", ""),
                        "Impact Justification": doc.get("impact_score_label", ""),
                        "Extraction Status": doc.get("extraction_status", ""),
                        "Text Source": doc.get("text_source", ""),
                        "Full Text Available": "Yes"
                        if doc.get("full_text_available", False)
                        else "No",
                        "Top Line": doc.get("top_line", ""),
                        "Abstract": doc.get("abstract_or_summary", ""),
                        "Landing Page URL": doc.get("landing_page_url", ""),
                        "Citation Count": doc.get("citation_count", ""),
                    }
                )
            except Exception as doc_error:
                logger.error(f"Error processing document {i}: {doc_error}")
                logger.error(f"Document data: {doc}")
                continue

        logger.info(f"Successfully processed {len(csv_rows)} documents into CSV rows")
        return pd.DataFrame(csv_rows)

    except Exception as e:
        logger.error(f"Error in prepare_documents_csv_data: {e}")
        raise


@router.get("/{project_id}/download/interventions-csv")
async def download_interventions_csv(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Generate and download interventions navigator data as CSV"""
    try:
        logger.info(f"Preparing interventions CSV for project {project_id}")

        # Prepare the DataFrame
        df = prepare_interventions_csv_data(project_id)

        if df.empty:
            return JSONResponse(
                status_code=404,
                content={"error": "No interventions data found for this project"},
            )

        # Store DataFrame for download
        download_key = download_service.store_dataframe(
            df,
            current_user.user_id,
            download_type="interventions",
            filename_prefix="interventions_navigator",
            project_id=project_id,
        )

        return {"download_key": download_key}

    except Exception as e:
        logger.error(f"Error preparing interventions CSV for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to prepare interventions CSV"
        )


@router.get("/{project_id}/download/documents-csv")
async def download_documents_csv(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Generate and download documents data as CSV"""
    try:
        logger.info(f"Preparing documents CSV for project {project_id}")
        logger.info(f"User: {current_user.user_id}")

        # Prepare the DataFrame
        df = prepare_documents_csv_data(project_id)

        logger.info(f"DataFrame shape: {df.shape}")
        logger.info(f"DataFrame columns: {df.columns.tolist()}")

        if df.empty:
            logger.warning(f"No documents found for project {project_id}")
            return JSONResponse(
                status_code=404,
                content={"error": "No documents found for this project"},
            )

        # Store DataFrame for download
        logger.info(f"Storing DataFrame for download, size: {len(df)} rows")
        download_key = download_service.store_dataframe(
            df,
            current_user.user_id,
            download_type="documents",
            filename_prefix="project_documents",
            project_id=project_id,
        )

        logger.info(f"Generated download key: {download_key}")
        return {"download_key": download_key}

    except Exception as e:
        logger.error(f"Error preparing documents CSV for project {project_id}: {e}")
        logger.error(f"Exception type: {type(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to prepare documents CSV")


@router.get("/{project_id}/feedback")
async def get_project_feedback(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get user feedback for a specific project from the user_feedback table"""
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

        # Get feedback for this user and project
        feedback_result = (
            vectorization_service.supabase.table("user_feedback")
            .select("rating, comment, updated_at")
            .eq("project_id", project_id)
            .eq("user_id", current_user.user_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if feedback_result.data and len(feedback_result.data) > 0:
            feedback = feedback_result.data[0]
            return {
                "feedback": {
                    "rating": feedback.get("rating"),
                    "comment": feedback.get("comment", ""),
                    "updated_at": feedback.get("updated_at"),
                }
            }
        return {"feedback": None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching feedback for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project feedback")


@router.post("/{project_id}/feedback")
async def save_project_feedback(
    project_id: str,
    request: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Save user feedback for a specific project as a new row in user_feedback table (no overwrite)"""
    try:
        # Validate request
        rating = request.get("rating")
        comment = request.get("comment", "").strip()
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            raise HTTPException(
                status_code=400, detail="Rating must be an integer between 1 and 5"
            )
        if len(comment) > 500:
            raise HTTPException(
                status_code=400, detail="Comment must be 500 characters or less"
            )
        # Check if project exists
        project_result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("id")
            .eq("id", project_id)
            .execute()
        )
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        # Insert new feedback row
        feedback_data = {
            "project_id": project_id,
            "user_id": current_user.user_id,
            "user_email": getattr(current_user, "email", None),
            "user_name": getattr(current_user, "name", None),
            "rating": rating,
            "comment": comment,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        result = (
            vectorization_service.supabase.table("user_feedback")
            .insert(feedback_data)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to save feedback")
        return {
            "message": "Feedback saved successfully",
            "feedback": {
                "rating": rating,
                "comment": comment,
                "updated_at": feedback_data["updated_at"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving feedback for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save project feedback")


@router.post("/generate-population-options", response_model=PopulationOptionsResponse)
async def generate_population_options(
    request: PopulationOptionsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate population options for a research question using AI, ordered from broad to narrow"""
    service = SearchWizardService()
    population_options = await service.generate_population_options(
        research_question=request.research_question,
        max_options=request.max_options,
        user_id=current_user.user_id,
    )

    if not population_options:
        raise HTTPException(
            status_code=500, detail="Failed to generate population options"
        )

    return PopulationOptionsResponse(
        research_question=request.research_question,
        population_options=population_options,
    )


@router.post("/generate-outcome-options", response_model=OutcomeOptionsResponse)
async def generate_outcome_options(
    request: OutcomeOptionsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate outcome options for a research question using AI, ordered from broad to narrow"""
    service = SearchWizardService()
    outcome_options = await service.generate_outcome_options(
        research_question=request.research_question,
        max_options=request.max_options,
        user_id=current_user.user_id,
    )

    if not outcome_options:
        raise HTTPException(
            status_code=500, detail="Failed to generate outcome options"
        )

    return OutcomeOptionsResponse(
        research_question=request.research_question, outcome_options=outcome_options
    )


@router.post(
    "/generate-inner-setting-options", response_model=InnerSettingOptionsResponse
)
async def generate_inner_setting_options(
    request: InnerSettingOptionsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate inner setting options for a research question using AI"""
    service = SearchWizardService()
    inner_setting_options = await service.generate_inner_setting_options(
        research_question=request.research_question,
        max_options=request.max_options,
        user_id=current_user.user_id,
    )

    if not inner_setting_options:
        raise HTTPException(
            status_code=500, detail="Failed to generate inner setting options"
        )

    return InnerSettingOptionsResponse(
        research_question=request.research_question,
        inner_setting_options=inner_setting_options,
    )


@router.post(
    "/generate-additional-questions", response_model=AdditionalQuestionsResponse
)
async def generate_additional_questions(
    request: AdditionalQuestionsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate additional research questions based on the main question, population, and outcome"""
    service = SearchWizardService()
    additional_questions = await service.generate_additional_questions(
        research_question=request.research_question,
        population_selected=request.population_selected,
        outcome_selected=request.outcome_selected,
        max_questions=request.max_questions,
        user_id=current_user.user_id,
    )

    if not additional_questions:
        raise HTTPException(
            status_code=500, detail="Failed to generate additional questions"
        )

    return AdditionalQuestionsResponse(
        research_question=request.research_question,
        additional_questions=additional_questions,
    )
