"""
MCP tool implementations.

Each tool is a thin facade over services in app/services/. The MCP layer
owns transport, schema, and tracing; business logic lives elsewhere.

Tools register against the FastMCP instance from app.mcp.server at import
time via @mcp.tool() decorators.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import tempfile
from pathlib import Path

import pandas as pd
from mcp.server.fastmcp import Context
from mcp.types import CallToolResult, TextContent

from app.mcp.schemas import (
    CompactPaper,
    EvidenceResult,
    PicoOption,
    ResultSummary,
    SearchEvidenceOutput,
    SuggestPicoOptionsOutput,
)
from app.mcp.server import mcp
from app.services.analysis.references import ReferencesService
from app.services.search_wizard import SearchWizardService

logger = logging.getLogger(__name__)

# MCP Apps widget URIs — each tool is independently invocable; widgets render
# whenever a host supports MCP Apps and ignores the _meta.ui.resourceUri annotation
# otherwise. The picker hands off to search_evidence via app.sendMessage rather
# than calling it directly, so each widget renders in response to its own
# LLM-initiated tool call.
PICO_PICKER_URI = "ui://policy-atlas/pico-picker"
SEARCH_EVIDENCE_URI = "ui://policy-atlas/search-evidence"

# Built artifacts from widgets/. Build with `npm run build` in that directory;
# vite-plugin-singlefile inlines all JS/CSS so the iframe sandbox can load them.
_WIDGETS_DIST = Path(__file__).parent / "widgets" / "dist"
_PICO_PICKER_HTML = _WIDGETS_DIST / "pico-picker.html"
_SEARCH_EVIDENCE_HTML = _WIDGETS_DIST / "search-evidence.html"


def _read_widget(path: Path) -> str:
    """Read a built widget file, raising a build-step hint if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Widget {path.name} not built. Run `npm install && npm run build` "
            f"in {path.parent.parent} to generate it."
        ) from exc


@mcp.resource(
    PICO_PICKER_URI,
    name="pico_picker",
    description="Interactive picker for population, outcome, and inner-setting facets.",
    mime_type="text/html;profile=mcp-app",
)
def pico_picker_widget() -> str:
    """Serve the built PICO picker widget HTML.

    Read lazily so a `npm run build` during dev is picked up without a Python
    server restart.
    """
    return _read_widget(_PICO_PICKER_HTML)


@mcp.resource(
    SEARCH_EVIDENCE_URI,
    name="search_evidence_results",
    description="Renders top-N evidence results from search_evidence as a list.",
    mime_type="text/html;profile=mcp-app",
)
def search_evidence_widget() -> str:
    """Serve the built search-evidence results widget HTML."""
    return _read_widget(_SEARCH_EVIDENCE_HTML)


def _labels_to_options(labels: list[str]) -> list[PicoOption]:
    """Convert plain-string labels into PicoOption objects.

    Descriptions stay empty in this spike: the existing wizard prompts return
    labels only. Upgrading the prompts to emit {label, description} pairs is
    a follow-up improvement; the schema already accepts the richer shape.
    """
    return [PicoOption(label=label, description="") for label in labels if label]


@mcp.tool(meta={"ui": {"resourceUri": PICO_PICKER_URI}})
async def suggest_pico_options(
    question: str,
    ctx: Context | None = None,
) -> SuggestPicoOptionsOutput:
    """Suggest PICO option sets for a policy research question.

    WHEN TO CALL:
    Call this FIRST when scoping an unfamiliar research question, before
    search_evidence. Skip if the user has already given explicit framings
    (e.g., they typed "search for X with population=Y, outcome=Z").

    WHAT IT RETURNS:
    3–5 options per PICO facet (population, outcome, inner_setting), ordered
    broad → narrow. The picker widget renders these for the user to select
    from; the user may also add their own free-text option per facet.
    Geography is supplied directly to search_evidence rather than suggested
    here. Facets are independent — outcome suggestions are not conditioned
    on which population was picked.

    PRESENTATION:
    After the tool returns, the widget renders the options. Do not narrate
    them as a markdown list — the widget already shows them.

    You MAY add a brief (1–2 sentence) critique IF you notice something
    genuinely useful — for example:
      - Two or more options collapse to essentially the same framing
      - A clearly-relevant dimension is missing (e.g., a question about
        homelessness with no "rough sleepers" or "single-adult vs family"
        option)
      - The question's terms are ambiguous and may have produced shallow
        options
    Keep critique terse. One sentence. No enumeration of the options
    themselves. If options look clean, just say so briefly ("framings
    look reasonable; pick from the widget above").

    POST-CALL:
    Wait for the user's picks. The picker hands off via app.sendMessage
    with a structured message; the user explicitly confirms by pressing
    send. Only then proceed to search_evidence with their picks.

    DO NOT:
    - Autonomously make picks for the user
    - Re-call this tool to "refine" picks — users refine via the picker's
      custom-input field, not by re-generating options
    - Proceed to search_evidence speculatively before the user confirms
    - Critique at length; the picker IS the surface for selection, your
      critique is just a brief steer
    """
    wizard = SearchWizardService()
    if ctx:
        await ctx.info(
            "Generating population, outcome, and inner-setting options in parallel…"
        )

    population, outcome, inner_setting = await asyncio.gather(
        wizard.generate_population_options(question),
        wizard.generate_outcome_options(question),
        wizard.generate_inner_setting_options(question),
        return_exceptions=True,
    )

    if ctx:
        counts = (
            (len(population) if isinstance(population, list) else 0),
            (len(outcome) if isinstance(outcome, list) else 0),
            (len(inner_setting) if isinstance(inner_setting, list) else 0),
        )
        await ctx.info(
            f"Got {counts[0]} population, {counts[1]} outcome, {counts[2]} setting options."
        )

    def _safe(result: object, fallback_msg: str) -> list[str]:
        if isinstance(result, BaseException):
            logger.warning("%s: %s", fallback_msg, result)
            return []
        return result if isinstance(result, list) else []

    output = SuggestPicoOptionsOutput(
        research_question=question,
        population_options=_labels_to_options(
            _safe(population, "Population options failed")
        ),
        outcome_options=_labels_to_options(_safe(outcome, "Outcome options failed")),
        inner_setting_options=_labels_to_options(
            _safe(inner_setting, "Inner setting options failed")
        ),
    )

    # Hosts that render the widget show interactive checkboxes; hosts that don't
    # see only the terse text below. The full data lives in structuredContent —
    # the widget consumes that via ontoolresult. Keeping `content` to a count
    # stops the model narrating every option as a markdown list under the iframe.
    summary = (
        f"PICO framings ready: {len(output.population_options)} population, "
        f"{len(output.outcome_options)} outcome, "
        f"{len(output.inner_setting_options)} inner-setting options. "
        f"Rendered as an interactive picker."
    )
    return CallToolResult(
        content=[TextContent(type="text", text=summary)],
        structuredContent=output.model_dump(mode="json", by_alias=True),
    )


# ---------------------------------------------------------------------------
# search_evidence
# ---------------------------------------------------------------------------


def _parse_authors(raw: object) -> list[str]:
    """Authors round-trip through CSV as a string repr of a list.

    Best-effort parse: try literal_eval first, fall back to a single-element
    list, never raise.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, list):
        return [str(a) for a in raw if a]
    try:
        parsed = ast.literal_eval(str(raw))
        if isinstance(parsed, list):
            return [str(a).strip() for a in parsed if a]
    except (ValueError, SyntaxError):
        pass
    return [str(raw)]


def _row_to_evidence(row: pd.Series) -> EvidenceResult:
    """Map one references.csv row to the EvidenceResult schema.

    Defensive about column names — different sources (OpenAlex, Overton)
    expose different fields, so we coalesce across plausible names and
    fall back to None.
    """

    def _g(*cols: str):
        for col in cols:
            if col in row.index:
                val = row[col]
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                return val
        return None

    abstract = _g("abstract", "content", "abstract_snippet", "abstract_or_summary")
    if isinstance(abstract, str) and len(abstract) > 500:
        abstract = abstract[:500].rstrip() + "…"

    cited = _g("cited_by_count")
    year = _g("publication_year", "year")
    rel = _g("relevance_score")
    vpri = _g("variant_priority")

    return EvidenceResult(
        doc_id=str(_g("doc_id", "id") or ""),
        title=str(_g("title") or "No title available"),
        year=int(year) if year is not None and not pd.isna(year) else None,
        source=str(_g("source") or "") or None,
        document_type=str(_g("work_type", "type", "document_type") or "") or None,
        authors=_parse_authors(_g("authors")),
        venue=str(_g("venue") or "") or None,
        cited_by_count=int(cited) if cited is not None else None,
        abstract_snippet=str(abstract) if abstract else None,
        is_open_access=bool(_g("is_oa", "is_open_access"))
        if _g("is_oa", "is_open_access") is not None
        else None,
        landing_page_url=str(_g("landing_page_url", "url") or "") or None,
        relevance_score=float(rel) if rel is not None and not pd.isna(rel) else None,
        query_variant=str(_g("query_variant") or "") or None,
        variant_priority=int(vpri) if vpri is not None and not pd.isna(vpri) else None,
    )


# Longer cap than EvidenceResult's 500 chars — the widget never renders these, so
# we keep up to the full ~1800-char abstract for the LLM's gap-analysis reflection.
# See docs/spec_search_evidence_agentic.md §4.
_COMPACT_ABSTRACT_MAX_CHARS = 1800


def _row_to_compact_paper(row: pd.Series, rank: int) -> CompactPaper:
    """Map one references.csv row to the CompactPaper schema.

    Used for `additional_results` — papers in the wider fetched set beyond the
    top-N. Carries the full abstract (truncated only at ~1800 chars) so the
    LLM has enough semantic signal to identify what's missing in the top-N.
    """

    def _g(*cols: str):
        for col in cols:
            if col in row.index:
                val = row[col]
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                return val
        return None

    abstract = _g("abstract", "content", "abstract_snippet", "abstract_or_summary")
    if isinstance(abstract, str) and len(abstract) > _COMPACT_ABSTRACT_MAX_CHARS:
        abstract = abstract[:_COMPACT_ABSTRACT_MAX_CHARS].rstrip() + "…"

    year = _g("publication_year", "year")
    rel = _g("relevance_score")
    vpri = _g("variant_priority")

    return CompactPaper(
        doc_id=str(_g("doc_id", "id") or ""),
        rank=rank,
        title=str(_g("title") or "No title available"),
        abstract_snippet=str(abstract) if abstract else None,
        year=int(year) if year is not None and not pd.isna(year) else None,
        source_country=str(_g("source_country") or "") or None,
        venue=str(_g("venue") or "") or None,
        document_type=str(_g("work_type", "type", "document_type") or "") or None,
        source=str(_g("source") or "") or None,
        relevance_score=float(rel) if rel is not None and not pd.isna(rel) else None,
        query_variant=str(_g("query_variant") or "") or None,
        variant_priority=int(vpri) if vpri is not None and not pd.isna(vpri) else None,
    )


# Country-name normalisation map. OpenAlex's source_country is produced upstream
# by `convert_country_codes_to_names` (full names like "United States"); Overton
# uses raw labels (often "USA", "UK", or ISO codes). Without normalisation, the
# same country surfaces as two entries in the summary strip — seen in the wild as
# "24% USA · 20% United States · …". Hybrid policy: deterministic dict for
# known-recurring cross-source mismatches; the LLM's gap-analysis reflection
# (post-call, per spec §12) catches anything novel. See spec §8.
_COUNTRY_ALIAS: dict[str, str] = {
    # United States
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    # United Kingdom
    "uk": "UK",
    "gb": "UK",
    "great britain": "UK",
    "britain": "UK",
    "united kingdom": "UK",
    "united kingdom of great britain and northern ireland": "UK",
    "england": "UK",
    "scotland": "UK",
    "wales": "UK",
    "northern ireland": "UK",
    # Frequently-occurring others worth canonicalising
    "canada": "Canada",
    "ca": "Canada",
    "australia": "Australia",
    "au": "Australia",
    "new zealand": "New Zealand",
    "nz": "New Zealand",
    "ireland": "Ireland",
    "ie": "Ireland",
    "germany": "Germany",
    "de": "Germany",
    "france": "France",
    "fr": "France",
    "netherlands": "Netherlands",
    "nl": "Netherlands",
    "the netherlands": "Netherlands",
    "spain": "Spain",
    "es": "Spain",
    "italy": "Italy",
    "it": "Italy",
    "sweden": "Sweden",
    "se": "Sweden",
    "norway": "Norway",
    "no": "Norway",
    "denmark": "Denmark",
    "dk": "Denmark",
    "finland": "Finland",
    "fi": "Finland",
}


def _normalise_country(raw: str) -> str:
    """Best-effort country-name normalisation. Falls back to the raw value
    title-cased if no alias matches — preserves unfamiliar labels rather than
    collapsing them into 'Unknown'.
    """
    key = raw.strip().lower()
    if not key:
        return ""
    if key in _COUNTRY_ALIAS:
        return _COUNTRY_ALIAS[key]
    return raw.strip().title()


def _compute_result_summary(df: pd.DataFrame) -> ResultSummary:
    """Compute aggregate distributions over the full fetched DataFrame.

    Runs deterministic pandas operations — no LLM cost, ~10ms server-side.
    The output drives both the widget's summary strip and the LLM's
    gap-analysis reflection. See docs/spec_search_evidence_agentic.md §8.
    """
    if df.empty:
        return ResultSummary()

    # Country distribution — normalise across sources before counting so that
    # OpenAlex's "United States" and Overton's "USA" don't surface as separate
    # entries. Fall back gracefully when source_country is missing.
    countries: dict[str, int] = {}
    if "source_country" in df.columns:
        counts = df["source_country"].dropna().astype(str).str.strip()
        counts = counts[counts != ""]
        normalised = counts.apply(_normalise_country)
        normalised = normalised[normalised != ""]
        countries = normalised.value_counts().to_dict()

    # Year range + median across rows that have a year.
    year_col = "publication_year" if "publication_year" in df.columns else "year"
    year_range: tuple[int, int] | None = None
    year_median: int | None = None
    if year_col in df.columns:
        years = pd.to_numeric(df[year_col], errors="coerce").dropna().astype(int)
        if not years.empty:
            year_range = (int(years.min()), int(years.max()))
            year_median = int(years.median())

    # Source mix (openalex vs overton vs …).
    source_mix: dict[str, int] = {}
    if "source" in df.columns:
        source_mix = df["source"].dropna().astype(str).value_counts().to_dict()

    # Document-type mix — coalesce across plausible column names.
    doctype_mix: dict[str, int] = {}
    for col in ("work_type", "type", "document_type"):
        if col in df.columns:
            doctype_mix = df[col].dropna().astype(str).value_counts().to_dict()
            break

    # Open-access fraction over rows that report it (excluding nulls).
    oa_fraction: float | None = None
    for col in ("is_oa", "is_open_access"):
        if col in df.columns:
            oa = df[col].dropna()
            if not oa.empty:
                oa_fraction = float(oa.astype(bool).mean())
            break

    return ResultSummary(
        country_distribution=countries,
        year_range=year_range,
        year_median=year_median,
        source_mix=source_mix,
        document_type_mix=doctype_mix,
        open_access_fraction=oa_fraction,
    )


@mcp.tool(meta={"ui": {"resourceUri": SEARCH_EVIDENCE_URI}})
async def search_evidence(
    research_question: str,
    population: list[str] | None = None,
    outcome: list[str] | None = None,
    inner_setting: list[str] | None = None,
    geography: list[str] | None = None,
    sources: list[str] | None = None,
    max_results: int = 5,
    total_limit: int = 50,
    ctx: Context | None = None,
) -> SearchEvidenceOutput:
    """Search OpenAlex (academic papers) and Overton (policy documents) for evidence.

    WHEN TO CALL:
    Call after the user has confirmed PICO picks (via the picker widget).
    May also be called standalone if the user gives explicit search terms
    without going through the picker. Defaults: both sources, max_results=5,
    total_limit=50.

    WHAT IT RETURNS:
    Three layers in structuredContent:
      - results: top-N papers (rendered by the search-evidence widget).
      - additional_results: ~45 more papers as CompactPaper — full abstracts
        included — NOT rendered by the widget; for YOUR reasoning over the
        wider evidence base.
      - result_summary: aggregate distributions (country, year range/median,
        source mix, document_type mix, OA fraction) over the FULL fetched
        set — rendered as a summary strip above the result cards, also
        available to you for reflection.
    Each paper also carries: relevance_score (from source API), query_variant
    (which boolean query matched), variant_priority, source.

    PRESENTATION:
    The widget renders top-5 + summary strip. Do not re-narrate either.
    A single brief acknowledgement is enough ("Results above; ~30s search").

    POST-CALL REFLECTION — REQUIRED:
    Silently perform a research gap analysis against the user's question.
    Ground it in actual data using result_summary + additional_results — do
    not speculate beyond what the results show.

    Identify dimensions where the evidence base is THIN or MISSING relative
    to what would fully answer the user's question:
      - Study designs (e.g., effectiveness question but no RCTs/quasi-
        experimental work in the set)
      - Populations or subgroups the question implies but results don't
        cover
      - Intervention types or delivery contexts conspicuously absent
      - Time periods (e.g., all pre-2015 when the question is current)
      - Outcomes measured (e.g., question asks about long-term effects;
        results only report short-term)
      - Geographies, as ONE dimension among many — not the primary lens
      - Source-mix asymmetry as a known limitation: Overton policy docs
        are systematically deprioritised in the merged ranking because
        their per-doc similarity score isn't extracted upstream. If the
        question is policy-relevant and few Overton docs surfaced, this
        may reflect that bias rather than a true literature gap.

    Then propose ONE corrective action in chat, grounded in the gap analysis:
      - For gaps adjusted search args would address → propose re-calling
        search_evidence with the relevant change ("no RCTs in the top-50 —
        want me to retry with stricter study-design filtering?")
      - For gaps the wider set partly addresses → name the specific buried
        papers ("Aubry 2020 at rank 12 covers the UK setting your question
        implied — want to look at it?")
      - For genuine evidence gaps (literature doesn't exist in the indexed
        set) → note honestly ("no RCTs on this question appear; only
        observational evidence available — the synthesis stage can still
        proceed but flag the limitation")

    Wait for explicit user confirmation before any corrective re-call.
    Surface gaps even if no corrective action is possible — the user
    benefits from knowing what's NOT in the evidence base.

    DO NOT:
    - Narrate the JSON; the widget renders it
    - Auto-retry without user confirmation
    - Treat the per-paper relevance_score as semantic relevance — it's a
      raw BM25-ish score from OpenAlex, not an explained judgement
    - Propose drilling into a paper's full text — that belongs to the next
      workflow stage (run_analysis), not search
    - Use geography as the primary lens of critique; treat it as one
      dimension in the broader gap analysis
    """
    sources_list = sources or ["openalex", "overton"]

    # PICO picks feed the boolean query generator via search_context
    search_context = {
        "research_question": research_question,
        "population": population or [],
        "outcome": outcome or [],
        "geography": geography or [],
    }

    if ctx:
        await ctx.info(
            f"Searching {', '.join(sources_list)} for: {research_question[:70]}…"
        )

    with tempfile.TemporaryDirectory(prefix="mcp_search_") as tmp:
        service = ReferencesService(export_dir=tmp)
        csv_path, boolean_queries, _semantic = await service.build_references(
            query=research_question,
            sources=sources_list,
            limit=total_limit,
            geography_filter=geography,
            search_context=search_context,
        )
        df = pd.read_csv(csv_path)

    total_found = len(df)
    if ctx:
        await ctx.info(
            f"Found {total_found} papers across {len(boolean_queries)} queries; "
            f"returning top {min(max_results, total_found)}."
        )

    # Three layers (see docs/spec_search_evidence_agentic.md §4, §6, §8):
    #   results            — top-N rendered by the widget
    #   additional_results — wider compact set (full abstracts) for LLM gap analysis
    #   result_summary     — aggregate stats over the FULL fetched DataFrame
    top_rows = df.head(max_results)
    results = [_row_to_evidence(row) for _, row in top_rows.iterrows()]
    additional_results = [
        _row_to_compact_paper(row, rank=max_results + i + 1)
        for i, (_, row) in enumerate(df.iloc[max_results:].iterrows())
    ]
    result_summary = _compute_result_summary(df)

    output = SearchEvidenceOutput(
        total_found=total_found,
        results_returned=len(results),
        results=results,
        additional_results=additional_results,
        result_summary=result_summary,
        boolean_queries_used=boolean_queries,
    )

    # Mirrors the pattern used by suggest_pico_options: terse text so hosts
    # that don't render the widget still get a useful summary, full data in
    # structuredContent for the widget to render the results list.
    summary = (
        f"Found {total_found} papers across {len(boolean_queries)} queries; "
        f"showing top {len(results)}. Wider {len(additional_results)} available for "
        f"reflection. Rendered as an interactive list."
    )
    return CallToolResult(
        content=[TextContent(type="text", text=summary)],
        structuredContent=output.model_dump(mode="json", by_alias=True),
    )
