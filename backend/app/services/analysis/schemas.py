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
    document_type: Optional[
        str
    ] = None  # "research_paper" | "reviews" | "policy_document" | "other"
    document_type_reason: Optional[str] = None
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
    access_types: Optional[List[str]] = None  # ["academic", "thinkTank", "government"]
    sub_questions: Optional[
        List[str]
    ] = None  # Additional questions to include in screening
    use_interim_storage: bool = True


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
