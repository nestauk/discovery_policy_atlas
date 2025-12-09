"""
Synthesis agent for policy atlas.

Uses LangGraph to orchestrate theme discovery, RAG retrieval, and briefing generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from typing import List, Dict, TypedDict, Optional, Any, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from app.services.vectorization import vectorization_service
from app.utils.llm.llm_utils import (
    get_llm,
    get_langfuse_handler,
    build_langfuse_metadata,
    resolve_langfuse_session_id,
)
from app.services.synthesis.schemas import (
    KeyIssue,
    PolicyIntervention,
    CitationInfo,
    EvidenceCoverageSnapshot,
    OutcomeTheme,
    RetrievedChunk,
    StructuredBriefing,
    CoreAnswer,
    EvidenceSnapshotRow,
    InterventionTableRow,
    OutcomeEffect,
    RecommendationItem,
    RecommendationsOutput,
    TopCitationItem,
    BackgroundSection,
)
from app.services.synthesis.prompts import (
    build_discover_themes_prompt,
    make_discover_themes_instructions,
    build_theme_critique_prompt,
    build_classify_concept_prompt,
    build_background_section_prompt,
    build_impact_narrative_prompt,
    build_recommendations_prompt,
    build_core_answer_prompt,
)

logger = logging.getLogger(__name__)

# Model selection
THEME_MODEL = "gpt-5-mini"
MAPPING_MODEL = "gpt-5-nano"
BRIEFING_MODEL = "gpt-5"

# Study type code mapping (Maryland Scientific Methods Scale - matches extraction prompts)
STUDY_TYPE_LABELS: Dict[str, str] = {
    "a": "Cross-Sectional",
    "b": "Pre-Post Study",
    "c": "Cross-Sectional with Controls",
    "d": "Pre-Post with Controls",
    "e": "Comparison Study",
    "f": "Quasi-Experimental",
    "g": "RCT",
    "h": "Meta-Analysis",
    "i": "Policy/Theoretical",
    "j": "Non-Scientific",
}

ThemeBranch = Literal["issue", "intervention", "outcome"]


def normalize_study_type(study_type: str) -> str:
    """Normalise study type codes to full readable names."""
    if not study_type:
        return ""
    st = study_type.strip().lower()
    if st in STUDY_TYPE_LABELS:
        return STUDY_TYPE_LABELS[st]
    for full_name in STUDY_TYPE_LABELS.values():
        if full_name.lower() == st:
            return full_name
    return study_type.strip().title()


def normalize_source_type(source: str, document_type: str) -> str:
    """Normalise document source to readable category."""
    src = (source or "").strip().lower()
    doc_type = (document_type or "").strip().lower()

    # OpenAlex is always academic
    if src == "openalex":
        return "Academic"

    # Overton document types
    if doc_type in ("journal article", "unknown", ""):
        return "Academic"
    if doc_type in ("government document", "government"):
        return "Government"
    if doc_type in ("ngo document", "ngo", "think tank"):
        return "NGO/Think Tank"
    if doc_type in ("policy document", "policy brief", "policy"):
        return "Policy"
    if doc_type in ("news", "news article", "media"):
        return "Media"

    # Return title-cased document_type if no match
    return document_type.title() if document_type else "Other"


def _escape_braces(text: str) -> str:
    """Escape braces for ChatPromptTemplate."""
    return (text or "").replace("{", "{{").replace("}", "}}")


class Concept(BaseModel):
    """A single enriched concept."""

    id: str
    canonical_description: str


class DiscoveredTheme(BaseModel):
    """Theme discovered by LLM."""

    theme_name: str
    theme_description: str


class FinalTheme(BaseModel):
    """Final theme with mapped concepts."""

    name: str
    description: str
    concepts: List[Concept] = Field(default_factory=list)
    frequency: int = 0


class SynthesisState(TypedDict):
    """State passed through the synthesis workflow."""

    project_id: str
    research_question: str
    raw_extractions: List[Dict]
    doc_metadata: Dict[str, Dict[str, Any]]

    # Concepts by branch
    issue_concepts: List[Concept]
    intervention_concepts: List[Concept]
    outcome_concepts: List[Concept]

    # Themes by branch
    discovered_issue_themes: List[DiscoveredTheme]
    discovered_intervention_themes: List[DiscoveredTheme]
    discovered_outcome_themes: List[DiscoveredTheme]
    final_issue_themes: List[FinalTheme]
    final_intervention_themes: List[FinalTheme]
    final_outcome_themes: List[FinalTheme]

    # Evidence coverage
    evidence_coverage: EvidenceCoverageSnapshot

    # Aggregated outputs
    aggregated_issues: List[KeyIssue]
    aggregated_interventions: List[PolicyIntervention]
    aggregated_outcomes: List[OutcomeTheme]
    extraction_quotes: Dict[str, List[str]]  # doc_uuid -> list of extraction quotes
    outcome_doc_effects: Dict[
        str, Dict[str, List[str]]
    ]  # outcome_name -> {doc_id -> [effects]}

    # RAG retrieval
    theme_evidence: Dict[str, List[RetrievedChunk]]
    issue_evidence: Dict[str, List[RetrievedChunk]]
    grounded_citations: List[CitationInfo]
    chunk_to_citation: Dict[str, int]

    # Final outputs
    executive_briefing: str
    structured_briefing: Optional[StructuredBriefing]
    citation_map: Dict[str, CitationInfo]

    # Langfuse tracing
    langfuse_handler: Any
    langfuse_session_id: str
    policy_user_id: Optional[str]


class ThemesOut(BaseModel):
    """Structured output for discovered themes."""

    themes: List[DiscoveredTheme]


def _langfuse_config(
    state: SynthesisState, tags: List[str], extra: Optional[Dict] = None
) -> Dict:
    """Build Langfuse config for LLM calls."""
    handler = state.get("langfuse_handler")
    return {
        "callbacks": [handler] if handler else [],
        "tags": tags,
        "metadata": build_langfuse_metadata(
            tags=tags,
            session_id=state.get("langfuse_session_id"),
            user_id=state.get("policy_user_id"),
            project_id=state.get("project_id"),
            extra=extra,
        ),
    }


# =============================================================================
# PHASE 1: LOAD DATA
# =============================================================================


async def load_raw_extractions(state: SynthesisState) -> SynthesisState:
    """Load extractions and document metadata."""
    print("--- Loading Extractions & Documents ---")
    project_id = state.get("project_id", "")
    if not project_id:
        return {
            "raw_extractions": [],
            "research_question": "Not specified",
            "doc_metadata": {},
        }

    supabase = vectorization_service.supabase

    # Fetch research question
    proj_res = (
        supabase.table("analysis_projects")
        .select("title, query")
        .eq("id", project_id)
        .execute()
    )
    research_question = (
        (proj_res.data[0].get("title") or proj_res.data[0].get("query"))
        if proj_res.data
        else "Not specified"
    )

    # Fetch document metadata
    docs_res = (
        supabase.table("analysis_documents")
        .select(
            "id, doc_id, title, year, authors, landing_page_url, pdf_url, source, document_type"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )

    doc_metadata: Dict[str, Dict] = {}
    for doc in docs_res.data or []:
        doc_uuid = str(doc.get("id"))
        authors = doc.get("authors") or []
        author_short = None
        if authors and isinstance(authors, list):
            parts = str(authors[0]).strip().split()
            if parts:
                author_short = parts[-1]
        doc_metadata[doc_uuid] = {
            "doc_id": doc.get("doc_id"),
            "title": doc.get("title") or "",
            "year": doc.get("year"),
            "author_short": author_short,
            "url": doc.get("landing_page_url") or doc.get("pdf_url"),
            "source": doc.get("source"),
            "document_type": doc.get("document_type"),
        }

    # Fetch extractions
    res = (
        supabase.table("analysis_extractions")
        .select(
            "id, analysis_document_id, extraction_type, label, description, raw_data"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )

    def to_uniform(row: Dict) -> Dict:
        et = str(row.get("extraction_type") or "")
        raw = row.get("raw_data") or {}
        if et == "intervention":
            raw_st = raw.get("study_type") or raw.get("type") or ""
            return {
                "id": str(row.get("id")),
                "type": "intervention",
                "intervention_name": str(row.get("label") or raw.get("name") or ""),
                "study_type": normalize_study_type(str(raw_st)),
                "country": str(raw.get("country") or ""),
                "description": str(
                    row.get("description") or raw.get("description") or ""
                ),
            }
        elif et == "issue":
            return {
                "id": str(row.get("id")),
                "type": "issue",
                "issue_label": str(row.get("label") or raw.get("label") or ""),
                "explanation": str(
                    raw.get("explanation") or row.get("description") or ""
                ),
            }
        elif et == "result":
            return {
                "id": str(row.get("id")),
                "type": "result",
                "outcome_variable": str(
                    raw.get("outcome_variable") or row.get("label") or ""
                ),
                "effect_direction": str(raw.get("effect_direction") or ""),
                "effect_size": str(raw.get("effect_size") or ""),
            }
        return {"id": str(row.get("id")), "type": et}

    uniform = [to_uniform(r) for r in (res.data or [])]
    print(f"Loaded {len(uniform)} extractions, {len(doc_metadata)} documents")
    return {
        "raw_extractions": uniform,
        "research_question": research_question,
        "doc_metadata": doc_metadata,
    }


async def create_canonical_concepts(state: SynthesisState) -> SynthesisState:
    """Create concept sets from extractions."""
    print("--- Creating Canonical Concepts ---")
    issue_concepts: List[Concept] = []
    intervention_concepts: List[Concept] = []
    outcome_concepts: List[Concept] = []

    for ext in state.get("raw_extractions") or []:
        if ext.get("issue_label"):
            desc = f"Issue: {ext['issue_label']}. Explanation: {ext.get('explanation', '')}"
            issue_concepts.append(Concept(id=ext["id"], canonical_description=desc))
        if ext.get("intervention_name"):
            desc = f"Intervention: {ext['intervention_name']}. Description: {ext.get('description', '')}"
            intervention_concepts.append(
                Concept(id=ext["id"], canonical_description=desc)
            )
        if ext.get("type") == "result" or ext.get("outcome_variable"):
            desc = f"Outcome: {ext.get('outcome_variable', '')}. Effect: {ext.get('effect_direction', '')}"
            outcome_concepts.append(Concept(id=ext["id"], canonical_description=desc))

    print(
        f"Created {len(issue_concepts)} issue, {len(intervention_concepts)} intervention, {len(outcome_concepts)} outcome concepts"
    )
    return {
        "issue_concepts": issue_concepts,
        "intervention_concepts": intervention_concepts,
        "outcome_concepts": outcome_concepts,
    }


# =============================================================================
# PHASE 2: THEME DISCOVERY (Consolidated)
# =============================================================================


async def _discover_themes(
    concepts: List[Concept],
    rq: str,
    state: SynthesisState,
    branch: ThemeBranch,
) -> List[DiscoveredTheme]:
    """Discover themes for a set of concepts (generic for all branches)."""
    if not concepts:
        return []

    tags = [
        "component:synthesis",
        "component:synthesis.discover_themes",
        f"branch:{branch}",
        f"model:{THEME_MODEL}",
    ]
    instructions = make_discover_themes_instructions(None)
    prompt = build_discover_themes_prompt()
    llm = get_llm(THEME_MODEL, temperature=0.0).with_structured_output(ThemesOut)

    try:
        out: ThemesOut = await llm.ainvoke(
            prompt.format(
                critique_instruction=instructions,
                rq=_escape_braces(rq),
                concepts=_escape_braces(json.dumps([c.dict() for c in concepts])),
            ),
            config={
                **_langfuse_config(state, tags, {"branch": branch}),
                "run_name": "synthesis.discover_themes",
            },
        )
        return out.themes or []
    except Exception as e:
        logger.warning(f"Theme discovery failed for {branch}: {e}")
        return [
            DiscoveredTheme(
                theme_name="General Theme",
                theme_description="Auto-generated placeholder",
            )
        ]


async def _critique_themes(
    themes: List[DiscoveredTheme],
    rq: str,
    state: SynthesisState,
    branch: ThemeBranch,
) -> None:
    """Critique themes (runs once, no iteration loop needed)."""
    if not themes:
        return

    print(f"--- Critiquing {branch.title()} Themes ---")
    tags = [
        "component:synthesis",
        "component:synthesis.critique",
        f"branch:{branch}",
        f"model:{THEME_MODEL}",
    ]
    prompt = build_theme_critique_prompt(branch)
    llm = get_llm(THEME_MODEL, temperature=0.0)

    await llm.ainvoke(
        prompt.format(
            rq=_escape_braces(rq),
            themes=_escape_braces(json.dumps([t.dict() for t in themes])),
        ),
        config={
            **_langfuse_config(state, tags, {"branch": branch}),
            "run_name": "synthesis.critique",
        },
    )


async def _map_concepts_to_themes(
    concepts: List[Concept],
    themes: List[DiscoveredTheme],
    state: SynthesisState,
    branch: ThemeBranch,
) -> List[FinalTheme]:
    """Map concepts to discovered themes."""
    if not concepts or not themes:
        return []

    print(f"--- Mapping {branch.title()} Concepts ---")
    theme_defs = [
        {"name": t.theme_name, "description": t.theme_description} for t in themes
    ]
    tags = [
        "component:synthesis",
        "component:synthesis.map",
        f"branch:{branch}",
        f"model:{MAPPING_MODEL}",
    ]

    sem = asyncio.Semaphore(32)
    llm = get_llm(MAPPING_MODEL, temperature=0.0)

    async def classify(concept: Concept) -> Optional[int]:
        prompt = build_classify_concept_prompt()
        async with sem:
            try:
                r = await llm.ainvoke(
                    prompt.format(
                        themes=_escape_braces(json.dumps(theme_defs)),
                        concept=_escape_braces(json.dumps(concept.dict())),
                    ),
                    config={
                        **_langfuse_config(state, tags, {"branch": branch}),
                        "run_name": "synthesis.map",
                    },
                )
                raw = (r.content if hasattr(r, "content") else str(r)).strip()
                idx = int(raw) - 1
                return idx if 0 <= idx < len(themes) else None
            except Exception:
                return None

    assignments = await asyncio.gather(*[classify(c) for c in concepts])

    buckets: Dict[int, List[Concept]] = {i: [] for i in range(len(themes))}
    for concept, idx in zip(concepts, assignments):
        if isinstance(idx, int):
            buckets[idx].append(concept)

    return [
        FinalTheme(
            name=t.theme_name,
            description=t.theme_description,
            concepts=buckets.get(i, []),
            frequency=len(buckets.get(i, [])),
        )
        for i, t in enumerate(themes)
    ]


async def process_issue_themes(state: SynthesisState) -> SynthesisState:
    """Process issue theme discovery, critique, and mapping."""
    rq = state.get("research_question") or "Not specified"
    concepts = state.get("issue_concepts") or []
    themes = await _discover_themes(concepts, rq, state, "issue")
    await _critique_themes(themes, rq, state, "issue")
    finals = await _map_concepts_to_themes(concepts, themes, state, "issue")
    return {"discovered_issue_themes": themes, "final_issue_themes": finals}


async def process_intervention_themes(state: SynthesisState) -> SynthesisState:
    """Process intervention theme discovery, critique, and mapping."""
    rq = state.get("research_question") or "Not specified"
    concepts = state.get("intervention_concepts") or []
    themes = await _discover_themes(concepts, rq, state, "intervention")
    await _critique_themes(themes, rq, state, "intervention")
    finals = await _map_concepts_to_themes(concepts, themes, state, "intervention")
    return {
        "discovered_intervention_themes": themes,
        "final_intervention_themes": finals,
    }


async def process_outcome_themes(state: SynthesisState) -> SynthesisState:
    """Process outcome theme discovery, critique, and mapping."""
    rq = state.get("research_question") or "Not specified"
    concepts = state.get("outcome_concepts") or []
    if not concepts:
        return {"discovered_outcome_themes": [], "final_outcome_themes": []}
    themes = await _discover_themes(concepts, rq, state, "outcome")
    await _critique_themes(themes, rq, state, "outcome")
    finals = await _map_concepts_to_themes(concepts, themes, state, "outcome")
    return {"discovered_outcome_themes": themes, "final_outcome_themes": finals}


# =============================================================================
# PHASE 3: EVIDENCE COVERAGE & AGGREGATION
# =============================================================================


async def compute_evidence_coverage(state: SynthesisState) -> SynthesisState:
    """Compute evidence coverage statistics (deterministic, no LLM)."""
    print("--- Computing Evidence Coverage ---")
    raw_extractions = state.get("raw_extractions") or []
    doc_metadata = state.get("doc_metadata") or {}

    study_types: Counter = Counter()
    countries: Counter = Counter()
    source_types: Counter = Counter()

    for ext in raw_extractions:
        if ext.get("type") == "intervention":
            st = ext.get("study_type")
            if st:
                study_types[normalize_study_type(st)] += 1
            country = ext.get("country")
            if country:
                countries[country] += 1

    years: Counter = Counter()
    for doc in doc_metadata.values():
        if doc.get("year"):
            years[doc["year"]] += 1
        # Count source types
        src_type = normalize_source_type(doc.get("source"), doc.get("document_type"))
        source_types[src_type] += 1

    # Determine strength based on study design quality
    rct_count = sum(c for st, c in study_types.items() if "rct" in st.lower())
    meta_count = sum(c for st, c in study_types.items() if "meta" in st.lower())

    if meta_count >= 3 or rct_count >= 5:
        strength = "High"
    elif meta_count >= 1 or rct_count >= 2:
        strength = "Moderate"
    else:
        strength = "Low"

    gaps = []
    if rct_count == 0:
        gaps.append("No RCTs found in evidence base")
    if meta_count == 0:
        gaps.append("No meta-analyses found")

    # Filter out null/None/empty values from display collections
    null_values = {"null", "none", "", "unknown", "n/a"}
    filtered_study_types = {
        k: v for k, v in study_types.items() if k.lower() not in null_values
    }
    filtered_countries = {
        k: v for k, v in countries.items() if k.lower() not in null_values
    }

    coverage = EvidenceCoverageSnapshot(
        total_sources=len(doc_metadata),
        study_types=filtered_study_types,
        source_types=dict(source_types),
        countries=filtered_countries,
        years={int(k): v for k, v in years.items()},
        overall_strength=strength,
        gaps=gaps,
    )
    return {"evidence_coverage": coverage}


async def build_aggregated_tables(state: SynthesisState) -> SynthesisState:
    """Build aggregated issues, interventions, and outcomes from themes."""
    print("--- Building Aggregated Tables ---")
    final_issue_themes = state.get("final_issue_themes") or []
    final_intervention_themes = state.get("final_intervention_themes") or []
    final_outcome_themes = state.get("final_outcome_themes") or []
    raw_extractions = state.get("raw_extractions") or []

    project_id = state.get("project_id", "")
    supabase = vectorization_service.supabase

    # Build extraction metadata lookup
    all_ex_ids = []
    for t in final_issue_themes + final_intervention_themes + final_outcome_themes:
        all_ex_ids.extend([c.id for c in t.concepts])
    all_ex_ids = list(set(all_ex_ids))

    ex_metadata: Dict[str, Dict] = {}
    if all_ex_ids:
        docs_res = (
            supabase.table("analysis_documents")
            .select("id, doc_id")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        uuid_to_doc_id = {
            str(d["id"]): str(d.get("doc_id") or "") for d in (docs_res.data or [])
        }

        for i in range(0, len(all_ex_ids), 500):
            chunk = all_ex_ids[i : i + 500]
            exts_res = (
                supabase.table("analysis_extractions")
                .select("id, analysis_document_id, raw_data")
                .in_("id", chunk)
                .execute()
            )
            for r in exts_res.data or []:
                doc_uuid = str(r.get("analysis_document_id") or "")
                ex_metadata[str(r["id"])] = {
                    "doc_uuid": doc_uuid,
                    "doc_id": uuid_to_doc_id.get(doc_uuid, ""),
                    "raw_data": r.get("raw_data") or {},
                }

    raw_ext_by_id = {str(e["id"]): e for e in raw_extractions}

    # Build doc_uuid -> result extractions mapping (for effect data)
    doc_to_results: Dict[str, List[Dict]] = {}
    for ext in raw_extractions:
        if ext.get("type") == "result" and ext.get("effect_direction"):
            meta = ex_metadata.get(ext.get("id", ""), {})
            doc_uuid = meta.get("doc_uuid", "")
            if doc_uuid:
                if doc_uuid not in doc_to_results:
                    doc_to_results[doc_uuid] = []
                doc_to_results[doc_uuid].append(ext)
    print(f"Built result mappings for {len(doc_to_results)} documents")

    # Build issues
    issues: List[KeyIssue] = []
    for t in final_issue_themes:
        doc_ids = set()
        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            if meta.get("doc_id"):
                doc_ids.add(meta["doc_id"])
        if doc_ids:
            issues.append(
                KeyIssue(
                    issue_theme=t.name,
                    summary_description=t.description,
                    frequency=len(doc_ids),
                    source_doc_ids=sorted(doc_ids),
                )
            )

    # Build interventions
    interventions: List[PolicyIntervention] = []
    for t in final_intervention_themes:
        doc_ids, doc_uuids, countries_set, study_types_counter = (
            set(),
            set(),
            set(),
            Counter(),
        )

        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            raw = meta.get("raw_data", {})
            raw_ext = raw_ext_by_id.get(c.id, {})

            if meta.get("doc_id"):
                doc_ids.add(meta["doc_id"])
            if meta.get("doc_uuid"):
                doc_uuids.add(meta["doc_uuid"])
            if raw.get("country") or raw_ext.get("country"):
                countries_set.add(raw.get("country") or raw_ext.get("country"))
            if raw.get("study_type") or raw_ext.get("study_type"):
                study_types_counter[
                    raw.get("study_type") or raw_ext.get("study_type")
                ] += 1

        # Aggregate effect counts and sizes from result extractions for these documents
        pos, neg, null = 0, 0, 0
        effect_sizes: List[str] = []
        related_outcomes: List[str] = []
        for doc_uuid in doc_uuids:
            for result_ext in doc_to_results.get(doc_uuid, []):
                effect_dir = result_ext.get("effect_direction", "").lower()
                if effect_dir in ("increase", "positive"):
                    pos += 1
                elif effect_dir in ("decrease", "negative"):
                    neg += 1
                elif effect_dir in ("null", "none", "no effect"):
                    null += 1
                # Collect effect sizes and outcome names
                effect_size = result_ext.get("effect_size", "")
                if effect_size and len(effect_size) > 2:
                    effect_sizes.append(effect_size[:100])
                outcome_var = result_ext.get("outcome_variable", "")
                if outcome_var and outcome_var not in related_outcomes:
                    related_outcomes.append(outcome_var)

        if not doc_ids:
            continue

        total = pos + neg + null
        if total == 0:
            consensus = "insufficient"
        elif pos > neg * 2:
            consensus = "positive"
        elif neg > pos * 2:
            consensus = "negative"
        else:
            consensus = "mixed"

        interventions.append(
            PolicyIntervention(
                intervention_name=t.name,
                brief_description=t.description,
                impact_summary=f"Evidence from {len(doc_ids)} studies ({pos}↑ {neg}↓ {null}—)",
                frequency=len(doc_ids),
                supporting_doc_ids=sorted(doc_ids),
                effect_consensus=consensus,
                positive_count=pos,
                negative_count=neg,
                null_count=null,
                sample_effect_sizes=effect_sizes[:5],  # Keep top 5
                countries=sorted(countries_set),
                study_types=dict(study_types_counter),
                related_outcomes=related_outcomes[:10],  # Keep top 10
            )
        )

    # Build outcomes and per-doc effect mapping
    outcomes: List[OutcomeTheme] = []
    # Mapping: (outcome_name, doc_id) -> list of effect directions
    outcome_doc_effects: Dict[str, Dict[str, List[str]]] = {}

    for t in final_outcome_themes:
        doc_ids = set()
        pos, neg, null = 0, 0, 0
        doc_effect_list: Dict[str, List[str]] = {}

        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            raw_ext = raw_ext_by_id.get(c.id, {})
            doc_id = meta.get("doc_id")
            if doc_id:
                doc_ids.add(doc_id)
            effect_dir = raw_ext.get("effect_direction")
            if effect_dir == "increase":
                pos += 1
                if doc_id:
                    doc_effect_list.setdefault(doc_id, []).append("positive")
            elif effect_dir == "decrease":
                neg += 1
                if doc_id:
                    doc_effect_list.setdefault(doc_id, []).append("negative")
            elif effect_dir == "null":
                null += 1
                if doc_id:
                    doc_effect_list.setdefault(doc_id, []).append("null")

        if not doc_ids:
            continue

        total = pos + neg + null
        if total == 0:
            consensus = "insufficient"
        elif pos > neg * 2:
            consensus = "positive"
        elif neg > pos * 2:
            consensus = "negative"
        else:
            consensus = "mixed"

        outcomes.append(
            OutcomeTheme(
                outcome_name=t.name,
                outcome_description=t.description,
                effect_consensus=consensus,
                positive_count=pos,
                negative_count=neg,
                null_count=null,
                frequency=len(doc_ids),
                source_doc_ids=sorted(doc_ids),
            )
        )
        outcome_doc_effects[t.name] = doc_effect_list

    # Build extraction quotes mapping (doc_uuid -> list of quotes from extractions)
    extraction_quotes: Dict[str, List[str]] = {}
    for ex_id, meta in ex_metadata.items():
        doc_uuid = meta.get("doc_uuid", "")
        raw = meta.get("raw_data", {})
        quote = raw.get("supporting_quote")
        if doc_uuid and quote and isinstance(quote, str) and len(quote) > 20:
            if doc_uuid not in extraction_quotes:
                extraction_quotes[doc_uuid] = []
            extraction_quotes[doc_uuid].append(quote)

    print(
        f"Built {len(issues)} issues, {len(interventions)} interventions, {len(outcomes)} outcomes"
    )
    print(f"Collected extraction quotes for {len(extraction_quotes)} documents")
    return {
        "aggregated_issues": issues,
        "aggregated_interventions": interventions,
        "aggregated_outcomes": outcomes,
        "extraction_quotes": extraction_quotes,
        "outcome_doc_effects": outcome_doc_effects,
    }


# =============================================================================
# PHASE 4: RAG RETRIEVAL
# =============================================================================


def _extract_doc_info_from_chunk(
    chunk: Dict, doc_metadata: Dict[str, Dict]
) -> Dict[str, Any]:
    """Extract document info from chunk, with fallbacks for missing metadata."""
    import re

    doc_uuid = str(chunk.get("document_id", ""))
    doc_info = doc_metadata.get(doc_uuid, {})

    # Get title: prefer doc_metadata, fallback to chunk's document_title
    chunk_doc_title = str(chunk.get("document_title", "")) or "Untitled"
    title = doc_info.get("title") or chunk_doc_title

    # Get author: prefer doc_metadata, fallback to extracting from title
    author_short = doc_info.get("author_short")
    if not author_short and title and title != "Untitled":
        parts = title.split()
        if parts:
            author_short = parts[0].rstrip(",.")

    # Get year: prefer doc_metadata, fallback to extracting from title
    year = doc_info.get("year")
    if not year and title:
        year_match = re.search(r"\((\d{4})\)", title)
        if year_match:
            year = int(year_match.group(1))

    return {
        "doc_uuid": doc_uuid,
        "doc_id": doc_info.get("doc_id"),
        "title": title,
        "author_short": author_short or "Unknown",
        "year": year,
        "url": doc_info.get("url"),
    }


async def retrieve_evidence_for_themes(state: SynthesisState) -> SynthesisState:
    """Retrieve document chunks for intervention themes using RAG."""
    print("--- RAG: Retrieving Evidence for Interventions ---")
    interventions = state.get("aggregated_interventions") or []
    doc_metadata = state.get("doc_metadata") or {}
    extraction_quotes = state.get("extraction_quotes") or {}
    project_id = state.get("project_id", "")

    theme_evidence: Dict[str, List[RetrievedChunk]] = {}
    grounded_citations: List[CitationInfo] = []
    chunk_to_citation: Dict[str, int] = {}
    seen_chunks: set = set()
    used_extraction_quotes = 0

    for intervention in interventions:
        theme_id = intervention.intervention_name
        query = (
            f"{intervention.intervention_name} {intervention.brief_description or ''}"[
                :500
            ]
        )

        if not query.strip():
            theme_evidence[theme_id] = []
            continue

        try:
            raw_chunks = await vectorization_service.search_similar_content(
                query=query, project_id=project_id, match_threshold=0.55, match_count=15
            )

            retrieved: List[RetrievedChunk] = []
            for chunk in raw_chunks or []:
                chunk_id = str(chunk.get("id", ""))
                if chunk_id in seen_chunks:
                    continue
                seen_chunks.add(chunk_id)

                info = _extract_doc_info_from_chunk(chunk, doc_metadata)
                content = str(chunk.get("content", ""))[:500]

                # Prefer extraction quote over chunk content
                doc_uuid = info["doc_uuid"]
                doc_quotes = extraction_quotes.get(doc_uuid, [])
                if doc_quotes:
                    # Use the first (most relevant) extraction quote for this doc
                    supporting_quote = doc_quotes[0][:300]
                    used_extraction_quotes += 1
                else:
                    supporting_quote = content[:300]

                retrieved_chunk = RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=doc_uuid,
                    content=content,
                    chunk_type=str(chunk.get("chunk_type", "content")),
                    similarity=float(chunk.get("similarity", 0)),
                    doc_title=info["title"],
                    author_short=info["author_short"],
                    year=info["year"],
                    url=info["url"],
                )
                retrieved.append(retrieved_chunk)

                if chunk_id not in chunk_to_citation:
                    cit_num = len(grounded_citations) + 1
                    chunk_to_citation[chunk_id] = cit_num
                    grounded_citations.append(
                        CitationInfo(
                            citation_key=f"[{cit_num}]",
                            citation_number=cit_num,
                            doc_id=info["doc_id"],
                            analysis_document_id=doc_uuid,
                            author_short=info["author_short"],
                            year=info["year"],
                            title=info["title"],
                            url=info["url"],
                            supporting_quote=supporting_quote,
                            chunk_id=chunk_id,
                        )
                    )

            retrieved.sort(key=lambda c: c.similarity, reverse=True)
            theme_evidence[theme_id] = retrieved[:8]

        except Exception as e:
            logger.warning(f"RAG retrieval failed for '{theme_id}': {e}")
            theme_evidence[theme_id] = []

    print(
        f"Retrieved evidence for {len(theme_evidence)} themes, {len(grounded_citations)} citations ({used_extraction_quotes} using extraction quotes)"
    )
    if grounded_citations:
        sample = grounded_citations[0]
        print(
            f"Sample citation - key: {sample.citation_key}, num: {sample.citation_number}, title: {sample.title}, quote: {sample.supporting_quote[:80]}..."
        )
    return {
        "theme_evidence": theme_evidence,
        "grounded_citations": grounded_citations,
        "chunk_to_citation": chunk_to_citation,
    }


async def retrieve_evidence_for_issues(state: SynthesisState) -> SynthesisState:
    """Retrieve document chunks for issue themes (for background section)."""
    print("--- RAG: Retrieving Evidence for Issues ---")
    issues = state.get("aggregated_issues") or []
    doc_metadata = state.get("doc_metadata") or {}
    extraction_quotes = state.get("extraction_quotes") or {}
    project_id = state.get("project_id", "")

    grounded_citations = list(state.get("grounded_citations") or [])
    chunk_to_citation = dict(state.get("chunk_to_citation") or {})
    seen_chunks = set(chunk_to_citation.keys())
    issue_evidence: Dict[str, List[RetrievedChunk]] = {}

    for issue in issues:
        theme_id = issue.issue_theme
        query = f"{issue.issue_theme} {issue.summary_description or ''}"[:400]

        if not query.strip():
            issue_evidence[theme_id] = []
            continue

        try:
            raw_chunks = await vectorization_service.search_similar_content(
                query=query, project_id=project_id, match_threshold=0.55, match_count=10
            )

            retrieved: List[RetrievedChunk] = []
            for chunk in raw_chunks or []:
                chunk_id = str(chunk.get("id", ""))
                if chunk_id in seen_chunks:
                    continue
                seen_chunks.add(chunk_id)

                info = _extract_doc_info_from_chunk(chunk, doc_metadata)
                content = str(chunk.get("content", ""))[:500]

                # Prefer extraction quote over chunk content
                doc_uuid = info["doc_uuid"]
                doc_quotes = extraction_quotes.get(doc_uuid, [])
                if doc_quotes:
                    supporting_quote = doc_quotes[0][:300]
                else:
                    supporting_quote = content[:300]

                retrieved_chunk = RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=doc_uuid,
                    content=content,
                    chunk_type=str(chunk.get("chunk_type", "content")),
                    similarity=float(chunk.get("similarity", 0)),
                    doc_title=info["title"],
                    author_short=info["author_short"],
                    year=info["year"],
                    url=info["url"],
                )
                retrieved.append(retrieved_chunk)

                if chunk_id not in chunk_to_citation:
                    cit_num = len(grounded_citations) + 1
                    chunk_to_citation[chunk_id] = cit_num
                    grounded_citations.append(
                        CitationInfo(
                            citation_key=f"[{cit_num}]",
                            citation_number=cit_num,
                            doc_id=info["doc_id"],
                            analysis_document_id=doc_uuid,
                            author_short=info["author_short"],
                            year=info["year"],
                            title=info["title"],
                            url=info["url"],
                            supporting_quote=supporting_quote,
                            chunk_id=chunk_id,
                        )
                    )

            retrieved.sort(key=lambda c: c.similarity, reverse=True)
            issue_evidence[theme_id] = retrieved[:6]

        except Exception as e:
            logger.warning(f"RAG retrieval failed for issue '{theme_id}': {e}")
            issue_evidence[theme_id] = []

    return {
        "issue_evidence": issue_evidence,
        "grounded_citations": grounded_citations,
        "chunk_to_citation": chunk_to_citation,
    }


# =============================================================================
# PHASE 5: STRUCTURED BRIEFING GENERATION
# =============================================================================


async def synthesize_executive_briefing(state: SynthesisState) -> SynthesisState:
    """Generate structured executive briefing with RAG-grounded citations."""
    print("--- Synthesizing Executive Briefing ---")
    rq = state.get("research_question") or "Not specified"
    issues = state.get("aggregated_issues") or []
    interventions = state.get("aggregated_interventions") or []
    evidence_coverage = state.get("evidence_coverage")
    theme_evidence = state.get("theme_evidence") or {}
    issue_evidence = state.get("issue_evidence") or {}
    grounded_citations = state.get("grounded_citations") or []
    chunk_to_citation = state.get("chunk_to_citation") or {}

    # 1. Evidence Snapshot (deterministic)
    evidence_snapshot = _build_evidence_snapshot(evidence_coverage)

    # 2. Background Section
    background = await _generate_background(
        state, issues, issue_evidence, chunk_to_citation
    )

    # 3. Interventions Table
    interventions_table = await _generate_interventions_table(
        state, interventions, theme_evidence, chunk_to_citation
    )

    # 4. Core Answer
    core_answer = await _generate_core_answer(state, rq, interventions, background)

    # 5. Recommendations
    recommendations = await _generate_recommendations(
        state, rq, interventions, theme_evidence, chunk_to_citation
    )

    # 6. Top Citations
    top_citations = _build_top_citations(grounded_citations, interventions_table)

    # 7. Follow-up Suggestions
    follow_ups = []
    if evidence_coverage and evidence_coverage.gaps:
        if any("RCT" in g for g in evidence_coverage.gaps):
            follow_ups.append("Search for randomised controlled trials on this topic")
        if any("systematic" in g.lower() for g in evidence_coverage.gaps):
            follow_ups.append("Look for systematic reviews or meta-analyses")
    if not follow_ups:
        follow_ups = ["Consider searching for implementation case studies"]

    structured_briefing = StructuredBriefing(
        core_answer=core_answer,
        evidence_snapshot=evidence_snapshot,
        evidence_snapshot_summary=" ".join(evidence_coverage.gaps)
        if evidence_coverage
        else "",
        background_section=background,
        interventions_table=interventions_table,
        recommendations=recommendations,
        top_citations=top_citations,
        follow_up_suggestions=follow_ups[:3],
    )

    citation_map = {c.citation_key: c for c in grounded_citations}

    return {
        "executive_briefing": "",  # Legacy field, no longer generated
        "structured_briefing": structured_briefing,
        "citation_map": citation_map,
    }


def _build_evidence_snapshot(
    coverage: Optional[EvidenceCoverageSnapshot]
) -> List[EvidenceSnapshotRow]:
    """Build evidence snapshot rows."""
    if not coverage:
        return [
            EvidenceSnapshotRow(
                metric="Status", detail="Evidence coverage not computed."
            )
        ]

    rows = [
        EvidenceSnapshotRow(
            metric="Total Studies", detail=f"{coverage.total_sources} documents"
        )
    ]

    if coverage.study_types:
        parts = [
            f"**{st}** ({c})"
            for st, c in sorted(coverage.study_types.items(), key=lambda x: -x[1])[:5]
        ]
        rows.append(EvidenceSnapshotRow(metric="Study Types", detail=", ".join(parts)))

    if coverage.countries:
        parts = [
            f"**{c}** ({n})"
            for c, n in sorted(coverage.countries.items(), key=lambda x: -x[1])[:5]
        ]
        rows.append(
            EvidenceSnapshotRow(metric="Geographic Scope", detail=", ".join(parts))
        )

    rows.append(
        EvidenceSnapshotRow(
            metric="Overall Strength", detail=f"**{coverage.overall_strength}**"
        )
    )
    return rows


async def _generate_background(
    state: SynthesisState,
    issues: List[KeyIssue],
    issue_evidence: Dict[str, List[RetrievedChunk]],
    chunk_to_citation: Dict[str, int],
) -> Optional[BackgroundSection]:
    """Generate background section using RAG."""
    if not issues:
        return None

    all_chunks = []
    for issue in issues[:5]:
        all_chunks.extend(issue_evidence.get(issue.issue_theme, [])[:4])

    if not all_chunks:
        return BackgroundSection(
            title="Policy Background",
            paragraphs=["Background context not available."],
            citation_numbers_used=[],
        )

    evidence_lines = []
    for chunk in all_chunks[:12]:
        cit_num = chunk_to_citation.get(chunk.chunk_id, 0)
        evidence_lines.append(
            f"[{cit_num}] {chunk.author_short or 'Unknown'}, {chunk.year or 'n.d.'}: \"{chunk.content[:200]}...\""
        )

    issues_summary = "\n".join(
        [f"- {i.issue_theme}: {i.summary_description}" for i in issues[:5]]
    )

    try:
        prompt = build_background_section_prompt()
        llm = get_llm(BRIEFING_MODEL, temperature=0)
        tags = [
            "component:synthesis",
            "component:synthesis.background",
            f"model:{BRIEFING_MODEL}",
        ]

        resp = await llm.ainvoke(
            prompt.format(
                research_question=state.get("research_question", ""),
                issues_summary=_escape_braces(issues_summary),
                evidence_context=_escape_braces("\n\n".join(evidence_lines)),
            ),
            config={
                **_langfuse_config(state, tags),
                "run_name": "synthesis.background",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        import re

        cit_nums = set(int(m) for m in re.findall(r"\[(\d+)\]", text))

        return BackgroundSection(
            title="Policy Background & Context",
            paragraphs=paragraphs,
            citation_numbers_used=sorted(cit_nums),
        )

    except Exception as e:
        logger.warning(f"Background generation failed: {e}")
        return BackgroundSection(
            title="Policy Background",
            paragraphs=[
                f"Key issues: {', '.join([i.issue_theme for i in issues[:5]])}"
            ],
            citation_numbers_used=[],
        )


async def _generate_interventions_table(
    state: SynthesisState,
    interventions: List[PolicyIntervention],
    theme_evidence: Dict[str, List[RetrievedChunk]],
    chunk_to_citation: Dict[str, int],
) -> List[InterventionTableRow]:
    """Generate interventions table rows with structured context and impact narratives."""
    rows: List[InterventionTableRow] = []
    null_values = {"null", "none", "", "unknown", "n/a"}

    # Use outcome themes from state (computed earlier in the workflow)
    aggregated_outcomes: List[OutcomeTheme] = state.get("aggregated_outcomes") or []

    for intervention in interventions[:10]:
        chunks = theme_evidence.get(intervention.intervention_name, [])
        if not chunks:
            continue

        cit_nums = [
            chunk_to_citation.get(c.chunk_id, 0)
            for c in chunks
            if c.chunk_id in chunk_to_citation
        ][:5]
        intervention_doc_ids = set(intervention.supporting_doc_ids)

        # Build structured context with labels
        context_parts = []

        valid_countries = [
            c for c in intervention.countries if c.lower() not in null_values
        ]
        if valid_countries:
            context_parts.append(f"**Location**: {', '.join(valid_countries[:4])}")

        # Extract setting from brief_description if available
        desc = intervention.brief_description.lower()
        if "school" in desc:
            context_parts.append("**Setting**: School-based")
        elif "community" in desc:
            context_parts.append("**Setting**: Community-based")
        elif "clinic" in desc or "hospital" in desc or "health" in desc:
            context_parts.append("**Setting**: Clinical/health facility")
        elif "workplace" in desc or "employer" in desc:
            context_parts.append("**Setting**: Workplace")

        valid_studies = [
            s for s in intervention.study_types.keys() if s.lower() not in null_values
        ]
        if valid_studies:
            study_counts = [
                f"{s} ({intervention.study_types[s]})" for s in valid_studies[:3]
            ]
            context_parts.append(f"**Studies**: {', '.join(study_counts)}")

        context = " ".join(context_parts) if context_parts else "Various settings"

        # Generate impact narrative using LLM
        impact_narrative = await _generate_impact_narrative(
            state, intervention, chunks, chunk_to_citation
        )

        # Match intervention to outcome themes by doc_id overlap
        # Get per-doc effect mapping
        outcome_doc_effects: Dict[str, Dict[str, List[str]]] = (
            state.get("outcome_doc_effects") or {}
        )

        outcome_effects: List[OutcomeEffect] = []
        for outcome in aggregated_outcomes:
            theme_doc_ids = set(outcome.source_doc_ids)
            overlap = intervention_doc_ids & theme_doc_ids

            if overlap:
                # Calculate counts filtered to overlapping docs only
                doc_effects = outcome_doc_effects.get(outcome.outcome_name, {})
                pos, neg, nul = 0, 0, 0
                for doc_id in overlap:
                    for effect in doc_effects.get(doc_id, []):
                        if effect == "positive":
                            pos += 1
                        elif effect == "negative":
                            neg += 1
                        elif effect == "null":
                            nul += 1

                # Skip if no effects from overlapping docs
                total = pos + neg + nul
                if total == 0:
                    continue

                # Determine direction from filtered counts
                if pos > neg * 2 and pos > nul:
                    direction = "positive"
                elif neg > pos * 2 and neg > nul:
                    direction = "negative"
                elif nul > pos and nul > neg:
                    direction = "null"
                else:
                    direction = "mixed"

                outcome_effects.append(
                    OutcomeEffect(
                        outcome_theme=outcome.outcome_name,
                        direction=direction,
                        positive_count=pos,
                        negative_count=neg,
                        null_count=nul,
                    )
                )

        # Sort by total effect count (most evidence first)
        outcome_effects.sort(
            key=lambda x: -(x.positive_count + x.negative_count + x.null_count)
        )

        rows.append(
            InterventionTableRow(
                intervention_name=intervention.intervention_name,
                citation_numbers=[n for n in cit_nums if n > 0],
                context=context,
                impact_narrative=impact_narrative,
                outcome_effects=outcome_effects[:5],  # Top 5 outcome themes
            )
        )

    return rows


async def _generate_impact_narrative(
    state: SynthesisState,
    intervention: PolicyIntervention,
    chunks: List[RetrievedChunk],
    chunk_to_citation: Dict[str, int],
) -> str:
    """Generate a concise impact narrative for an intervention using RAG evidence."""
    if not chunks:
        return intervention.impact_summary or "Impact data not available."

    # Build evidence context with citations
    evidence_lines = []
    for chunk in chunks[:5]:
        cit_num = chunk_to_citation.get(chunk.chunk_id, 0)
        if cit_num > 0:
            evidence_lines.append(f'[{cit_num}] "{chunk.content[:250]}..."')

    if not evidence_lines:
        return intervention.impact_summary or "Impact data not available."

    try:
        prompt = build_impact_narrative_prompt()
        llm = get_llm(MAPPING_MODEL, temperature=0)
        tags = [
            "component:synthesis",
            "component:synthesis.impact_narrative",
            f"model:{MAPPING_MODEL}",
        ]

        resp = await llm.ainvoke(
            prompt.format(
                intervention_name=intervention.intervention_name,
                effect_consensus=intervention.effect_consensus or "mixed",
                evidence_context=_escape_braces("\n".join(evidence_lines)),
            ),
            config={
                **_langfuse_config(state, tags),
                "run_name": "synthesis.impact_narrative",
            },
        )
        return (resp.content if hasattr(resp, "content") else str(resp)).strip()

    except Exception as e:
        logger.warning(f"Impact narrative generation failed: {e}")
        return intervention.impact_summary or "Impact data not available."


async def _generate_core_answer(
    state: SynthesisState,
    rq: str,
    interventions: List[PolicyIntervention],
    background: Optional[BackgroundSection],
) -> CoreAnswer:
    """Generate core answer section."""
    top_intrs = ", ".join([i.intervention_name for i in interventions[:5]])

    try:
        prompt = build_core_answer_prompt()
        llm = get_llm(BRIEFING_MODEL, temperature=0)
        tags = [
            "component:synthesis",
            "component:synthesis.core_answer",
            f"model:{BRIEFING_MODEL}",
        ]

        resp = await llm.ainvoke(
            prompt.format(
                research_question=rq,
                top_interventions=_escape_braces(top_intrs),
                intervention_count=len(interventions),
                background_context=_escape_braces(
                    background.paragraphs[0]
                    if background and background.paragraphs
                    else ""
                ),
            ),
            config={
                **_langfuse_config(state, tags),
                "run_name": "synthesis.core_answer",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()

        try:
            data = json.loads(text)
            return CoreAnswer(
                query=rq,
                answer=data.get("answer", text),
                directive=data.get("directive", ""),
            )
        except json.JSONDecodeError:
            sentences = text.split(". ")
            return CoreAnswer(
                query=rq,
                answer=sentences[0] + "." if sentences else text,
                directive=". ".join(sentences[1:]) if len(sentences) > 1 else "",
            )

    except Exception as e:
        logger.warning(f"Core answer generation failed: {e}")
        return CoreAnswer(
            query=rq,
            answer=f"Evidence review identified {len(interventions)} intervention types.",
            directive="Further analysis recommended.",
        )


async def _generate_recommendations(
    state: SynthesisState,
    rq: str,
    interventions: List[PolicyIntervention],
    theme_evidence: Dict[str, List[RetrievedChunk]],
    chunk_to_citation: Dict[str, int],
) -> List[RecommendationItem]:
    """Generate recommendations with RAG grounding using structured output."""
    all_evidence = []
    for intr in interventions[:5]:
        for chunk in theme_evidence.get(intr.intervention_name, [])[:3]:
            all_evidence.append((chunk, intr.intervention_name))

    if not all_evidence:
        return []

    evidence_lines = [
        f'[{chunk_to_citation.get(c.chunk_id, 0)}] ({name}) "{c.content[:150]}..."'
        for c, name in all_evidence[:10]
    ]
    top_intrs = [
        f"{i.intervention_name} ({i.effect_consensus or 'mixed'})"
        for i in interventions[:5]
    ]

    prompt = build_recommendations_prompt()
    llm = get_llm(BRIEFING_MODEL, temperature=0)
    tags = [
        "component:synthesis",
        "component:synthesis.recommendations",
        f"model:{BRIEFING_MODEL}",
    ]

    try:
        structured_llm = llm.with_structured_output(RecommendationsOutput)
        result: RecommendationsOutput = await structured_llm.ainvoke(
            prompt.format(
                research_question=rq,
                top_interventions=_escape_braces("\n".join(top_intrs)),
                evidence_context=_escape_braces("\n".join(evidence_lines)),
            ),
            config={
                **_langfuse_config(state, tags),
                "run_name": "synthesis.recommendations",
            },
        )
        # Ensure numbers are sequential
        for idx, rec in enumerate(result.recommendations, 1):
            rec.number = idx
        return result.recommendations
    except Exception as e:
        logger.warning(
            f"Structured recommendations failed: {e}, falling back to text parsing"
        )
        resp = await llm.ainvoke(
            prompt.format(
                research_question=rq,
                top_interventions=_escape_braces("\n".join(top_intrs)),
                evidence_context=_escape_braces("\n".join(evidence_lines)),
            ),
            config={
                **_langfuse_config(state, tags),
                "run_name": "synthesis.recommendations.fallback",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return _parse_recommendations(text)


def _parse_recommendations(text: str) -> List[RecommendationItem]:
    """Fallback parser for recommendations. Expected format: **Title:** Description"""
    import re

    pattern = r"\*\*([^:*]+)\*\*[:\s]*(.+?)(?=\n\*\*|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    return [
        RecommendationItem(
            number=idx,
            title=title.strip(),
            description=desc.strip(),
            citation_numbers=[int(m) for m in re.findall(r"\[(\d+)\]", desc)],
        )
        for idx, (title, desc) in enumerate(matches, 1)
    ]


def _build_top_citations(
    grounded_citations: List[CitationInfo],
    interventions_table: List[InterventionTableRow],
) -> List[TopCitationItem]:
    """Build top citations ranked by usage."""
    usage: Counter = Counter()
    for row in interventions_table:
        for cit_num in row.citation_numbers:
            usage[cit_num] += 1

    citation_by_num = {c.citation_number: c for c in grounded_citations}
    ranked = sorted(usage.keys(), key=lambda n: (-usage[n], n))

    top_citations = []
    for cit_num in ranked[:5]:
        cit = citation_by_num.get(cit_num)
        if cit:
            top_citations.append(
                TopCitationItem(
                    citation_number=cit_num,
                    title=cit.title or "Untitled",
                    author_year=f"{cit.author_short or 'Unknown'}, {cit.year or 'n.d.'}",
                    reason=f"Referenced in {usage[cit_num]} intervention(s)",
                    url=cit.url,
                )
            )

    return top_citations


# =============================================================================
# WORKFLOW DEFINITION
# =============================================================================


def create_synthesis_workflow():
    """Create the synthesis workflow."""
    workflow = StateGraph(SynthesisState)

    # Phase 1: Load
    workflow.add_node("load_raw_extractions", load_raw_extractions)
    workflow.add_node("create_canonical_concepts", create_canonical_concepts)

    # Phase 2: Theme discovery (consolidated - no more critique loops)
    workflow.add_node("process_issue_themes", process_issue_themes)
    workflow.add_node("process_intervention_themes", process_intervention_themes)
    workflow.add_node("process_outcome_themes", process_outcome_themes)

    # Phase 3: Aggregation
    workflow.add_node("compute_evidence_coverage", compute_evidence_coverage)
    workflow.add_node("build_aggregated_tables", build_aggregated_tables)

    # Phase 4: RAG
    workflow.add_node("retrieve_evidence_for_themes", retrieve_evidence_for_themes)
    workflow.add_node("retrieve_evidence_for_issues", retrieve_evidence_for_issues)

    # Phase 5: Briefing
    workflow.add_node("synthesize_executive_briefing", synthesize_executive_briefing)

    # Edges
    workflow.set_entry_point("load_raw_extractions")
    workflow.add_edge("load_raw_extractions", "create_canonical_concepts")

    # Parallel theme processing
    workflow.add_edge("create_canonical_concepts", "process_issue_themes")
    workflow.add_edge("create_canonical_concepts", "process_intervention_themes")
    workflow.add_edge("create_canonical_concepts", "process_outcome_themes")

    # Converge to aggregation
    workflow.add_edge("process_issue_themes", "compute_evidence_coverage")
    workflow.add_edge("process_intervention_themes", "compute_evidence_coverage")
    workflow.add_edge("process_outcome_themes", "compute_evidence_coverage")

    workflow.add_edge("compute_evidence_coverage", "build_aggregated_tables")
    workflow.add_edge("build_aggregated_tables", "retrieve_evidence_for_themes")
    workflow.add_edge("retrieve_evidence_for_themes", "retrieve_evidence_for_issues")
    workflow.add_edge("retrieve_evidence_for_issues", "synthesize_executive_briefing")
    workflow.add_edge("synthesize_executive_briefing", END)

    return workflow.compile()


class SynthesisAgent:
    """Facade for running the synthesis workflow."""

    def __init__(self) -> None:
        self.workflow = create_synthesis_workflow()

    async def run(
        self, project_id: str, user_id: Optional[str] = None
    ) -> SynthesisState:
        session_id = resolve_langfuse_session_id(project_id)
        handler = get_langfuse_handler(session_id=session_id)
        resolved_user = user_id or self._resolve_project_user(project_id)

        initial_state: SynthesisState = {
            "project_id": project_id,
            "langfuse_handler": handler,
            "langfuse_session_id": session_id,
            "policy_user_id": resolved_user,
        }
        return await self.workflow.ainvoke(initial_state)

    @staticmethod
    def _resolve_project_user(project_id: str) -> Optional[str]:
        try:
            result = (
                vectorization_service.supabase.table("analysis_projects")
                .select("created_by_user_id")
                .eq("id", project_id)
                .execute()
            )
            return result.data[0].get("created_by_user_id") if result.data else None
        except Exception:
            return None
