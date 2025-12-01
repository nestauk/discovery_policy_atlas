from __future__ import annotations

import asyncio
import json
from typing import List, Dict, TypedDict, Optional, Any
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from app.services.vectorization import vectorization_service
from app.utils.llm.llm_utils import (
    get_llm,
    get_langfuse_handler,
    build_langfuse_metadata,
    resolve_langfuse_session_id,
)
from app.services.synthesis.schemas import KeyIssue, PolicyIntervention
from app.services.synthesis.prompts import (
    build_discover_themes_prompt,
    make_discover_themes_instructions,
    build_theme_critique_prompt,
    build_classify_concept_prompt,
    build_impact_summary_prompt,
    build_executive_briefing_prompt,
)


class Concept(BaseModel):
    """A data structure for a single enriched concept."""

    id: str
    canonical_description: str


# Model selection per node
THEME_MODEL = "gpt-5-mini"  # define_themes, critique_themes
MAPPING_MODEL = "gpt-5-nano"  # map concepts to final themes
BRIEFING_MODEL = "gpt-5"  # synthesise executive briefing
CRITIQUE_ITERATIONS = 1


def _escape_braces(text: str) -> str:
    """Escape braces to avoid ChatPromptTemplate .format() interpreting them as variables."""
    return (text or "").replace("{", "{{").replace("}", "}}")


def _langfuse_config(
    state: SynthesisState,
    tags: List[str],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    handler = state.get("langfuse_handler")
    metadata = build_langfuse_metadata(
        tags=tags,
        session_id=state.get("langfuse_session_id"),
        user_id=state.get("policy_user_id"),
        project_id=state.get("project_id"),
        extra=extra,
    )
    return {
        "callbacks": [handler] if handler else [],
        "tags": tags,
        "metadata": metadata,
    }


class DiscoveredTheme(BaseModel):
    """A theme discovered by the first LLM pass (definitions only)."""

    theme_name: str
    theme_description: str


class FinalTheme(BaseModel):
    """The final, validated theme with all its concepts mapped."""

    name: str
    description: str
    concepts: List[Concept] = Field(default_factory=list)
    frequency: int = 0


class SynthesisState(TypedDict):
    project_id: str
    research_question: str
    raw_extractions: List[Dict]
    # Parallel concept sets
    issue_concepts: List[Concept]
    intervention_concepts: List[Concept]
    # Discovered themes per branch
    discovered_issue_themes: List[DiscoveredTheme]
    discovered_intervention_themes: List[DiscoveredTheme]
    # Critiques and iteration counters per branch
    issue_theme_critique: Optional[str]
    intervention_theme_critique: Optional[str]
    issue_theme_iteration: int
    intervention_theme_iteration: int
    # Final themed concepts per branch
    final_issue_themes: List[FinalTheme]
    final_intervention_themes: List[FinalTheme]
    executive_briefing: str
    aggregated_issues: List[KeyIssue]
    aggregated_interventions: List[PolicyIntervention]
    # Langfuse handler for tracing (injected at runtime)
    langfuse_handler: Any
    langfuse_session_id: str
    policy_user_id: Optional[str]


class ThemesOut(BaseModel):
    """Structured output container for discovered themes."""

    themes: List[DiscoveredTheme]


async def _discover_themes_for_concepts(
    concepts: List[Concept],
    critique: Optional[str],
    rq: str,
    *,
    handler: Any = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    run_name: Optional[str] = None,
) -> List[DiscoveredTheme]:
    """Generic helper to discover themes for a given concept set (structured output)."""
    if not concepts:
        return []
    instructions = make_discover_themes_instructions(critique)
    prompt = build_discover_themes_prompt()
    base_llm = get_llm(THEME_MODEL, temperature=0.0)
    structured_llm = base_llm.with_structured_output(ThemesOut)
    try:
        out: ThemesOut = await structured_llm.ainvoke(
            prompt.format(
                critique_instruction=instructions,
                rq=_escape_braces(rq),
                concepts=_escape_braces(json.dumps([c.dict() for c in concepts])),
            ),
            config={
                "callbacks": [handler] if handler else [],
                "tags": tags or [],
                "metadata": metadata or {},
                "run_name": run_name or "synthesis.discover_themes",
            },
        )
        return out.themes or []
    except Exception:
        return [
            DiscoveredTheme(
                theme_name="General Theme",
                theme_description="Auto-generated theme placeholder",
            )
        ]


async def load_raw_extractions(state: SynthesisState) -> SynthesisState:
    """Load raw extractions and research question for a project."""
    print("--- Step 0: Loading Raw Extractions ---")
    project_id = state.get("project_id", "")
    if not project_id:
        return {"raw_extractions": [], "research_question": "Not specified"}  # type: ignore[return-value]

    supabase = vectorization_service.supabase
    # Fetch research question (prefer title; fallback to query for backward compatibility)
    proj_res = (
        supabase.table("analysis_projects")
        .select("title, query")
        .eq("id", project_id)
        .execute()
    )
    research_question = (
        (proj_res.data[0].get("title") or proj_res.data[0].get("query"))
        if proj_res and proj_res.data
        else None
    ) or "Not specified"
    res = (
        supabase.table("analysis_extractions")
        .select(
            "id, analysis_document_id, extraction_type, label, description, raw_data"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )
    rows: List[Dict[str, Any]] = res.data or []

    def to_uniform(row: Dict[str, Any]) -> Dict[str, Any]:
        et = str(row.get("extraction_type") or "")
        raw = row.get("raw_data") or {}
        if et == "intervention":
            return {
                "id": str(row.get("id")),
                "type": "intervention",
                "intervention_name": str(row.get("label") or raw.get("name") or ""),
                "intervention_type": str(
                    raw.get("study_type") or raw.get("type") or ""
                ),
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
        return {"id": str(row.get("id")), "type": et}

    uniform = [to_uniform(r) for r in rows]
    print(f"Loaded {len(uniform)} extractions")
    return {"raw_extractions": uniform, "research_question": research_question}  # type: ignore[return-value]


async def create_canonical_concepts(state: SynthesisState) -> SynthesisState:
    """Create and separate canonical concepts for issues and interventions."""
    print("--- Step 1: Creating and Separating Canonical Concepts ---")

    issue_concepts: List[Concept] = []
    intervention_concepts: List[Concept] = []

    for ext in state.get("raw_extractions", []) or []:
        if ext.get("issue_label"):
            desc = f"Issue: {ext.get('issue_label', '')}. Explanation: {ext.get('explanation', '')}"
            issue_concepts.append(Concept(id=ext["id"], canonical_description=desc))
        if ext.get("intervention_name"):
            desc = (
                f"Intervention: {ext.get('intervention_name', '')}. "
                f"Type: {ext.get('intervention_type', '')}. "
                f"Description: {ext.get('description', '')}"
            )
            intervention_concepts.append(
                Concept(id=ext["id"], canonical_description=desc)
            )

    return {
        **state,
        "issue_concepts": issue_concepts,
        "intervention_concepts": intervention_concepts,
        "issue_theme_iteration": 0,
        "intervention_theme_iteration": 0,
    }


async def define_issue_themes(state: SynthesisState) -> SynthesisState:
    tags = [
        "component:synthesis",
        "component:synthesis.discover_themes",
        "branch:issues",
        f"model:{THEME_MODEL}",
    ]
    themes = await _discover_themes_for_concepts(
        state.get("issue_concepts", []) or [],
        state.get("issue_theme_critique"),
        str(state.get("research_question") or "Not specified"),
        handler=state.get("langfuse_handler"),
        tags=tags,
        metadata=build_langfuse_metadata(
            tags=tags,
            session_id=state.get("langfuse_session_id"),
            user_id=state.get("policy_user_id"),
            project_id=state.get("project_id"),
            extra={"branch": "issues"},
        ),
        run_name="synthesis.discover_themes",
    )
    return {"discovered_issue_themes": themes}


async def define_intervention_themes(state: SynthesisState) -> SynthesisState:
    tags = [
        "component:synthesis",
        "component:synthesis.discover_themes",
        "branch:interventions",
        f"model:{THEME_MODEL}",
    ]
    themes = await _discover_themes_for_concepts(
        state.get("intervention_concepts", []) or [],
        state.get("intervention_theme_critique"),
        str(state.get("research_question") or "Not specified"),
        handler=state.get("langfuse_handler"),
        tags=tags,
        metadata=build_langfuse_metadata(
            tags=tags,
            session_id=state.get("langfuse_session_id"),
            user_id=state.get("policy_user_id"),
            project_id=state.get("project_id"),
            extra={"branch": "interventions"},
        ),
        run_name="synthesis.discover_themes",
    )
    return {"discovered_intervention_themes": themes}


async def critique_issue_themes(state: SynthesisState) -> SynthesisState:
    print("--- Critiquing Issue Themes ---")
    themes_payload = _escape_braces(
        json.dumps([t.dict() for t in state.get("discovered_issue_themes", [])])
    )
    prompt = build_theme_critique_prompt("issue")
    llm = get_llm(THEME_MODEL, temperature=0.0)
    tags = [
        "component:synthesis",
        "component:synthesis.critique",
        "branch:issues",
        f"model:{THEME_MODEL}",
    ]
    resp = await llm.ainvoke(
        prompt.format(
            rq=_escape_braces(str(state.get("research_question") or "Not specified")),
            themes=themes_payload,
        ),
        config={
            **_langfuse_config(
                state,
                tags,
                extra={"branch": "issues"},
            ),
            "run_name": "synthesis.critique",
        },
    )
    critique = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    next_iter = int(state.get("issue_theme_iteration") or 0) + 1
    return {
        "issue_theme_critique": critique if critique.lower() != "none" else None,
        "issue_theme_iteration": next_iter,
    }


async def critique_intervention_themes(state: SynthesisState) -> SynthesisState:
    print("--- Critiquing Intervention Themes ---")
    themes_payload = _escape_braces(
        json.dumps([t.dict() for t in state.get("discovered_intervention_themes", [])])
    )
    prompt = build_theme_critique_prompt("intervention")
    llm = get_llm(THEME_MODEL, temperature=0.0)
    tags = [
        "component:synthesis",
        "component:synthesis.critique",
        "branch:interventions",
        f"model:{THEME_MODEL}",
    ]
    resp = await llm.ainvoke(
        prompt.format(
            rq=_escape_braces(str(state.get("research_question") or "Not specified")),
            themes=themes_payload,
        ),
        config={
            **_langfuse_config(
                state,
                tags,
                extra={"branch": "interventions"},
            ),
            "run_name": "synthesis.critique",
        },
    )
    critique = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    next_iter = int(state.get("intervention_theme_iteration") or 0) + 1
    return {
        "intervention_theme_critique": critique if critique.lower() != "none" else None,
        "intervention_theme_iteration": next_iter,
    }


async def _map_concepts(
    concepts: List[Concept],
    themes: List[DiscoveredTheme],
    *,
    handler: Any = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    run_name: Optional[str] = None,
) -> List[FinalTheme]:
    if not concepts or not themes:
        return []

    # Prepare a compact list for prompting
    theme_defs = [
        {"name": t.theme_name, "description": t.theme_description} for t in themes
    ]

    sem = asyncio.Semaphore(32)
    llm = get_llm(MAPPING_MODEL, temperature=0.0)

    async def _classify(concept: Concept) -> Optional[int]:
        prompt = build_classify_concept_prompt()
        async with sem:
            try:
                r = await llm.ainvoke(
                    prompt.format(
                        themes=_escape_braces(json.dumps(theme_defs)),
                        concept=_escape_braces(json.dumps(concept.dict())),
                    ),
                    config={
                        "callbacks": [handler] if handler else [],
                        "tags": tags or [],
                        "metadata": metadata or {},
                        "run_name": run_name or "synthesis.map_concepts",
                    },
                )
                raw = (r.content if hasattr(r, "content") else str(r)).strip()
                # Parse integer index directly
                idx = int(raw) - 1
                if 0 <= idx < len(themes):
                    return idx
            except Exception:
                return None
        return None

    assignments = await asyncio.gather(*[_classify(c) for c in concepts])

    # Aggregate
    buckets: Dict[int, List[Concept]] = {i: [] for i in range(len(themes))}
    for concept, idx in zip(concepts, assignments):
        if isinstance(idx, int) and 0 <= idx < len(themes):
            buckets[idx].append(concept)

    final_themes_list: List[FinalTheme] = []
    for i, t in enumerate(themes):
        cs = buckets.get(i, [])
        final_themes_list.append(
            FinalTheme(
                name=t.theme_name,
                description=t.theme_description,
                concepts=cs,
                frequency=len(cs),
            )
        )

    return final_themes_list


async def map_issue_concepts_to_final_themes(state: SynthesisState) -> SynthesisState:
    print("--- Mapping Issue Concepts to Final Themes ---")
    tags = [
        "component:synthesis",
        "component:synthesis.map_concepts",
        "branch:issues",
        f"model:{MAPPING_MODEL}",
    ]
    finals = await _map_concepts(
        state.get("issue_concepts", []) or [],
        state.get("discovered_issue_themes", []) or [],
        handler=state.get("langfuse_handler"),
        tags=tags,
        metadata=build_langfuse_metadata(
            tags=tags,
            session_id=state.get("langfuse_session_id"),
            user_id=state.get("policy_user_id"),
            project_id=state.get("project_id"),
            extra={"branch": "issues"},
        ),
        run_name="synthesis.map_concepts",
    )
    return {"final_issue_themes": finals}


async def map_intervention_concepts_to_final_themes(
    state: SynthesisState
) -> SynthesisState:
    print("--- Mapping Intervention Concepts to Final Themes ---")
    tags = [
        "component:synthesis",
        "component:synthesis.map_concepts",
        "branch:interventions",
        f"model:{MAPPING_MODEL}",
    ]
    finals = await _map_concepts(
        state.get("intervention_concepts", []) or [],
        state.get("discovered_intervention_themes", []) or [],
        handler=state.get("langfuse_handler"),
        tags=tags,
        metadata=build_langfuse_metadata(
            tags=tags,
            session_id=state.get("langfuse_session_id"),
            user_id=state.get("policy_user_id"),
            project_id=state.get("project_id"),
            extra={"branch": "interventions"},
        ),
        run_name="synthesis.map_concepts",
    )
    return {"final_intervention_themes": finals}


async def build_aggregated_tables(state: SynthesisState) -> SynthesisState:
    """Derive KeyIssue and PolicyIntervention tables from separate final theme sets.

    Frequency is computed as unique document coverage per theme using Supabase lookups.
    """
    print("--- Building Aggregated Tables from Final Themes ---")
    final_issue_themes: List[FinalTheme] = state.get("final_issue_themes", []) or []
    final_intervention_themes: List[FinalTheme] = (
        state.get("final_intervention_themes", []) or []
    )
    issues: List[KeyIssue] = []
    interventions: List[PolicyIntervention] = []

    # Build mapping from extraction_id to analysis_document_id -> doc_id
    project_id = state.get("project_id", "")
    supabase = vectorization_service.supabase

    # Gather all concept extraction IDs per theme
    def concept_ids_for_theme(t: FinalTheme) -> List[str]:
        # Concepts were created from extractions; use concept.id
        return [c.id for c in t.concepts]

    all_issue_ex_ids: List[str] = []
    for t in final_issue_themes:
        all_issue_ex_ids.extend(concept_ids_for_theme(t))
    all_intr_ex_ids: List[str] = []
    for t in final_intervention_themes:
        all_intr_ex_ids.extend(concept_ids_for_theme(t))

    def fetch_doc_ids_for_extractions(ex_ids: List[str]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        if not ex_ids:
            return mapping
        CHUNK = 1000
        # Preload analysis_documents for this project to map analysis_document_id -> doc_id
        docs_res = (
            supabase.table("analysis_documents")
            .select("id, doc_id")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        doc_uuid_to_doc_id = {
            str(d.get("id")): str(d.get("doc_id") or "") for d in (docs_res.data or [])
        }
        for i in range(0, len(ex_ids), CHUNK):
            chunk = ex_ids[i : i + CHUNK]
            exts_res = (
                supabase.table("analysis_extractions")
                .select("id, analysis_document_id")
                .in_("id", chunk)
                .execute()
            )
            for r in exts_res.data or []:
                rid = str(r.get("id"))
                doc_uuid = str(r.get("analysis_document_id") or "")
                mapping[rid] = doc_uuid_to_doc_id.get(doc_uuid, "")
        return mapping

    issue_ex_id_to_doc_id = fetch_doc_ids_for_extractions(all_issue_ex_ids)
    intr_ex_id_to_doc_id = fetch_doc_ids_for_extractions(all_intr_ex_ids)

    # Helper to generate a short impact summary via LLM (fast model)
    async def _impact_for_theme(name: str, concept_texts: List[str]) -> str:
        try:
            llm = get_llm(MAPPING_MODEL, temperature=0)
            sample = "\n".join([f"- {s}" for s in concept_texts[:8]])
            prompt = build_impact_summary_prompt()
            tags = [
                "component:synthesis",
                "component:synthesis.impact_summary",
                f"model:{MAPPING_MODEL}",
            ]
            resp = await llm.ainvoke(
                prompt.format(name=name, sample=_escape_braces(sample)),
                config={
                    **_langfuse_config(
                        state,
                        tags,
                    ),
                    "run_name": "synthesis.impact_summary",
                },
            )
            return (resp.content if hasattr(resp, "content") else str(resp)).strip()
        except Exception:
            return "Synthesised from grouped concept evidence."

    # Build Key Issues with doc coverage
    for t in final_issue_themes:
        ids = concept_ids_for_theme(t)
        doc_ids = sorted(
            list(
                {
                    issue_ex_id_to_doc_id.get(x, "")
                    for x in ids
                    if issue_ex_id_to_doc_id.get(x)
                }
            )
        )
        freq = len(doc_ids)
        if freq == 0:
            continue
        issues.append(
            KeyIssue(
                issue_theme=t.name,
                summary_description=t.description,
                frequency=freq,
                source_doc_ids=doc_ids,
            )
        )

    # Build Interventions with doc coverage and impact summary
    for t in final_intervention_themes:
        ids = concept_ids_for_theme(t)
        doc_ids = sorted(
            list(
                {
                    intr_ex_id_to_doc_id.get(x, "")
                    for x in ids
                    if intr_ex_id_to_doc_id.get(x)
                }
            )
        )
        freq = len(doc_ids)
        if freq == 0:
            continue
        impact = await _impact_for_theme(
            t.name, [c.canonical_description for c in t.concepts]
        )
        interventions.append(
            PolicyIntervention(
                intervention_name=t.name,
                brief_description=t.description,
                impact_summary=impact,
                frequency=freq,
                supporting_doc_ids=doc_ids,
            )
        )

    return {"aggregated_issues": issues, "aggregated_interventions": interventions}


async def synthesize_executive_briefing(state: SynthesisState) -> SynthesisState:
    """Generates the final executive briefing from separated issues and interventions."""
    print("--- Step 5: Synthesizing Executive Briefing ---")
    rq = state.get("research_question") or "Not specified"
    issues = state.get("aggregated_issues", []) or []
    interventions = state.get("aggregated_interventions", []) or []

    payload = {
        "issues": [
            {
                "name": t.issue_theme,
                "description": t.summary_description,
                "frequency": t.frequency,
            }
            for t in issues
        ],
        "interventions": [
            {
                "name": t.intervention_name,
                "description": t.brief_description,
                "frequency": t.frequency,
            }
            for t in interventions
        ],
    }

    prompt = build_executive_briefing_prompt()
    llm = get_llm(BRIEFING_MODEL, temperature=0)
    try:
        tags = [
            "component:synthesis",
            "component:synthesis.executive_brief",
            f"model:{BRIEFING_MODEL}",
        ]
        resp = await llm.ainvoke(
            prompt.format(
                rq=rq,
                payload=_escape_braces(json.dumps(payload)),
            ),
            config={
                **_langfuse_config(
                    state,
                    tags,
                ),
                "run_name": "synthesis.executive_brief",
            },
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("text\n"):
                text = text[len("text\n") :]

        executive_briefing = text
    except Exception:
        executive_briefing = (
            "Executive briefing could not be generated from the current themes."
        )
    return {"executive_briefing": executive_briefing}


def check_issue_critique(state: SynthesisState) -> str:
    has_critique = bool(state.get("issue_theme_critique"))
    iter_num = int(state.get("issue_theme_iteration") or 0)
    if has_critique and iter_num < CRITIQUE_ITERATIONS:
        return "define_issue_themes"
    return "map_issue_concepts_to_final_themes"


def check_intervention_critique(state: SynthesisState) -> str:
    has_critique = bool(state.get("intervention_theme_critique"))
    iter_num = int(state.get("intervention_theme_iteration") or 0)
    if has_critique and iter_num < CRITIQUE_ITERATIONS:
        return "define_intervention_themes"
    return "map_intervention_concepts_to_final_themes"


def create_synthesis_workflow():
    workflow = StateGraph(SynthesisState)
    workflow.add_node("load_raw_extractions", load_raw_extractions)
    workflow.add_node("create_canonical_concepts", create_canonical_concepts)
    # Issue branch
    workflow.add_node("define_issue_themes", define_issue_themes)
    workflow.add_node("critique_issue_themes", critique_issue_themes)
    workflow.add_node(
        "map_issue_concepts_to_final_themes", map_issue_concepts_to_final_themes
    )
    # Intervention branch
    workflow.add_node("define_intervention_themes", define_intervention_themes)
    workflow.add_node("critique_intervention_themes", critique_intervention_themes)
    workflow.add_node(
        "map_intervention_concepts_to_final_themes",
        map_intervention_concepts_to_final_themes,
    )
    workflow.add_node("build_aggregated_tables", build_aggregated_tables)
    workflow.add_node("synthesize_executive_briefing", synthesize_executive_briefing)

    workflow.set_entry_point("load_raw_extractions")
    workflow.add_edge("load_raw_extractions", "create_canonical_concepts")
    # Parallel issue branch
    workflow.add_edge("create_canonical_concepts", "define_issue_themes")
    workflow.add_edge("define_issue_themes", "critique_issue_themes")
    workflow.add_conditional_edges("critique_issue_themes", check_issue_critique)
    # Parallel intervention branch
    workflow.add_edge("create_canonical_concepts", "define_intervention_themes")
    workflow.add_edge("define_intervention_themes", "critique_intervention_themes")
    workflow.add_conditional_edges(
        "critique_intervention_themes", check_intervention_critique
    )
    # Both mapping nodes converge to aggregation
    workflow.add_edge("map_issue_concepts_to_final_themes", "build_aggregated_tables")
    workflow.add_edge(
        "map_intervention_concepts_to_final_themes", "build_aggregated_tables"
    )
    workflow.add_edge("build_aggregated_tables", "synthesize_executive_briefing")
    workflow.add_edge("synthesize_executive_briefing", END)

    return workflow.compile()


class SynthesisAgent:
    """Facade for running the synthesis workflow for a given project."""

    def __init__(self) -> None:
        self.workflow = create_synthesis_workflow()

    async def run(
        self, project_id: str, user_id: Optional[str] = None
    ) -> SynthesisState:
        # Create a per-run Langfuse session and propagate handler through state
        session_id = resolve_langfuse_session_id(project_id)
        handler = get_langfuse_handler(session_id=session_id)
        resolved_user = user_id or self._resolve_project_user(project_id)
        initial_state: SynthesisState = {  # type: ignore[assignment]
            "project_id": project_id,
            "langfuse_handler": handler,
            "langfuse_session_id": session_id,
            "policy_user_id": resolved_user,
        }
        final_state: SynthesisState = await self.workflow.ainvoke(initial_state)
        return final_state

    @staticmethod
    def _resolve_project_user(project_id: str) -> Optional[str]:
        try:
            result = (
                vectorization_service.supabase.table("analysis_projects")
                .select("created_by_user_id")
                .eq("id", project_id)
                .execute()
            )
            if result.data:
                return result.data[0].get("created_by_user_id")
        except Exception:
            return None
        return None
