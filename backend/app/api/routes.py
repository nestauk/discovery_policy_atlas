from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import uuid
import io
import pandas as pd
from pathlib import Path
from datetime import datetime
from app.core.models import (
    SearchRequest,
    OpenAlexSearchRequest,
    MediaCloudSearchRequest,
    OvertonSearchRequest,
    SearchResultWithDownload,
)
from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings

from app.services.openalex import OpenAlexService
from app.services.mediacloud import MediaCloudService
from app.services.overton import OvertonService
from app.services.screening import ScreeningService
from app.services.summary import SummaryService
from app.services.analysis.service import AnalysisService
from app.services.analysis.schemas import RunConfig
from app.services.download import download_service
import logging

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/api/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Test endpoint to verify Clerk authentication"""
    return {"user_id": current_user.user_id, "email": current_user.email}


@router.post("/api/search", response_model=SearchResultWithDownload)
async def enhanced_search(
    request: SearchRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Enhanced search with screening, extraction, and synthesis"""
    session_id = str(uuid.uuid4())[:8]

    # 1. Fetch data from appropriate source
    if isinstance(request, OpenAlexSearchRequest):
        service = OpenAlexService()
        papers_df = await service.search(
            query=request.query,
            max_results=request.max_results,
            min_citations=request.min_citations,
            date_from=request.date_from,
            date_to=request.date_to,
        )
    elif isinstance(request, MediaCloudSearchRequest):
        service = MediaCloudService()
        papers_df = await service.search(
            query=request.query,
            max_results=request.max_results,
            date_from=request.date_from,
            date_to=request.date_to,
        )
    elif isinstance(request, OvertonSearchRequest):
        service = OvertonService()
        papers_df = await service.search(
            query=request.query,
            max_results=request.max_results,
            source_country=request.source_country,
            source_type=request.source_type,
            published_after=request.date_from,
            published_before=request.date_to,
            topics=request.topics,
            classifications=request.classifications,
            semantic_search=getattr(request, "semantic_search", True),
        )
    else:
        raise ValueError(f"Unsupported search request type: {type(request)}")

    screening_enabled = getattr(request, "screening_enabled", False)
    logger.info(
        f"screening_enabled received: {screening_enabled} (type: {type(screening_enabled)})"
    )
    if not screening_enabled:
        # Skip screening, mark all as relevant
        papers_df["is_relevant"] = True
        papers_df["relevance_reason"] = "Screening disabled"
        papers_df["confidence"] = 1.0
        relevant_df = papers_df
        screening_df = papers_df[
            ["id", "is_relevant", "relevance_reason", "confidence"]
        ]
    else:
        screening_texts = service.format_for_screening(papers_df)
        extraction_fields = getattr(request, "extraction_fields", None) or []
        screening_message = (
            f"Determine if this document is relevant to: {request.query}"
        )
        if getattr(request, "inclusion_criteria", None):
            screening_message += f"Determine if this document is relevant to: {request.query}.\nInclusion criteria: {request.inclusion_criteria}"
        screening_service = ScreeningService(
            system_message=screening_message, extra_fields=extraction_fields
        )
        screening_df = await screening_service.screen_batch(screening_texts, session_id)
        relevant_df = (
            papers_df.merge(screening_df, left_on="id", right_on="id", how="left")
            .assign(
                is_relevant=lambda x: x["is_relevant"].fillna(False),
                relevance_reason=lambda x: x["relevance_reason"].fillna("Not screened"),
                confidence=lambda x: x["confidence"].fillna(0.0),
            )
            .query("is_relevant == True")
        )

    papers_list = relevant_df.to_dict("records")

    # Store DataFrame for download if we have relevant results
    download_key = None
    if len(relevant_df) > 0:
        try:
            download_key = download_service.store_dataframe(
                relevant_df, request.query, current_user.user_id
            )
        except ValueError as e:
            # DataFrame too large - log warning but continue without download
            logger.warning(f"Could not store DataFrame for download: {e}")
            download_key = None

    return SearchResultWithDownload(
        papers=papers_list,
        total_found=len(papers_df),
        total_screened=len(screening_df),
        total_relevant=len(relevant_df),
        download_key=download_key,
    )


@router.get("/api/download/{download_key}")
async def download_csv(
    download_key: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Download search results as CSV"""
    # Get DataFrame from cache
    df = download_service.get_dataframe(download_key, current_user.user_id)

    if df is None:
        return JSONResponse(
            status_code=404, content={"error": "Download not found or expired"}
        )

    # Convert DataFrame to CSV
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    # Create filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"search_results_{timestamp}.csv"

    # Return as streaming response
    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/api/summary")
async def get_summary(
    request: Request, current_user: CurrentUser = Depends(get_current_user)
):
    data = await request.json()
    papers = data.get("papers", [])
    extraction_fields = data.get("extraction_fields", [])
    prompt = data.get("prompt", None)
    # You can use config or env for model params
    summary_service = SummaryService(
        model_name="gpt-4.1-mini", temperature=0.2, max_tokens=1024
    )
    summary = summary_service.summarize(papers, extraction_fields, prompt)
    return JSONResponse(content={"summary": summary})


@router.post("/api/analysis/run")
async def run_analysis(
    request: Request, current_user: CurrentUser = Depends(get_current_user)
):
    """Trigger the deterministic analysis pipeline with switches for screening/extraction/RAG."""
    body = await request.json()
    config = RunConfig(
        query=body.get("query", ""),
        sources=body.get("sources", ["openalex", "overton"]),
        date_from=body.get("since"),
        date_to=body.get("until"),
        limit=int(body.get("limit", 200)),
        screening_enabled=bool(body.get("screening", False)),
        relevance_enabled=bool(body.get("relevance_enabled", True)),
        retrieval_mode=body.get("mode", "semantic"),
        boolean_query=body.get("boolean_query"),
        use_abstracts_only=bool(body.get("use_abstracts_only", False)),
    )

    service = AnalysisService(export_dir=settings.EXPORT_FILES_DIR)
    result = await service.run(config)
    return JSONResponse(
        content={
            "run_id": result.run_id,
            "total_references": result.total_references,
            "relevant_references": result.relevant_references,
            "references_csv_path": result.references_csv_path,
            "extractions_json_path": result.extractions_json_path,
        }
    )


@router.get("/api/analysis/{run_id}/references")
async def get_analysis_references(
    run_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get the references CSV for a specific analysis run"""

    # Construct the path to the references CSV
    references_path = (
        Path(settings.EXPORT_FILES_DIR) / f"run_{run_id}" / "references.csv"
    )

    if not references_path.exists():
        return JSONResponse(
            status_code=404, content={"error": f"References not found for run {run_id}"}
        )

    try:
        # Read CSV and convert to JSON
        df = pd.read_csv(references_path)
        # Replace NaN values with None for JSON serialization
        df = df.fillna("")
        references_data = df.to_dict("records")

        return JSONResponse(
            content={
                "run_id": run_id,
                "total_references": len(references_data),
                "references": references_data,
            }
        )
    except Exception as e:
        logger.error(f"Error reading references for run {run_id}: {e}")
        return JSONResponse(
            status_code=500, content={"error": f"Failed to read references: {str(e)}"}
        )


@router.get("/api/analysis/{run_id}/extractions")
async def get_analysis_extractions(
    run_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get the extractions JSON for a specific analysis run"""
    import json
    from pathlib import Path

    # Construct the path to the extractions JSON
    extractions_path = (
        Path(settings.EXPORT_FILES_DIR) / f"run_{run_id}" / "extractions.json"
    )

    if not extractions_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": f"Extractions not found for run {run_id}"},
        )

    try:
        # Read JSON file
        with open(extractions_path, "r", encoding="utf-8") as f:
            extractions_data = json.load(f)

        return JSONResponse(content=extractions_data)
    except Exception as e:
        logger.error(f"Error reading extractions for run {run_id}: {e}")
        return JSONResponse(
            status_code=500, content={"error": f"Failed to read extractions: {str(e)}"}
        )


@router.get("/api/analysis/runs")
async def list_analysis_runs(current_user: CurrentUser = Depends(get_current_user)):
    """List all available analysis runs"""
    import json

    export_dir = Path(settings.EXPORT_FILES_DIR)
    if not export_dir.exists():
        return JSONResponse(content={"runs": []})

    runs = []
    for run_dir in export_dir.iterdir():
        if run_dir.is_dir() and run_dir.name.startswith("run_"):
            run_id = run_dir.name[4:]  # Remove "run_" prefix

            # Check if this run has results
            references_path = run_dir / "references.csv"
            extractions_path = run_dir / "extractions.json"

            run_info = {
                "run_id": run_id,
                "has_references": references_path.exists(),
                "has_extractions": extractions_path.exists(),
                "created_at": None,
            }

            # Try to get creation time from extractions metadata
            # To do: simplify this
            if extractions_path.exists():
                try:
                    with open(extractions_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if (
                            "run_metadata" in data
                            and "created_at" in data["run_metadata"]
                        ):
                            run_info["created_at"] = data["run_metadata"]["created_at"]
                except Exception:
                    pass

            runs.append(run_info)

    # Sort by creation time (newest first)
    runs.sort(key=lambda x: x["created_at"] or "", reverse=True)

    return JSONResponse(content={"runs": runs})
