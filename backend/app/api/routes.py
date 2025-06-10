from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from typing import Union
import uuid
from app.core.models import (
    SearchRequest, 
    OpenAlexSearchRequest, 
    MediaCloudSearchRequest,
    SimpleSearchResult,
)
from app.core.auth import get_current_user, CurrentUser

from app.services.openalex import OpenAlexService
from app.services.mediacloud import MediaCloudService
from app.services.screening import ScreeningService
from app.services.summary import SummaryService

router = APIRouter()

@router.get("/api/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Test endpoint to verify Clerk authentication"""
    return {
        "user_id": current_user.user_id,
        "email": current_user.email
    }

@router.post("/api/search", response_model=SimpleSearchResult)
async def enhanced_search(
    request: SearchRequest,
    current_user: CurrentUser = Depends(get_current_user)
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
            date_to=request.date_to
        )
    elif isinstance(request, MediaCloudSearchRequest):
        service = MediaCloudService()
        papers_df = await service.search(
            query=request.query,
            max_results=request.max_results,
            date_from=request.date_from,
            date_to=request.date_to
        )
    screening_enabled = getattr(request, 'screening_enabled', False)
    if not screening_enabled:
        # Skip screening, mark all as relevant
        papers_df['is_relevant'] = True
        papers_df['relevance_reason'] = 'Screening disabled'
        papers_df['confidence'] = 1.0
        relevant_df = papers_df
        screening_df = papers_df[['id', 'is_relevant', 'relevance_reason', 'confidence']]
    else:
        screening_texts = service.format_for_screening(papers_df)
        extraction_fields = getattr(request, 'extraction_fields', None) or []
        screening_message = f"Determine if this document is relevant to: {request.query}"
        if getattr(request, 'inclusion_criteria', None):
            screening_message += f"Determine if this document is relevant to: {request.query}.\nInclusion criteria: {request.inclusion_criteria}"
        screening_service = ScreeningService(
            system_message=screening_message,
            extra_fields=extraction_fields
        )
        screening_df = await screening_service.screen_batch(
            screening_texts, 
            session_id
        )
        relevant_df = (
            papers_df
            .merge(
                screening_df,
                left_on='id',
                right_on='id',
                how='left'
            )
            .assign(
                is_relevant=lambda x: x['is_relevant'].fillna(False),
                relevance_reason=lambda x: x['relevance_reason'].fillna('Not screened'),
                confidence=lambda x: x['confidence'].fillna(0.0)
            )
            .query("is_relevant == True")
        )

    papers_list = relevant_df.to_dict('records')

    return SimpleSearchResult(
        papers=papers_list,
        total_found=len(papers_df),
        total_screened=len(screening_df),
        total_relevant=len(relevant_df)
    )
    
    
@router.post("/api/summary")
async def get_summary(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    data = await request.json()
    papers = data.get("papers", [])
    extraction_fields = data.get("extraction_fields", [])
    # You can use config or env for model params
    summary_service = SummaryService(model_name="gpt-4o", temperature=0.2, max_tokens=1024)
    summary = summary_service.summarize(papers, extraction_fields)
    return JSONResponse(content={"summary": summary})