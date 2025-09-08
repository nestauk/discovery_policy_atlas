from __future__ import annotations

import asyncio
import json
from typing import List, Dict, TypedDict, Optional, Any
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from app.services.vectorization import vectorization_service
from app.utils.llm.llm_utils import get_llm
from langchain_core.prompts import ChatPromptTemplate


class Concept(BaseModel):
    """A data structure for a single enriched concept."""

    id: str
    canonical_description: str


# Model selection per node
HIGH_REASONING_MODEL = "gpt-5"  # define_themes, critique_themes
CLASSIFICATION_MODEL = "gpt-5-nano"  # map_concepts_to_final_themes
BRIEFING_MODEL = "gpt-5"  # synthesize_executive_briefing


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
    concepts: List[Concept]
    discovered_themes: List[DiscoveredTheme]
    theme_critique: Optional[str]
    theme_iteration: int
    final_themes: List[FinalTheme]
    executive_briefing: str


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
    """
    Creates high-quality "canonical descriptions" from structured extraction fields.
    This step does not require an LLM, it's a deterministic formatting step.
    """
    print("--- Step 1: Creating Canonical Concepts ---")

    def generate_description(ext: Dict) -> str:
        if ext.get("intervention_name"):
            return (
                f"Intervention: {ext.get('intervention_name', '')}. "
                f"Type: {ext.get('intervention_type', '')}. "
                f"Description: {ext.get('description', '')}"
            )
        elif ext.get("issue_label"):
            return (
                f"Issue: {ext.get('issue_label', '')}. "
                f"Explanation: {ext.get('explanation', '')}"
            )
        return ""

    concepts = [
        Concept(id=ext["id"], canonical_description=generate_description(ext))
        for ext in state.get("raw_extractions", [])
        if generate_description(ext)
    ]

    return {**state, "concepts": concepts, "theme_iteration": 0}


async def define_themes(state: SynthesisState) -> SynthesisState:
    """
    Uses a principled, single-pass LLM call to discover the natural thematic structure.
    This is the core reasoning step and requires our most powerful model.
    """
    print("--- Step 2: Discovering Themes via Principled Prompt ---")

    critique_prompt_addition = (
        f"You must address the following critique of your previous attempt: {state.get('theme_critique')}"
        if state.get("theme_critique")
        else ""
    )

    concepts_payload = json.dumps([c.dict() for c in state.get("concepts", [])])
    system = "You return STRICT JSON only. No prose."
    user = (
        "You are a senior research analyst at Nesta. Identify the natural thematic structure in the provided concepts.\n\n"
        "Principles:\n"
        "1) Exhaustiveness – cover the full space of the provided concepts.\n"
        "2) Mutual Exclusivity – avoid overlapping themes; merge near-duplicates.\n"
        "3) Appropriate Granularity – mid-level, actionable themes.\n\n"
        f"{critique_prompt_addition}\n\n"
        'Output STRICT JSON with schema: {"themes":[{"theme_name":str,"theme_description":str}]}\n'
        f"Concepts (for reference only – do NOT assign): {concepts_payload}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(HIGH_REASONING_MODEL, temperature=0.0)
    resp = await llm.ainvoke(prompt.format())
    raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json\n"):
            raw = raw[len("json\n") :]
    # Extract JSON substring if model adds any wrapping
    text = raw
    if "{" in raw and "}" in raw:
        try:
            first = raw.index("{")
            last = raw.rindex("}")
            text = raw[first : last + 1]
        except ValueError:
            text = raw
    try:
        data = json.loads(text) or {}
    except json.JSONDecodeError:
        data = {"themes": []}
    items = data.get("themes") or data.get("groups") or []
    discovered_themes = []
    for t in items:
        try:
            discovered_themes.append(
                DiscoveredTheme(
                    theme_name=str(
                        t.get("theme_name") or t.get("name") or "Theme"
                    ).strip(),
                    theme_description=str(
                        t.get("theme_description") or t.get("description") or ""
                    ).strip(),
                )
            )
        except Exception:
            continue
    return {**state, "discovered_themes": discovered_themes}


async def critique_themes(state: SynthesisState) -> SynthesisState:
    """Reviews the discovered themes against the guiding principles."""
    print("--- Step 3: Critiquing Discovered Themes ---")

    themes_payload = json.dumps([t.dict() for t in state.get("discovered_themes", [])])
    system = "You return STRICT TEXT only: either 'None' or a concise list of changes."
    user = (
        "You are a meticulous editor. Assess themes against: Exhaustiveness, Mutual Exclusivity, Appropriate Granularity.\n"
        "If acceptable, reply exactly 'None'. Otherwise, list concise edits (rename themes, merge themes, split themes, add missing themes).\n\n"
        f"Themes: {themes_payload}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(HIGH_REASONING_MODEL, temperature=0.0)
    resp = await llm.ainvoke(prompt.format())
    critique = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    next_iter = int(state.get("theme_iteration") or 0) + 1
    return {
        **state,
        "theme_critique": critique if critique.lower() != "none" else None,
        "theme_iteration": next_iter,
    }


async def map_concepts_to_final_themes(state: SynthesisState) -> SynthesisState:
    """Assign each concept to the best theme via fast parallel classification, then aggregate."""
    print("--- Step 4: Mapping Concepts to Final Themes ---")

    concepts: List[Concept] = state.get("concepts", []) or []
    themes: List[DiscoveredTheme] = state.get("discovered_themes", []) or []
    if not concepts or not themes:
        return {**state, "final_themes": []}

    # Prepare a compact list for prompting
    theme_defs = [
        {"name": t.theme_name, "description": t.theme_description} for t in themes
    ]

    sem = asyncio.Semaphore(12)
    llm = get_llm(CLASSIFICATION_MODEL, temperature=0.0)

    async def _classify(concept: Concept) -> Optional[int]:
        prompt_user = (
            'Classify the concept to the single best matching theme. Return STRICT JSON: {"index": number}.\n\n'
            f"Themes: {json.dumps(theme_defs)}\n"
            f"Concept: {json.dumps(concept.dict())}"
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Return STRICT JSON only."),
                ("user", prompt_user),
            ]
        )
        async with sem:
            try:
                r = await llm.ainvoke(prompt.format())
                raw = (r.content if hasattr(r, "content") else str(r)).strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    if raw.startswith("json\n"):
                        raw = raw[len("json\n") :]
                text = raw
                if "{" in raw and "}" in raw:
                    try:
                        first = raw.index("{")
                        last = raw.rindex("}")
                        text = raw[first : last + 1]
                    except ValueError:
                        text = raw
                data = json.loads(text)
                idx = data.get("index")
                if isinstance(idx, int) and 0 <= idx < len(themes):
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

    return {**state, "final_themes": final_themes_list}


async def synthesize_executive_briefing(state: SynthesisState) -> SynthesisState:
    """Generates the final executive briefing from the high-quality themes."""
    print("--- Step 5: Synthesizing Executive Briefing ---")
    rq = state.get("research_question") or "Not specified"
    themes = state.get("final_themes", []) or []

    # Build compact evidence for briefing
    payload = [
        {
            "name": t.name,
            "description": t.description,
            "frequency": t.frequency,
        }
        for t in themes
    ]

    system = "You are a senior UK policy advisor. Return plaintext only (no markdown)."
    user = (
        "Write a concise executive briefing (2 short paragraphs).\n"
        "- Directly answer the research question.\n"
        "- Use the most frequent themes as key challenges/levers.\n"
        "- Close with a high-level assessment of the evidence base.\n\n"
        f"Research question: {rq}\n"
        f"Themes: {json.dumps(payload)}"
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
    return {**state, "executive_briefing": executive_briefing}


# Removed: load_research_question (consolidated into load_raw_extractions)


def check_critique(state: SynthesisState) -> str:
    """Router function for the self-correction loop."""
    has_critique = bool(state.get("theme_critique"))
    iter_num = int(state.get("theme_iteration") or 0)
    if has_critique and iter_num < 2:
        return "define_themes"
    return "map_concepts_to_final_themes"


def create_synthesis_workflow():
    workflow = StateGraph(SynthesisState)
    workflow.add_node("load_raw_extractions", load_raw_extractions)
    workflow.add_node("create_canonical_concepts", create_canonical_concepts)
    workflow.add_node("define_themes", define_themes)
    workflow.add_node("critique_themes", critique_themes)
    workflow.add_node("map_concepts_to_final_themes", map_concepts_to_final_themes)
    workflow.add_node("synthesize_executive_briefing", synthesize_executive_briefing)

    workflow.set_entry_point("load_raw_extractions")
    workflow.add_edge("load_raw_extractions", "create_canonical_concepts")
    workflow.add_edge("create_canonical_concepts", "define_themes")
    workflow.add_edge("define_themes", "critique_themes")
    workflow.add_conditional_edges("critique_themes", check_critique)
    workflow.add_edge("map_concepts_to_final_themes", "synthesize_executive_briefing")
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
