from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import uuid
import io
from datetime import datetime
from app.core.models import (
    SearchRequest,
    OpenAlexSearchRequest,
    MediaCloudSearchRequest,
    OvertonSearchRequest,
    SearchResultWithDownload,
)
from app.core.auth import get_current_user, CurrentUser

from app.services.openalex import OpenAlexService
from app.services.mediacloud import MediaCloudService
from app.services.overton import OvertonService
from app.services.screening import ScreeningService
from app.services.summary import SummaryService
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
