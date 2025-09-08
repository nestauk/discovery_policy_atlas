from __future__ import annotations

import asyncio
import json
from typing import List, Dict, TypedDict, Optional, Any
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from app.services.vectorization import vectorization_service
from app.utils.llm.llm_utils import get_llm
from langchain_core.prompts import ChatPromptTemplate
from app.services.synthesis.schemas import KeyIssue, PolicyIntervention


class Concept(BaseModel):
    """A data structure for a single enriched concept."""

    id: str
    canonical_description: str


# Model selection per node
HIGH_REASONING_MODEL = "gpt-5-mini"  # define_themes, critique_themes
CLASSIFICATION_MODEL = "gpt-5-nano"  # map_concepts_to_final_themes
BRIEFING_MODEL = "gpt-5"  # synthesize_executive_briefing


def _escape_braces(text: str) -> str:
    """Escape braces to avoid ChatPromptTemplate .format() interpreting them as variables."""
    return (text or "").replace("{", "{{").replace("}", "}}")


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


class ThemesOut(BaseModel):
    """Structured output container for discovered themes."""

    themes: List[DiscoveredTheme]


async def _discover_themes_for_concepts(
    concepts: List[Concept], critique: Optional[str]
) -> List[DiscoveredTheme]:
    """Generic helper to discover themes for a given concept set (structured output)."""
    if not concepts:
        return []
    critique_prompt_addition = (
        f"You must address the following critique of your previous attempt: {critique}"
        if critique
        else ""
    )
    system = "You are a senior research analyst at Nesta. Identify the natural thematic structure in the provided concepts."
    user = (
        "Follow these principles: 1) Exhaustiveness; 2) Mutual Exclusivity; 3) Appropriate Granularity.\n"
        f"{critique_prompt_addition}\n"
        "Return a structured list of themes with name and description only."
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", system), ("user", "{instructions}\n\nCONCEPTS:\n{concepts}")]
    )
    base_llm = get_llm(HIGH_REASONING_MODEL, temperature=0.0)
    structured_llm = base_llm.with_structured_output(ThemesOut)
    try:
        out: ThemesOut = await structured_llm.ainvoke(
            prompt.format(
                instructions=user,
                concepts=_escape_braces(json.dumps([c.dict() for c in concepts])),
            )
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
    # Fetch research question
    proj_res = (
        supabase.table("analysis_projects")
        .select("query")
        .eq("id", project_id)
        .execute()
    )
    research_question = (
        proj_res.data[0].get("query") if proj_res and proj_res.data else None
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
    themes = await _discover_themes_for_concepts(
        state.get("issue_concepts", []) or [], state.get("issue_theme_critique")
    )
    return {"discovered_issue_themes": themes}


async def define_intervention_themes(state: SynthesisState) -> SynthesisState:
    themes = await _discover_themes_for_concepts(
        state.get("intervention_concepts", []) or [],
        state.get("intervention_theme_critique"),
    )
    return {"discovered_intervention_themes": themes}


async def critique_issue_themes(state: SynthesisState) -> SynthesisState:
    print("--- Critiquing Issue Themes ---")
    themes_payload = _escape_braces(
        json.dumps([t.dict() for t in state.get("discovered_issue_themes", [])])
    )
    system = "You return STRICT TEXT only: either 'None' or a concise list of changes."
    user = (
        "Assess issue themes against: Exhaustiveness, Mutual Exclusivity, Appropriate Granularity.\n"
        "If acceptable, reply exactly 'None'. Otherwise, list concise edits.\n\n"
        f"Themes: {themes_payload}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(HIGH_REASONING_MODEL, temperature=0.0)
    resp = await llm.ainvoke(prompt.format())
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
    system = "You return STRICT TEXT only: either 'None' or a concise list of changes."
    user = (
        "Assess intervention themes against: Exhaustiveness, Mutual Exclusivity, Appropriate Granularity.\n"
        "If acceptable, reply exactly 'None'. Otherwise, list concise edits.\n\n"
        f"Themes: {themes_payload}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(HIGH_REASONING_MODEL, temperature=0.0)
    resp = await llm.ainvoke(prompt.format())
    critique = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    next_iter = int(state.get("intervention_theme_iteration") or 0) + 1
    return {
        "intervention_theme_critique": critique if critique.lower() != "none" else None,
        "intervention_theme_iteration": next_iter,
    }


async def _map_concepts(
    concepts: List[Concept], themes: List[DiscoveredTheme]
) -> List[FinalTheme]:
    if not concepts or not themes:
        return []

    # Prepare a compact list for prompting
    theme_defs = [
        {"name": t.theme_name, "description": t.theme_description} for t in themes
    ]

    sem = asyncio.Semaphore(12)
    llm = get_llm(CLASSIFICATION_MODEL, temperature=0.0)

    async def _classify(concept: Concept) -> Optional[int]:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Return only the number."),
                (
                    "user",
                    "Classify the concept to the single best matching theme. Respond ONLY with the theme number (e.g., 1). No words.\n\nThemes:\n{themes}\n\nConcept:\n{concept}",
                ),
            ]
        )
        async with sem:
            try:
                r = await llm.ainvoke(
                    prompt.format(
                        themes=_escape_braces(json.dumps(theme_defs)),
                        concept=_escape_braces(json.dumps(concept.dict())),
                    )
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
    finals = await _map_concepts(
        state.get("issue_concepts", []) or [],
        state.get("discovered_issue_themes", []) or [],
    )
    return {"final_issue_themes": finals}


async def map_intervention_concepts_to_final_themes(
    state: SynthesisState
) -> SynthesisState:
    print("--- Mapping Intervention Concepts to Final Themes ---")
    finals = await _map_concepts(
        state.get("intervention_concepts", []) or [],
        state.get("discovered_intervention_themes", []) or [],
    )
    return {"final_intervention_themes": finals}


async def build_aggregated_tables(state: SynthesisState) -> SynthesisState:
    """Derive KeyIssue and PolicyIntervention tables from separate final theme sets."""
    print("--- Building Aggregated Tables from Final Themes ---")
    final_issue_themes: List[FinalTheme] = state.get("final_issue_themes", []) or []
    final_intervention_themes: List[FinalTheme] = (
        state.get("final_intervention_themes", []) or []
    )
    issues: List[KeyIssue] = []
    interventions: List[PolicyIntervention] = []

    for t in final_issue_themes:
        issues.append(
            KeyIssue(
                issue_theme=t.name,
                summary_description=t.description,
                frequency=t.frequency,
                source_doc_ids=[],
                justification="Mapped via concept-level classification to this theme.",
            )
        )
    for t in final_intervention_themes:
        interventions.append(
            PolicyIntervention(
                intervention_name=t.name,
                brief_description=t.description,
                impact_summary="Synthesised from grouped concept evidence.",
                frequency=t.frequency,
                supporting_doc_ids=[],
                justification="Mapped via concept-level classification to this theme.",
            )
        )

    return {"aggregated_issues": issues, "aggregated_interventions": interventions}


async def synthesize_executive_briefing(state: SynthesisState) -> SynthesisState:
    """Generates the final executive briefing from separated issues and interventions."""
    print("--- Step 5: Synthesizing Executive Briefing ---")
    rq = state.get("research_question") or "Not specified"
    issues = state.get("final_issue_themes", []) or []
    interventions = state.get("final_intervention_themes", []) or []

    payload = {
        "issues": [
            {"name": t.name, "description": t.description, "frequency": t.frequency}
            for t in issues
        ],
        "interventions": [
            {"name": t.name, "description": t.description, "frequency": t.frequency}
            for t in interventions
        ],
    }

    system = "You are a senior UK policy advisor. Return plaintext only (no markdown)."
    user = (
        "Write a concise executive briefing (2 short paragraphs).\n"
        "- Directly answer the research question.\n"
        "- Distinguish clearly between Key Challenges (issues) and Recommended Interventions.\n"
        "- Close with a high-level assessment of the evidence base.\n\n"
        f"Research question: {rq}\n"
        f"Structured data: {_escape_braces(json.dumps(payload))}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(BRIEFING_MODEL, temperature=0.2)
    try:
        resp = llm.invoke(prompt.format())
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


# Removed: load_research_question (consolidated into load_raw_extractions)


def check_issue_critique(state: SynthesisState) -> str:
    has_critique = bool(state.get("issue_theme_critique"))
    iter_num = int(state.get("issue_theme_iteration") or 0)
    if has_critique and iter_num < 2:
        return "define_issue_themes"
    return "map_issue_concepts_to_final_themes"


def check_intervention_critique(state: SynthesisState) -> str:
    has_critique = bool(state.get("intervention_theme_critique"))
    iter_num = int(state.get("intervention_theme_iteration") or 0)
    if has_critique and iter_num < 2:
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

    async def run(self, project_id: str) -> SynthesisState:
        initial_state: SynthesisState = {"project_id": project_id}  # type: ignore[assignment]
        final_state: SynthesisState = await self.workflow.ainvoke(initial_state)
        return final_state
