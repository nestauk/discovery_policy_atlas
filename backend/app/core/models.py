from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import date, datetime
from app.core.config import settings


# Base search request with common parameters
class BaseSearchRequest(BaseModel):
    query: str
    max_results: int = Field(
        default=settings.DEFAULT_MAX_RESULTS, ge=1, le=settings.MAX_SEARCH_RESULTS
    )
    inclusion_criteria: Optional[str] = None
    extraction_fields: Optional[List[str]] = None
    screening_enabled: Optional[bool] = True


class OpenAlexSearchRequest(BaseSearchRequest):
    source: Literal["openalex"] = "openalex"
    min_citations: Optional[int] = Field(default=None, ge=0)
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class MediaCloudSearchRequest(BaseSearchRequest):
    source: Literal["mediacloud"] = "mediacloud"
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class OvertonSearchRequest(BaseSearchRequest):
    source: Literal["overton"] = "overton"
    source_country: Optional[str] = None
    source_type: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    topics: Optional[str] = None
    classifications: Optional[str] = None
    semantic_search: Optional[bool] = True


# Unified search request
SearchRequest = OpenAlexSearchRequest | MediaCloudSearchRequest | OvertonSearchRequest


# Result models
class ScreeningResult(BaseModel):
    id: str
    is_relevant: bool
    relevance_reason: Optional[str] = None
    confidence: Optional[float] = None


class ExtractedData(BaseModel):
    id: str
    title: str
    key_findings: List[str]
    methodology: Optional[str] = None
    policy_implications: Optional[List[str]] = None
    custom_fields: Dict[str, Any] = {}


class SummaryResult(BaseModel):
    summary: str
    key_themes: List[str]
    policy_recommendations: List[str]
    evidence_gaps: List[str]
    source_count: int


class SimpleSearchResult(BaseModel):
    papers: List[Dict[str, Any]]
    total_found: int
    total_screened: int
    total_relevant: int


class SearchResultWithDownload(BaseModel):
    papers: List[Dict[str, Any]]
    total_found: int
    total_screened: int
    total_relevant: int
    download_key: Optional[str] = None


class DownloadCacheEntry(BaseModel):
    df_data: Dict[str, Any]  # Serialized DataFrame data
    query: str
    user_id: str
    created_at: datetime
    expires_at: datetime


# class SearchResult(BaseModel):
#     raw_results: List[Dict[str, Any]]
#     screened_results: List[ScreeningResult]
#     extracted_data: List[ExtractedData]
#     synthesis: Optional[SynthesisResult] = None
#     total_found: int
#     total_screened: int
#     total_relevant: int
