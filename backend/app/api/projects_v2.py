from fastapi import APIRouter, HTTPException, Depends, Query
import logging
from datetime import datetime
import uuid
from typing import Optional, List

from app.core.auth import get_current_user, CurrentUser
from app.services.vectorization import vectorization_service
from app.services.chatbot import ChatRequest, ChatResponse
from app.services.chatbot.chat_service import chatbot_service
from app.services.synthesis.schemas import (
    SynthesisSummary,
    Finding,
    ThematicGroup,
    EvidenceItem,
)
from app.services.synthesis.service import SynthesisService
from app.services.synthesis.agent import SynthesisAgent, SynthesisState
from app.services.synthesis.logbook import read_cached_summary, write_run_from_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis-projects", tags=["analysis-projects"])


# END-I - INFO REGION END


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
    """Invoke the synthesis agent to get executive briefing and aggregated tables."""
    try:
        # Cache read via Supabase
        cached = await read_cached_summary(project_id)
        if cached:
            return cached

        # Cache miss: run agent
        synthesis_agent = SynthesisAgent()
        final_state: SynthesisState = await synthesis_agent.run(project_id)

        # Cache write via Supabase
        await write_run_from_state(project_id, final_state)

        # Return fresh results
        return SynthesisSummary(
            executive_briefing=final_state.get(
                "executive_briefing", "Failed to generate briefing."
            ),
            key_issues=final_state.get("aggregated_issues", []),
            interventions=final_state.get("aggregated_interventions", []),
        )
    except Exception as e:
        logger.error(f"Error running synthesis agent for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to build synthesis summary")


@router.get("")
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

        # Map database field names to frontend expectations for documents
        documents = []
        for doc in docs_result.data:
            doc_copy = doc.copy()
            # Map citation_count (database) to cited_by_count (frontend)
            if "citation_count" in doc_copy:
                doc_copy["cited_by_count"] = doc_copy["citation_count"]
            documents.append(doc_copy)

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
            "documents": documents,
            "extractions": extractions_result.data,
            "document_count": len(documents),
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

        # Clean up chunks that reference analysis_documents from this project
        try:
            # First, get all analysis_documents.id values for this project
            docs_result = (
                vectorization_service.supabase.table("analysis_documents")
                .select("id")
                .eq("analysis_project_id", project_id)
                .execute()
            )

            analysis_doc_ids = [doc["id"] for doc in docs_result.data]

            # Delete chunks that reference these analysis_documents
            if analysis_doc_ids:
                vectorization_service.supabase.table("chunks").delete().in_(
                    "document_id", analysis_doc_ids
                ).execute()
                logger.info(
                    f"Deleted chunks for {len(analysis_doc_ids)} analysis documents"
                )

            # Also delete any chunks by project_id (legacy/fallback)
            vectorization_service.supabase.table("chunks").delete().eq(
                "project_id", project_id
            ).execute()

            logger.info(f"Cleaned up chunks for analysis project {project_id}")
        except Exception as e:
            logger.warning(f"Failed to clean up chunks for project {project_id}: {e}")
            # Don't fail the deletion if chunk cleanup fails

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

        # Map access_types to appropriate sources
        access_types = request.get("access_types", [])
        sources = []
        if "academic" in access_types:
            sources.append("openalex")
        if "policy" in access_types:
            sources.append("overton")

        # Fallback to default sources if none specified
        if not sources:
            sources = request.get("sources", ["openalex", "overton"])

        config = RunConfig(
            query=query,
            sources=sources,
            date_from=request.get("date_from")
            or request.get("since"),  # Support both chat and legacy formats
            date_to=request.get("date_to") or request.get("until"),
            limit=int(request.get("limit", 200)),
            screening_enabled=bool(request.get("screening", False)),
            relevance_enabled=bool(request.get("relevance_enabled", True)),
            retrieval_mode=request.get("mode", "semantic"),
            boolean_query=request.get("boolean_query"),
            use_abstracts_only=bool(request.get("use_abstracts_only", False)),
            # Chat interface parameters
            geography_filter=request.get("geography_filter"),
            access_types=access_types,
            sub_questions=request.get("sub_questions"),
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
        # Map database field names to frontend expectations
        documents = []
        for doc in docs_result.data:
            doc_copy = doc.copy()
            # Map citation_count (database) to cited_by_count (frontend)
            if "citation_count" in doc_copy:
                doc_copy["cited_by_count"] = doc_copy["citation_count"]
            documents.append(doc_copy)

        return {"documents": documents, "total": len(documents)}

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
        ..., description="Type of items", regex="^(intervention|issue)$"
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
        # Get all documents for this project that have extraction results
        docs_result = (
            vectorization_service.supabase.table("analysis_documents")
            .select("*")
            .eq("analysis_project_id", project_id)
            .not_.is_("extraction_results", "null")
            .execute()
        )

        if not docs_result.data:
            return {"interventions": [], "total": 0}

        # Process interventions from all documents
        aggregated_interventions = {}

        def get_study_type_rank(study_type):
            """Convert study type letter to numeric rank for sorting (lower = better)
            g (RCT) is highest quality, empty is lowest quality"""
            if not study_type:
                return 999  # Empty types go to the end (lowest quality)

            # Study type is already a letter (a-j) from Maryland Scientific Methods Scale
            study_type_clean = study_type.strip().lower()

            # Reverse ranking so 'g' (RCT) gets rank 1 (highest), 'a' gets rank 8
            if study_type_clean == "g":  # Randomised controlled trial - highest quality
                return 1
            elif study_type_clean == "h":  # Meta-analysis
                return 2
            elif study_type_clean == "f":  # Quasi-experimental study
                return 3
            elif study_type_clean == "e":  # Comparison of outcomes in treated group
                return 4
            elif study_type_clean == "d":  # Study measures outcome pre and post
                return 5
            elif study_type_clean == "c":  # Cross-sectional with control variables
                return 6
            elif study_type_clean == "b":  # Study measures outcome pre and post
                return 7
            elif study_type_clean == "a":  # Purely cross-sectional study
                return 8
            elif study_type_clean == "i":  # Policy recommendation/theoretical modelling
                return 9
            elif (
                study_type_clean == "j"
            ):  # News article/opinion piece/government announcement
                return 10
            else:
                return 999  # Unknown types go to the end

        for document in docs_result.data:
            extraction_results = document.get("extraction_results", {})
            interventions = extraction_results.get("interventions", [])
            results = extraction_results.get("results", [])

            # Group results by intervention
            results_by_intervention = {}
            for result in results:
                intervention_idx = result.get("intervention_idx")
                if intervention_idx is not None:
                    if intervention_idx not in results_by_intervention:
                        results_by_intervention[intervention_idx] = []
                    results_by_intervention[intervention_idx].append(result)

            # Process each intervention
            for intervention in interventions:
                intervention_name = intervention.get("name", "Unknown Intervention")
                intervention_idx = intervention.get("idx")

                # Create a unique key for this intervention (could be improved with better deduplication)
                intervention_key = f"{intervention_name}_{intervention.get('type', '')}_{intervention.get('country', '')}"

                if intervention_key not in aggregated_interventions:
                    # Initialize intervention data
                    aggregated_interventions[intervention_key] = {
                        "name": intervention_name,
                        "type": intervention.get("type", "Unknown"),
                        "country": intervention.get("country", "Unknown"),
                        "description": intervention.get("description", ""),
                        "study_types": [],
                        "sample_sizes": [],
                        "result_count": 0,
                        "results_summary": [],
                        "highest_study_type": None,
                        "highest_study_type_rank": 999,
                        "documents": [],
                    }

                # Add document info
                aggregated_interventions[intervention_key]["documents"].append(
                    {
                        "doc_id": document.get("doc_id"),
                        "title": document.get("title"),
                        "source": document.get("source"),
                        "landing_page_url": document.get("landing_page_url"),
                    }
                )

                # Add study type if available
                study_type = intervention.get("study_type")
                if study_type:
                    aggregated_interventions[intervention_key]["study_types"].append(
                        study_type
                    )

                    # Update highest study type (lowest rank number = highest quality)
                    study_rank = get_study_type_rank(study_type)
                    if (
                        study_rank
                        < aggregated_interventions[intervention_key][
                            "highest_study_type_rank"
                        ]
                    ):
                        aggregated_interventions[intervention_key][
                            "highest_study_type"
                        ] = study_type
                        aggregated_interventions[intervention_key][
                            "highest_study_type_rank"
                        ] = study_rank

                # Add sample size if available
                sample_size = intervention.get("sample_size")
                if sample_size:
                    try:
                        aggregated_interventions[intervention_key][
                            "sample_sizes"
                        ].append(int(sample_size))
                    except (ValueError, TypeError):
                        pass  # Skip non-numeric sample sizes

                # Add result count and summaries for this intervention
                intervention_results = results_by_intervention.get(intervention_idx, [])
                aggregated_interventions[intervention_key]["result_count"] += len(
                    intervention_results
                )

                # Add results summaries with detailed information
                for result in intervention_results:
                    outcome = result.get("outcome_variable", "Unknown outcome")
                    direction = result.get("effect_direction", "unknown")
                    if outcome and outcome != "Unknown outcome":
                        result_detail = {
                            "outcome": outcome,
                            "direction": direction,
                            "effect_size": result.get("effect_size"),
                            "effect_size_type": result.get("effect_size_type"),
                            "p_value": result.get("p_value"),
                            "uncertainty": result.get("uncertainty"),
                            "result_text": result.get("result_text"),
                            "supporting_quote": result.get("supporting_quote"),
                            "population_measured": result.get("population_measured"),
                            "subgroup_or_dose": result.get("subgroup_or_dose"),
                        }
                        aggregated_interventions[intervention_key][
                            "results_summary"
                        ].append(result_detail)

        # Convert to list and add computed fields
        interventions_list = []
        for key, intervention_data in aggregated_interventions.items():
            # Calculate aggregate sample size
            sample_sizes = intervention_data["sample_sizes"]
            if sample_sizes:
                intervention_data["total_sample_size"] = sum(sample_sizes)
                intervention_data["avg_sample_size"] = sum(sample_sizes) / len(
                    sample_sizes
                )
            else:
                intervention_data["total_sample_size"] = None
                intervention_data["avg_sample_size"] = None

            # Deduplicate results summaries (keep the one with most details)
            unique_results = []
            seen_combinations = set()
            for result in intervention_data["results_summary"]:
                combo = (result["outcome"], result["direction"])
                if combo not in seen_combinations:
                    unique_results.append(result)
                    seen_combinations.add(combo)
                else:
                    # If we've seen this combination, keep the one with more details
                    existing_idx = next(
                        i
                        for i, r in enumerate(unique_results)
                        if (r["outcome"], r["direction"]) == combo
                    )
                    existing = unique_results[existing_idx]
                    # Count non-null values to determine which has more details
                    existing_details = sum(
                        1
                        for v in [
                            existing.get("effect_size"),
                            existing.get("p_value"),
                            existing.get("uncertainty"),
                        ]
                        if v
                    )
                    new_details = sum(
                        1
                        for v in [
                            result.get("effect_size"),
                            result.get("p_value"),
                            result.get("uncertainty"),
                        ]
                        if v
                    )
                    if new_details > existing_details:
                        unique_results[existing_idx] = result

            intervention_data["results_summary"] = unique_results

            # Clean up temporary fields
            del intervention_data["sample_sizes"]
            del intervention_data["study_types"]

            interventions_list.append(intervention_data)

        # Sort by highest study type rank (best first), then by result count
        interventions_list.sort(
            key=lambda x: (x["highest_study_type_rank"], -x["result_count"])
        )

        return {"interventions": interventions_list, "total": len(interventions_list)}

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
        # Verify project exists and user has access
        project_result = (
            vectorization_service.supabase.table("analysis_projects")
            .select("id")
            .eq("id", project_id)
            .single()
            .execute()
        )

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Generate chat response using the chatbot service
        response = await chatbot_service.chat(project_id, request)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process chat message")


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
    """Get flattened findings via service layer."""
    try:
        service = SynthesisService()
        return await service.get_findings(
            project_id,
            intervention_name=intervention_name,
            issue_theme=issue_theme,
        )
    except Exception as e:
        logger.error(f"Error fetching findings for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch findings")
