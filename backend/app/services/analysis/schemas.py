from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


class UnifiedReference(BaseModel):
    doc_id: str
    source: str  # "openalex" | "overton" ("web" for future)
    source_id: str
    title: str
    abstract_or_summary: str | None = None
    year: int | None = None
    doi: str | None = None
    authors: List[str] | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    is_oa: bool | None = None
    type: str | None = None
    author_institution_countries: List[str] | None = None
    cited_by_count: Optional[int] = None  # Number of citations
    source_country: Optional[
        str
    ] = (
        None
    )  # Country of the source/institution (converted from codes to names for OpenAlex)
    # Relevance fields
    is_relevant: Optional[bool] = None
    relevance_confidence: Optional[float] = None
    relevance_reason: Optional[str] = None
    top_line: Optional[str] = None  # Concise summary of main takeaway
    # TODO: Remove document_type fields once old projects no longer need them
    # Kept for backward compatibility with existing Supabase data
    document_type: Optional[str] = None
    document_type_reason: Optional[str] = None
    # Evidence categorisation (replaces document_type)
    evidence_category: Optional[str] = None
    evidence_confidence: Optional[float] = None
    evidence_category_reasoning: Optional[str] = None
    # Acquisition fields
    acquisition_status: Optional[str] = None  # "success" | "failed" | "not_attempted"
    acquisition_error: Optional[str] = None  # Error message if acquisition failed
    full_text_available: Optional[
        bool
    ] = None  # Whether full text was successfully acquired
    file_path: Optional[str] = None  # Path to downloaded file (if successful)
    # Extraction fields
    extraction_status: Optional[str] = None  # "success" | "failed" | "skipped"
    extraction_error: Optional[str] = None  # Error message if extraction failed
    text_source: Optional[
        str
    ] = None  # "full_text" | "abstract" - what was used for extraction


class SearchContext(BaseModel):
    """Flat search context payload sent by the search wizard."""

    research_question: str
    population: List[str] = Field(default_factory=list)
    outcome: List[str] = Field(default_factory=list)
    screening_factors: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    geography: List[str] = Field(default_factory=list)
    time_preset: Optional[str] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    max_results: Optional[int] = None
    additional_questions: List[str] = Field(default_factory=list)


# Search wizard API request/response schemas
class PopulationOptionsRequest(BaseModel):
    research_question: str
    max_options: int = 3


class PopulationOptionsResponse(BaseModel):
    research_question: str
    population_options: List[str]  # Ordered from broad to narrow


class OutcomeOptionsRequest(BaseModel):
    research_question: str
    max_options: int = 3


class OutcomeOptionsResponse(BaseModel):
    research_question: str
    outcome_options: List[str]  # Ordered from broad to narrow


class AdditionalQuestionsRequest(BaseModel):
    research_question: str
    population_selected: List[str] = []
    outcome_selected: List[str] = []
    max_questions: int = 2


class AdditionalQuestionsResponse(BaseModel):
    research_question: str
    additional_questions: List[str]


class RunConfig(BaseModel):
    query: str
    sources: List[str] = Field(default_factory=lambda: ["openalex", "overton"])
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 200
    screening_enabled: bool = False
    relevance_enabled: bool = True  # Filter documents by relevance before acquisition
    retrieval_mode: str = "semantic"  # "semantic" | "boolean"
    boolean_query: Optional[str] = None
    use_abstracts_only: bool = False
    # Chat interface specific parameters
    geography_filter: Optional[List[str]] = None  # Countries/regions to filter by
    sub_questions: Optional[
        List[str]
    ] = None  # Additional questions to include in screening (deprecated - step skipped)
    use_interim_storage: bool = True
    # New search wizard context
    search_context: Optional[SearchContext] = None


class RunResult(BaseModel):
    run_id: str
    total_references: int
    relevant_references: Optional[
        int
    ] = None  # Number of documents deemed relevant after filtering
    references_csv_path: str  # Single consolidated references CSV with all data
    extractions_json_path: Optional[
        str
    ] = None  # Single consolidated extractions JSON file
    boolean_queries: Optional[
        List[str]
    ] = None  # Generated boolean queries used for search (list for multi-query support)
    semantic_query: Optional[str] = None  # Generated semantic query used for Overton
