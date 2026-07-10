"""
Pydantic schemas for Policy Atlas MCP tools.

These models are the public contract the MCP server exposes to calling agents.
FastMCP serialises them to JSON Schema and embeds the `description=` strings
in the tool manifest — so every description is written for an agent reader,
not a human maintainer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PicoOption(BaseModel):
    """A single suggested option for a PICO facet (population, outcome, setting, geography)."""

    label: str = Field(
        ...,
        description="Short label suitable for a pick-list, e.g. 'Children with EHCPs specifically'.",
    )
    description: str = Field(
        "",
        description="One-sentence clarification distinguishing this option from neighbours.",
    )


class SuggestPicoOptionsOutput(BaseModel):
    """LLM-suggested PICO option sets for a research question.

    Each option list is ordered broad → narrow. The caller (typically an agent
    or a UI) picks one or more options per facet to assemble a structured
    search. Options are independent across facets in this version (i.e. outcome
    suggestions are not conditioned on which population was chosen).
    """

    research_question: str = Field(
        ...,
        description="The original question, echoed back so the output is self-contained.",
    )
    population_options: list[PicoOption] = Field(
        default_factory=list,
        description="Suggested ways to scope the population this research applies to.",
    )
    outcome_options: list[PicoOption] = Field(
        default_factory=list,
        description="Suggested outcomes the research could measure progress against.",
    )
    inner_setting_options: list[PicoOption] = Field(
        default_factory=list,
        description="Suggested implementation settings where the intervention would be delivered.",
    )
    # Geography intentionally omitted in the spike — the caller supplies it
    # directly to search_evidence. Re-add as a facet if/when worth the prompt.


class EvidenceResult(BaseModel):
    """A single paper returned by search_evidence.

    Fields are mostly optional — different sources (OpenAlex, Overton) return
    different field sets, and the schema absorbs that variation rather than
    dropping papers with sparse metadata.
    """

    doc_id: str = Field(
        ..., description="Stable cross-source identifier, e.g. 'openalex:W12345'."
    )
    title: str = Field(..., description="Paper title.")
    year: int | None = Field(None, description="Year of publication if known.")
    source: str | None = Field(
        None, description="Origin database: 'openalex' or 'overton'."
    )
    document_type: str | None = Field(
        None,
        description="Type label from the source (e.g. 'journal-article', 'report').",
    )
    authors: list[str] = Field(
        default_factory=list, description="Author names as plain strings."
    )
    venue: str | None = Field(None, description="Journal, publisher, or hosting org.")
    cited_by_count: int | None = Field(
        None, description="Citation count from the source, when available."
    )
    abstract_snippet: str | None = Field(
        None, description="Abstract or summary excerpt (truncated to ~500 chars)."
    )
    is_open_access: bool | None = Field(
        None, description="Whether the paper is open access (when known)."
    )
    landing_page_url: str | None = Field(
        None, description="URL where the agent or a human can read the paper."
    )
    # Existing pipeline signals plumbed through for LLM ranking-bias reasoning.
    # See docs/spec_search_evidence_agentic.md §6.
    relevance_score: float | None = Field(
        None,
        description=(
            "Source-database relevance score (BM25-ish from OpenAlex). NB: Overton "
            "documents typically have 0 here because their per-doc similarity score "
            "isn't extracted upstream — see references.py and the asymmetry note in §7."
        ),
    )
    query_variant: str | None = Field(
        None,
        description="Label of the boolean-query variant that retrieved this paper, e.g. 'broad', 'uk-stratified'.",
    )
    variant_priority: int | None = Field(
        None,
        description="Priority the search strategy assigned to the matching query variant (lower = primary).",
    )


class CompactPaper(BaseModel):
    """Trimmed paper representation for LLM reasoning over the wider result set.

    The widget never renders these; they're for the agent's gap-analysis
    reflection over the broader retrieval (papers ranked beyond the top-N).
    Carries the full abstract (up to ~1800 chars) so the LLM has enough
    semantic signal to identify study designs, populations, outcomes,
    time horizons, and intervention types missing from the top-N. See
    docs/spec_search_evidence_agentic.md §4.
    """

    doc_id: str = Field(..., description="Stable cross-source identifier.")
    rank: int = Field(
        ...,
        description="1-indexed position in the full sorted result set (1 = top of wider 50).",
    )
    title: str = Field(..., description="Paper title.")
    abstract_snippet: str | None = Field(
        None,
        description="Full abstract truncated to ~1800 chars when longer; max signal for gap analysis.",
    )
    year: int | None = Field(None, description="Year of publication.")
    source_country: str | None = Field(
        None, description="Country of origin / publication."
    )
    venue: str | None = Field(None, description="Journal, publisher, or hosting org.")
    document_type: str | None = Field(
        None,
        description="Type label from the source (e.g. 'journal-article', 'report').",
    )
    source: str | None = Field(None, description="'openalex' or 'overton'.")
    relevance_score: float | None = Field(
        None, description="Source-database relevance score (see §7 asymmetry caveat)."
    )
    query_variant: str | None = Field(
        None, description="Boolean-query variant that retrieved this paper."
    )
    variant_priority: int | None = Field(
        None, description="Priority of the matching query variant (lower = primary)."
    )


class ResultSummary(BaseModel):
    """Aggregate distributions computed over the FULL fetched result set (not just top-N).

    Rendered as a single summary strip above the widget's results list, and
    consumed by the LLM for gap-analysis reflection. Same data, two audiences.
    See docs/spec_search_evidence_agentic.md §8.
    """

    country_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of papers per source_country, e.g. {'US': 30, 'UK': 5, 'AU': 8}.",
    )
    year_range: tuple[int, int] | None = Field(
        None,
        description="(min_year, max_year) across the result set; None if no year data.",
    )
    year_median: int | None = Field(
        None, description="Median publication year across the result set."
    )
    source_mix: dict[str, int] = Field(
        default_factory=dict,
        description="Count of papers per source database, e.g. {'openalex': 42, 'overton': 8}.",
    )
    document_type_mix: dict[str, int] = Field(
        default_factory=dict,
        description="Count of papers per document_type, e.g. {'journal-article': 35, 'report': 10}.",
    )
    open_access_fraction: float | None = Field(
        None,
        description="Fraction (0-1) of papers known to be open access; None if is_oa data is missing for all.",
    )


class SearchEvidenceOutput(BaseModel):
    """Result of a single search across OpenAlex and/or Overton.

    Returns three layers:
      - `results`: top-N papers (capped by max_results), full EvidenceResult shape — rendered by the widget.
      - `additional_results`: the wider set (papers ranked N+1 onwards) as CompactPaper — NOT rendered by the widget; for LLM gap-analysis reflection.
      - `result_summary`: aggregate stats over the FULL fetched DataFrame — rendered by the widget as a summary strip, also consumed by the LLM.

    The agentic flow expects the LLM to reflect on `result_summary` + `additional_results` after results return — see docs/spec_search_evidence_agentic.md §4, §8, §12.
    """

    total_found: int = Field(
        ..., description="Total number of papers matched across all sources."
    )
    results_returned: int = Field(
        ...,
        description="Number of papers included in `results` (capped by max_results).",
    )
    results: list[EvidenceResult] = Field(
        default_factory=list,
        description="Top results ordered by source-defined relevance.",
    )
    additional_results: list[CompactPaper] = Field(
        default_factory=list,
        description=(
            "Wider compact set (papers ranked beyond the top-N). Full abstract included "
            "for gap-analysis reflection. The widget ignores this field."
        ),
    )
    result_summary: ResultSummary | None = Field(
        None,
        description="Aggregate distributions over the full fetched set for triage + reflection.",
    )
    boolean_queries_used: list[str] = Field(
        default_factory=list,
        description="The actual queries sent to OpenAlex — surfaced for auditability.",
    )
