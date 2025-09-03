from __future__ import annotations

from typing import List, TypedDict, Dict, Tuple, Optional

from langgraph.graph import StateGraph, END

# Schemas for responses and interim state
from app.services.synthesis.schemas import Finding, KeyIssue, PolicyIntervention
from app.services.vectorization import vectorization_service
import json

# numpy import removed - no longer needed for LLM-based clustering
from langchain_core.prompts import ChatPromptTemplate
from discovery_utils.utils.llm.llm_utils import get_llm
from app.core.config import settings


class SynthesisState(TypedDict, total=False):
    """Represents the state of the synthesis agent workflow.

    Fields are intentionally permissive at this stage to allow
    incremental evolution of the agent without breaking changes.
    """

    project_id: str
    research_question: str
    raw_findings: List[Finding]
    aggregated_summary: Dict[str, List]
    executive_briefing: str
    # New fields for the extended workflow
    issue_clusters: Dict[int, List[str]]
    intervention_clusters: Dict[int, List[str]]
    issue_theme_names: Dict[int, str]
    intervention_theme_names: Dict[int, str]
    theme_iteration: int
    finding_to_theme_map: Dict[str, Dict[str, str]]
    extraction_text_by_id: Dict[str, str]
    theme_critique: Optional[str]
    critique_notes: str
    justifications: Dict[str, List[str]]
    aggregated_issues: List[KeyIssue]
    aggregated_interventions: List[PolicyIntervention]


async def fetch_project_data(state: SynthesisState) -> SynthesisState:
    """Fetch initial data (e.g. research question and raw findings) for a project.

    For the initial scaffolding step, this uses placeholder values without
    hitting the database. Future iterations will populate these values from
    the persistence layer (e.g. Supabase/SQLAlchemy).
    """
    print("---FETCHING PROJECT DATA---")
    project_id = state["project_id"]

    supabase = vectorization_service.supabase

    # Load project (to get research question/query)
    project_res = (
        supabase.table("analysis_projects").select("*").eq("id", project_id).execute()
    )
    if not project_res.data:
        raise ValueError(f"Project with ID {project_id} not found")
    project = project_res.data[0]
    research_question = project.get("query") or "Not specified"

    # Load documents for the project
    docs_res = (
        supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    documents = docs_res.data or []

    findings: List[Finding] = _flatten_all_findings(documents)

    return {**state, "research_question": research_question, "raw_findings": findings}


def _flatten_all_findings(documents: List[dict]) -> List[Finding]:
    """Flatten findings across all documents without filtering.

    Mirrors the structure used in the legacy service, but returns all results.
    """
    all_findings: List[Finding] = []
    for doc in documents:
        extraction_results = doc.get("extraction_results") or {}
        if not extraction_results:
            continue

        interventions = extraction_results.get("interventions", []) or []
        results = extraction_results.get("results", []) or []

        # Map intervention index → intervention object
        intr_by_idx = {
            int(i.get("idx")): i
            for i in interventions
            if i is not None and i.get("idx") is not None
        }

        for res in results:
            try:
                intr_idx = int(res.get("intervention_idx"))
            except Exception:
                continue

            intr = intr_by_idx.get(intr_idx) or {}

            evidence_items: List[str] = []
            intr_quote = intr.get("supporting_quote")
            if intr_quote:
                evidence_items.append(str(intr_quote))
            res_quote = res.get("supporting_quote")
            if res_quote:
                evidence_items.append(str(res_quote))
            res_text = res.get("result_text")
            if res_text and str(res_text) not in evidence_items:
                evidence_items.append(str(res_text))

            finding = Finding(
                SourceTitle=str(doc.get("title") or "Unknown Source"),
                Source=str(doc.get("source") or "") or None,
                DocId=str(doc.get("doc_id") or doc.get("id") or "") or None,
                Year=doc.get("year"),
                Url=(
                    doc.get("landing_page_url") or doc.get("pdf_url") or doc.get("url")
                )
                or None,
                Intervention=str(intr.get("name") or "") or None,
                StudyDesign=str(intr.get("study_type") or "") or None,
                Outcome=str(res.get("outcome_variable") or "") or None,
                EffectDirection=str(res.get("effect_direction") or "") or None,
                EffectSizeType=str(res.get("effect_size_type") or "") or None,
                EffectSize=str(res.get("effect_size") or "") or None,
                PValue=str(res.get("p_value") or "") or None,
                Uncertainty=str(res.get("uncertainty") or "") or None,
                Evidence=[e for e in evidence_items if e],
            )
            all_findings.append(finding)

    # Sort similar to legacy service (desc by year, then title)
    all_findings.sort(key=lambda f: (f.Year or 0, f.SourceTitle or ""), reverse=True)
    return all_findings


def create_synthesis_workflow():
    """Create the LangGraph agent for the synthesis process.

    Starts with a single data-fetch step and terminates. Future nodes
    (e.g. clustering, self-critique, justification) will extend this.
    """
    workflow = StateGraph(SynthesisState)

    # Nodes
    workflow.add_node("fetch_project_data", fetch_project_data)
    workflow.add_node("generate_and_assign_themes", generate_and_assign_themes)
    workflow.add_node("critique_generated_themes", critique_generated_themes)
    workflow.add_node("apply_critique_suggestions", apply_critique_suggestions)
    workflow.add_node("build_aggregated_tables", build_aggregated_tables)
    workflow.add_node("synthesize_policy_briefing", synthesize_policy_briefing)

    # Linear flow for now
    workflow.set_entry_point("fetch_project_data")
    workflow.add_edge("fetch_project_data", "generate_and_assign_themes")
    workflow.add_edge("generate_and_assign_themes", "critique_generated_themes")
    workflow.add_conditional_edges(
        "critique_generated_themes",
        check_critique,
        {
            "apply_critique_suggestions": "apply_critique_suggestions",
            "build_aggregated_tables": "build_aggregated_tables",
        },
    )
    workflow.add_edge("apply_critique_suggestions", "generate_and_assign_themes")
    # After tables, synthesize the final policy briefing and end
    workflow.add_edge("build_aggregated_tables", "synthesize_policy_briefing")
    workflow.add_edge("synthesize_policy_briefing", END)

    return workflow.compile()


async def cluster_evidence(state: SynthesisState) -> SynthesisState:
    """Skeleton clustering node.

    For now, returns empty clusters and passes through findings. Future
    iterations will implement MECE clustering using LLM or algorithmic approaches.
    """
    print("---CLUSTERING EVIDENCE (placeholder)---")
    return {**state, "aggregated_summary": {"issues": [], "interventions": []}}


async def critique_clusters(state: SynthesisState) -> SynthesisState:
    """Skeleton critique node.

    Adds placeholder critique notes to support later self-correction.
    """
    print("---CRITIQUE CLUSTERS (placeholder)---")
    return {**state, "critique_notes": "No critique yet (placeholder)."}


async def build_justifications(state: SynthesisState) -> SynthesisState:
    """Skeleton justification node.

    Produces placeholder provenance/justifications for transparency.
    """
    print("---BUILD JUSTIFICATIONS (placeholder)---")
    return {**state, "justifications": {"issues": [], "interventions": []}}


async def generate_briefing(state: SynthesisState) -> SynthesisState:
    """Skeleton executive briefing generation node.

    Uses the research question and (future) clusters to generate a briefing.
    """
    print("---GENERATE BRIEFING (placeholder)---")
    rq = state.get("research_question") or "Not specified"
    briefing = (
        "Executive briefing is being generated by the new agent. "
        f"Research question: {rq}"
    )
    return {**state, "executive_briefing": briefing}


async def synthesize_policy_briefing(state: SynthesisState) -> SynthesisState:
    """Generate policy-grade executive briefing from aggregated tables."""
    print("---SYNTHESIZING POLICY BRIEFING---")
    research_question = state.get("research_question", "")
    top_issues = sorted(
        state.get("aggregated_issues", []) or [],
        key=lambda x: x.frequency,
        reverse=True,
    )[:3]
    top_interventions = sorted(
        state.get("aggregated_interventions", []) or [],
        key=lambda x: x.frequency,
        reverse=True,
    )[:3]

    structured_data_for_prompt = {
        "top_issues": [i.dict() for i in top_issues],
        "top_interventions": [t.dict() for t in top_interventions],
    }

    system = "You are a Principal Policy Advisor. Respond with a concise, neutral executive briefing."
    user = (
        "Write an evidence-grounded briefing strictly using the provided data.\n"
        "Structure: Opening sentence; Key Challenges (2-3); Recommended Interventions (2-3); Evidence Assessment.\n"
        f'Research question: "{research_question}"\n\n'
        f"Structured Evidence Data: {_escape_braces(json.dumps(structured_data_for_prompt)[:15000])}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    try:
        llm = get_llm(settings.LLM_MODEL, temperature=0.2)
        resp = llm.invoke(prompt.format())
        briefing = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        if briefing.startswith("```"):
            briefing = briefing.strip("`")
            if briefing.startswith("text\n"):
                briefing = briefing[len("text\n") :]
    except Exception:
        briefing = (
            f"In response to the query on '{research_question}', the evidence points to key challenges. "
            "The recommended interventions derive from the most frequent clustered themes. "
            "The evidence base spans multiple sources."
        )

    return {**state, "executive_briefing": briefing}


async def build_aggregated_tables(state: SynthesisState) -> SynthesisState:
    """Construct final aggregated tables with summaries and justifications.

    Uses clustered themes and document mappings to produce KeyIssue and
    PolicyIntervention lists suitable for API consumption.
    """
    print("---BUILDING AGGREGATED TABLES---")
    project_id = state.get("project_id", "")

    # Fetch documents to map theme concepts back to document IDs
    supabase = vectorization_service.supabase
    docs_res = (
        supabase.table("analysis_documents")
        .select("id, doc_id, extraction_results")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    documents = docs_res.data or []

    # Build reverse indices: issue_label -> {doc_ids}, intr_name -> {doc_ids}
    issue_to_doc_ids: Dict[str, set] = {}
    intr_to_doc_ids: Dict[str, set] = {}
    for doc in documents:
        doc_id = str(doc.get("doc_id") or doc.get("id") or "")
        extraction_results = doc.get("extraction_results") or {}
        for iss in extraction_results.get("issues") or []:
            label = str(iss.get("label") or "").strip()
            if label:
                issue_to_doc_ids.setdefault(label, set()).add(doc_id)
        for intr in extraction_results.get("interventions") or []:
            name = str(intr.get("name") or "").strip()
            if name:
                intr_to_doc_ids.setdefault(name, set()).add(doc_id)

    aggregated_issues: List[KeyIssue] = []
    aggregated_interventions: List[PolicyIntervention] = []

    # Summarise issues
    issue_clusters = state.get("issue_clusters", {}) or {}
    issue_theme_names = state.get("issue_theme_names", {}) or {}
    for cid, concept_texts in issue_clusters.items():
        theme_name = issue_theme_names.get(cid) or "Issue Theme"
        # Use concept count as frequency for now (until proper doc mapping is fixed)
        frequency = len(concept_texts)
        # TODO: Fix proper document mapping
        doc_ids = []  # Placeholder until mapping is fixed

        # Generate better descriptions using LLM for larger themes
        if frequency >= 3:
            summary = await _generate_theme_summary(theme_name, concept_texts)
        else:
            summary = (
                f"Summary for {theme_name} based on {len(concept_texts)} concept(s)."
            )

        justification = f"Grouped {len(concept_texts)} related concept(s) under a standardised theme."
        aggregated_issues.append(
            KeyIssue(
                issue_theme=theme_name,
                summary_description=summary,
                frequency=frequency,
                source_doc_ids=doc_ids,
                justification=justification,
            )
        )

    # Summarise interventions
    intr_clusters = state.get("intervention_clusters", {}) or {}
    intr_theme_names = state.get("intervention_theme_names", {}) or {}
    for cid, concept_texts in intr_clusters.items():
        theme_name = intr_theme_names.get(cid) or "Intervention Theme"
        # Use concept count as frequency for now (until proper doc mapping is fixed)
        frequency = len(concept_texts)
        doc_ids = []  # Placeholder until mapping is fixed

        # Generate better descriptions using LLM for larger themes
        if frequency >= 3:
            brief_description = await _generate_intervention_brief(
                theme_name, concept_texts
            )
            impact_summary = await _generate_intervention_impact(
                theme_name, concept_texts
            )
        else:
            brief_description = (
                f"Brief description for {theme_name} derived from clustered concepts."
            )
            impact_summary = (
                "Synthesised impact across documents based on the clustered concepts."
            )
        justification = f"Grouped {len(concept_texts)} related concept(s) under a standardised theme."
        aggregated_interventions.append(
            PolicyIntervention(
                intervention_name=theme_name,
                brief_description=brief_description,
                impact_summary=impact_summary,
                frequency=frequency,
                supporting_doc_ids=doc_ids,
                justification=justification,
            )
        )

    return {
        **state,
        "aggregated_issues": aggregated_issues,
        "aggregated_interventions": aggregated_interventions,
    }


def _apply_theme_suggestions(state: SynthesisState, suggestions: Dict) -> None:
    """Apply merges, renames and moves to in-memory clusters and names.

    Mutates the provided state dict in-place. Assumes cluster IDs are current
    integer keys; re-indexes as needed on merges.
    """
    issue_clusters: Dict[int, List[str]] = dict(state.get("issue_clusters", {}) or {})
    intr_clusters: Dict[int, List[str]] = dict(
        state.get("intervention_clusters", {}) or {}
    )
    issue_names: Dict[int, str] = dict(state.get("issue_theme_names", {}) or {})
    intr_names: Dict[int, str] = dict(state.get("intervention_theme_names", {}) or {})

    def _merge(ids: List[int], to_name: str, is_issue: bool) -> None:
        clusters = issue_clusters if is_issue else intr_clusters
        names = issue_names if is_issue else intr_names
        # Create new cluster id
        new_id = max(clusters.keys() or [-1]) + 1
        merged: List[str] = []
        for cid in ids:
            merged.extend(clusters.get(int(cid), []))
            clusters.pop(int(cid), None)
            names.pop(int(cid), None)
        # De-duplicate while preserving order
        seen = set()
        merged_unique = []
        for t in merged:
            if t not in seen:
                seen.add(t)
                merged_unique.append(t)
        clusters[new_id] = merged_unique
        names[new_id] = to_name

    def _rename(cid: int, to_name: str, is_issue: bool) -> None:
        names = issue_names if is_issue else intr_names
        if int(cid) in names:
            names[int(cid)] = to_name

    def _move(concept: str, src: int, dst: int, is_issue: bool) -> None:
        clusters = issue_clusters if is_issue else intr_clusters
        src_list = clusters.get(int(src), [])
        dst_list = clusters.setdefault(int(dst), [])
        if concept in src_list:
            src_list = [t for t in src_list if t != concept]
            clusters[int(src)] = src_list
            if concept not in dst_list:
                dst_list.append(concept)

    # Apply merges
    for m in suggestions.get("merges", []) or []:
        is_issue = (m.get("type") or "").lower().startswith("issue")

        # Handle LLM format: {"from": source_theme_name, "to": target_theme_name}
        from_val = m.get("from")
        to_val = m.get("to")
        to_name = m.get("to_name")

        if from_val is not None and to_val is not None:
            clusters = issue_clusters if is_issue else intr_clusters
            names = issue_names if is_issue else intr_names

            # Try to parse as integers first (cluster IDs)
            try:
                from_id, to_id = int(from_val), int(to_val)
                # Handle as cluster IDs
                if from_id in clusters and to_id in clusters:
                    source_concepts = clusters[from_id]
                    target_concepts = clusters[to_id]

                    # Merge concepts (de-duplicate)
                    merged_concepts = target_concepts[:]
                    for concept in source_concepts:
                        if concept not in merged_concepts:
                            merged_concepts.append(concept)

                    clusters[to_id] = merged_concepts

                    # Remove source cluster
                    del clusters[from_id]
                    if from_id in names:
                        del names[from_id]

                    # Update target name if provided
                    if to_name:
                        names[to_id] = str(to_name).strip()
            except ValueError:
                # Handle as theme names
                from_theme = str(from_val).strip()
                to_theme = str(to_val).strip()

                # Find cluster IDs by theme names
                from_id = None
                to_id = None
                for cid, theme_name in names.items():
                    if theme_name == from_theme:
                        from_id = cid
                    elif theme_name == to_theme:
                        to_id = cid

                # Merge if both found
                if from_id is not None and to_id is not None:
                    source_concepts = clusters.get(from_id, [])
                    target_concepts = clusters.get(to_id, [])

                    # Merge concepts (de-duplicate)
                    merged_concepts = target_concepts[:]
                    for concept in source_concepts:
                        if concept not in merged_concepts:
                            merged_concepts.append(concept)

                    clusters[to_id] = merged_concepts

                    # Remove source cluster
                    if from_id in clusters:
                        del clusters[from_id]
                    if from_id in names:
                        del names[from_id]

        # Fallback: handle legacy format with "from" as array and "to_name"
        elif m.get("from") and m.get("to_name"):
            from_val = m.get("from")
            if isinstance(from_val, list):
                ids = [int(x) for x in from_val]
            elif from_val is not None:
                ids = [int(from_val)]
            else:
                ids = []

            to_name = str(m.get("to_name") or "Merged Theme").strip()
            if ids:
                _merge(ids, to_name, is_issue)

    # Apply renames
    for r in suggestions.get("renames", []) or []:
        is_issue = (r.get("type") or "").lower().startswith("issue")

        # Handle multiple field name formats
        old_name = r.get("old")
        new_name = r.get("new") or r.get("new_name") or r.get("to_name")
        cid = r.get("id") or r.get("index")

        if old_name and new_name:
            # Handle theme name-based rename
            clusters = issue_clusters if is_issue else intr_clusters
            names = issue_names if is_issue else intr_names

            # Find cluster ID by old theme name
            target_cid = None
            for cluster_id, theme_name in names.items():
                if theme_name == str(old_name).strip():
                    target_cid = cluster_id
                    break

            if target_cid is not None:
                names[target_cid] = str(new_name).strip()

        elif cid is not None:
            # Handle cluster ID-based rename
            try:
                cid = int(cid)
                to_name = str(new_name or "Theme").strip()
                _rename(cid, to_name, is_issue)
            except ValueError:
                pass

    # Apply moves
    for mv in suggestions.get("moves", []) or []:
        is_issue = (mv.get("type") or "").lower().startswith("issue")
        concept = str(mv.get("concept") or "").strip()
        src = int(mv.get("from")) if mv.get("from") is not None else None
        dst = int(mv.get("to")) if mv.get("to") is not None else None
        if concept and src is not None and dst is not None:
            _move(concept, src, dst, is_issue)

    # Write back
    state["issue_clusters"] = issue_clusters
    state["intervention_clusters"] = intr_clusters
    state["issue_theme_names"] = issue_names
    state["intervention_theme_names"] = intr_names


def _escape_braces(text: str) -> str:
    """Escape braces for ChatPromptTemplate formatting."""
    return (text or "").replace("{", "{{").replace("}", "}}")


def _get_concepts_from_findings(
    findings: List[Finding], concept_type: str
) -> List[Tuple[str, str]]:
    """Extract concepts (issues or interventions) from raw findings.

    Note: current Finding schema lacks an Issue field; we only extract interventions
    for now and leave issues empty until issue extraction is available.
    """
    concepts: List[Tuple[str, str]] = []
    for f in findings:
        if concept_type == "intervention" and (f.Intervention or "").strip():
            concepts.append((f.DocId or f.SourceTitle, str(f.Intervention)))
        elif concept_type == "issue":
            # Placeholder: no issue field in Finding schema yet
            pass
    return concepts


async def _cluster_and_theme_concepts(
    concepts: List[Tuple[str, str]],  # (extraction_id, concept_text)
) -> Tuple[Dict[int, List[str]], Dict[str, str]]:
    """LLM-based semantic clustering for short concept texts.

    Returns: (clusters, concept_to_theme_name_mapping)
    - clusters: {cluster_id: [concept_texts]}
    - mapping: {concept_text: theme_name}
    """
    if not concepts:
        return {}, {}

    concept_texts = [text for _, text in concepts]

    print(f"LLM clustering {len(concept_texts)} concepts")

    try:
        # Use LLM to semantically group concepts
        from langchain_core.prompts import ChatPromptTemplate
        from app.core.config import settings

        llm = get_llm(settings.LLM_MODEL, temperature=0.1)

        # Prepare concepts list for the prompt
        concepts_list = "\n".join(
            [f"{i+1}. {text}" for i, text in enumerate(concept_texts)]
        )

        print(f"Debug - LLM clustering input: {concepts_list[:200]}...")

        prompt = ChatPromptTemplate.from_template(
            """
You are an expert policy researcher tasked with grouping related concepts into coherent themes.

Review the following list of concepts and group them into 3-8 meaningful themes based on semantic similarity and policy relevance. Concepts that are very similar should be grouped together, while distinct concepts should remain separate.

CONCEPTS TO GROUP:
{concepts_list}

Provide your response as a JSON object with this structure:
{{"groups": [
  {{
    "theme_name": "Clear, descriptive theme name", 
    "concepts": ["concept 1", "concept 2", "concept 3"],
    "rationale": "Brief explanation of why these concepts belong together"
  }}
]}}

Guidelines:
- Aim for 3-8 groups total (fewer groups with more concepts each)
- Group names should be clear and descriptive  
- Each concept should appear in exactly one group
- If a concept is truly unique, it can form its own group
- Focus on semantic meaning and policy domain, not just keyword matching
- Prioritize creating meaningful larger groups over many small groups
"""
        )

        formatted_prompt = prompt.format(concepts_list=_escape_braces(concepts_list))
        print("Debug - About to call LLM for clustering")
        response = await llm.ainvoke(formatted_prompt)
        print(f"Debug - LLM clustering response type: {type(response)}")

        # Parse LLM response
        content = response.content.strip()
        print(f"Debug - LLM clustering raw content: {content[:500]}...")

        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]

        print(f"Debug - Cleaned content for JSON parsing: {content[:200]}...")

        import json

        groups_data = json.loads(content)
        groups_list = groups_data.get("groups", [])
        print(f"Debug - Successfully parsed JSON with {len(groups_list)} groups")

        if not groups_list:
            print(
                "Debug - LLM returned empty groups list, falling back to individual clusters"
            )
            raise ValueError("LLM returned empty groups")

        # Convert to our cluster format
        clusters: Dict[int, List[str]] = {}
        concept_to_theme_name: Dict[str, str] = {}

        for cluster_id, group in enumerate(groups_list):
            theme_name = group.get("theme_name", f"Theme {cluster_id + 1}")
            concepts_in_group = group.get("concepts", [])

            print(
                f"Debug - Processing group {cluster_id}: '{theme_name}' with {len(concepts_in_group)} concepts"
            )

            if concepts_in_group:
                clusters[cluster_id] = concepts_in_group
                for concept in concepts_in_group:
                    concept_to_theme_name[concept] = theme_name

        # Handle any concepts that weren't grouped by the LLM
        grouped_concepts = set(concept_to_theme_name.keys())
        ungrouped = [c for c in concept_texts if c not in grouped_concepts]

        if ungrouped:
            print(
                f"Debug - {len(ungrouped)} concepts were not grouped by LLM: {ungrouped[:5]}..."
            )

        next_id = len(clusters)
        for concept in ungrouped:
            clusters[next_id] = [concept]
            concept_to_theme_name[concept] = f"Theme: {concept}"
            next_id += 1

        print(f"LLM created {len(clusters)} semantic clusters:")
        for cid, concepts_in_cluster in clusters.items():
            theme_name = concept_to_theme_name.get(
                concepts_in_cluster[0], f"Theme {cid}"
            )
            print(f"  {theme_name}: {len(concepts_in_cluster)} concepts")

        return clusters, concept_to_theme_name

    except Exception as e:
        print(f"LLM clustering failed with error: {type(e).__name__}: {e}")
        import traceback

        print(f"LLM clustering traceback: {traceback.format_exc()}")
        # Fallback: each concept gets its own cluster
        clusters = {i: [text] for i, text in enumerate(concept_texts)}
        concept_to_theme_name = {text: f"Theme: {text}" for text in concept_texts}
        print(f"Falling back to {len(clusters)} individual clusters")
        return clusters, concept_to_theme_name


async def _generate_theme_name_for_cluster(concept_texts: List[str]) -> str:
    """Generate a concise theme name for a cluster of related concepts using LLM."""
    from discovery_utils.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts)

    system = "You generate concise, descriptive theme names for clusters of related concepts."
    user = f"""Create a short theme name (3-8 words) that captures the essence of these related concepts:

{concepts_str}

Return ONLY the theme name, starting with "Theme: ". Be specific and descriptive."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.0)
    resp = llm.invoke(prompt.format())
    theme_name = (resp.content if hasattr(resp, "content") else str(resp)).strip()

    # Ensure it starts with "Theme: "
    if not theme_name.startswith("Theme: "):
        theme_name = f"Theme: {theme_name}"

    return theme_name


async def _generate_theme_summary(theme_name: str, concept_texts: List[str]) -> str:
    """Generate a descriptive summary for a theme based on its concepts."""
    from discovery_utils.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts)

    system = "You are a policy researcher writing concise summaries for government briefings."
    user = f"""Write a 1-2 sentence summary for this theme:

Theme: {theme_name}
Related concepts: {concepts_str}

Explain what this theme represents and why it's important for policy makers. Be specific and actionable."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.1)
    resp = llm.invoke(prompt.format())
    return (resp.content if hasattr(resp, "content") else str(resp)).strip()


async def _generate_intervention_brief(
    theme_name: str, concept_texts: List[str]
) -> str:
    """Generate a brief description for an intervention theme."""
    from discovery_utils.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts)

    system = (
        "You are a policy researcher writing brief descriptions of intervention themes."
    )
    user = f"""Write 1-2 sentences describing this intervention theme:

Theme: {theme_name}
Related interventions: {concepts_str}

Describe what these interventions do and their common approach. Be clear and specific."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.1)
    resp = llm.invoke(prompt.format())
    return (resp.content if hasattr(resp, "content") else str(resp)).strip()


async def _generate_intervention_impact(
    theme_name: str, concept_texts: List[str]
) -> str:
    """Generate an impact summary for an intervention theme."""
    from discovery_utils.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts)

    system = "You are a policy researcher summarizing intervention impacts and effectiveness."
    user = f"""Write 1-2 sentences about the impact of this intervention theme:

Theme: {theme_name}
Related interventions: {concepts_str}

Describe the expected impact and effectiveness of these types of interventions. Focus on outcomes and benefits."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.1)
    resp = llm.invoke(prompt.format())
    return (resp.content if hasattr(resp, "content") else str(resp)).strip()


async def generate_and_assign_themes(state: SynthesisState) -> SynthesisState:
    """Generate MECE themes for issues and interventions from raw findings."""
    print("---GENERATING & ASSIGNING THEMES---")
    project_id = state.get("project_id", "")

    # Check if this is a re-iteration (themes already exist and have been modified)
    current_iteration = state.get("theme_iteration", 0)
    if (
        current_iteration > 0
        and state.get("issue_clusters")
        and state.get("intervention_clusters")
    ):
        print(f"Re-iteration {current_iteration}: preserving existing clusters")
        # Return existing state without re-clustering
        return state

    print("Initial clustering: generating themes from raw extractions")
    issue_concepts = _get_issue_concepts_for_project(project_id)
    intr_concepts = _get_intervention_concepts_for_project(project_id)

    # Build helper maps: concept text -> set(extraction_ids)
    issue_text_to_ext_ids: Dict[str, set] = {}
    extraction_text_by_id: Dict[str, str] = {}
    for ext_id, text in issue_concepts:
        extraction_text_by_id[ext_id] = text
        issue_text_to_ext_ids.setdefault(text, set()).add(ext_id)
    intr_text_to_ext_ids: Dict[str, set] = {}
    for ext_id, text in intr_concepts:
        extraction_text_by_id[ext_id] = text
        intr_text_to_ext_ids.setdefault(text, set()).add(ext_id)

    issue_clusters_raw, issue_map = await _cluster_and_theme_concepts(issue_concepts)
    intr_clusters_raw, intr_map = await _cluster_and_theme_concepts(intr_concepts)

    # Use the actual clustering results directly
    issue_clusters = issue_clusters_raw
    intr_clusters = intr_clusters_raw

    # Create theme name mappings
    issue_theme_names = {}
    intervention_theme_names = {}

    # Get theme names for each cluster
    for cluster_id, concept_texts in issue_clusters.items():
        # Get theme name for any concept in this cluster (they all have the same theme)
        theme_name = issue_map.get(
            concept_texts[0], f"Theme: Issue Cluster {cluster_id}"
        )
        issue_theme_names[cluster_id] = theme_name

    for cluster_id, concept_texts in intr_clusters.items():
        # Get theme name for any concept in this cluster (they all have the same theme)
        theme_name = intr_map.get(
            concept_texts[0], f"Theme: Intervention Cluster {cluster_id}"
        )
        intervention_theme_names[cluster_id] = theme_name

    # Build finding-to-theme mapping using extraction IDs
    finding_to_theme_map: Dict[str, Dict[str, str]] = {}
    # Issue assignments
    for cid, concepts in issue_clusters.items():
        theme_name = issue_theme_names.get(cid, "")
        for concept_text in concepts:
            for ext_id in issue_text_to_ext_ids.get(concept_text, set()):
                finding_to_theme_map.setdefault(ext_id, {}).update(
                    {"issue_theme": theme_name}
                )
    # Intervention assignments
    for cid, concepts in intr_clusters.items():
        theme_name = intervention_theme_names.get(cid, "")
        for concept_text in concepts:
            for ext_id in intr_text_to_ext_ids.get(concept_text, set()):
                finding_to_theme_map.setdefault(ext_id, {}).update(
                    {"intervention_theme": theme_name}
                )

    return {
        **state,
        "issue_clusters": issue_clusters,
        "intervention_clusters": intr_clusters,
        "issue_theme_names": issue_theme_names,
        "intervention_theme_names": intervention_theme_names,
        "finding_to_theme_map": finding_to_theme_map,
        "extraction_text_by_id": extraction_text_by_id,
    }


def _get_issue_concepts_for_project(project_id: str) -> List[Tuple[str, str]]:
    """Extract issue concepts from analysis_extractions as (extraction_id, text).

    De-duplicates per analysis_document_id + normalised text while retaining a
    representative extraction_id for each unique concept per document.
    """
    if not project_id:
        return []
    supabase = vectorization_service.supabase
    exts_res = (
        supabase.table("analysis_extractions")
        .select("id, analysis_document_id, extraction_type, label, raw_data")
        .eq("analysis_project_id", project_id)
        .eq("extraction_type", "issue")
        .execute()
    )
    rows = exts_res.data or []
    # De-duplicate per document
    seen: Dict[Tuple[str, str], str] = {}
    for row in rows:
        doc_uuid = str(row.get("analysis_document_id") or "")
        label = str(
            row.get("label") or (row.get("raw_data") or {}).get("label") or ""
        ).strip()
        if not label:
            continue
        key = (doc_uuid, _normalise_concept(label))
        if key not in seen:
            seen[key] = str(row.get("id"))
    concepts: List[Tuple[str, str]] = [
        (ext_id, label) for (_, norm), ext_id in seen.items() for label in [norm]
    ]
    return concepts


def _get_intervention_concepts_for_project(project_id: str) -> List[Tuple[str, str]]:
    """Extract intervention concepts from analysis_extractions as (extraction_id, text).

    De-duplicates per analysis_document_id + normalised text while retaining a
    representative extraction_id for each unique concept per document.
    """
    if not project_id:
        return []
    supabase = vectorization_service.supabase
    exts_res = (
        supabase.table("analysis_extractions")
        .select("id, analysis_document_id, extraction_type, label, raw_data")
        .eq("analysis_project_id", project_id)
        .eq("extraction_type", "intervention")
        .execute()
    )
    rows = exts_res.data or []
    seen: Dict[Tuple[str, str], str] = {}
    for row in rows:
        doc_uuid = str(row.get("analysis_document_id") or "")
        name = str(
            row.get("label") or (row.get("raw_data") or {}).get("name") or ""
        ).strip()
        if not name:
            continue
        key = (doc_uuid, _normalise_concept(name))
        if key not in seen:
            seen[key] = str(row.get("id"))
    concepts: List[Tuple[str, str]] = [
        (ext_id, label) for (_, label), ext_id in seen.items()
    ]
    return concepts


def _normalise_concept(text: str) -> str:
    """Normalise concept text for de-duplication.

    Lowercase, trim, and collapse internal whitespace. Keep punctuation to
    avoid over-merging distinct concepts; further canonicalisation can be
    added later if needed.
    """
    t = (text or "").strip().lower()
    t = " ".join(t.split())
    return t


async def critique_generated_themes(state: SynthesisState) -> SynthesisState:
    """Evaluate generated themes for MECE quality using LLM; return JSON suggestions.

    Expected LLM output (JSON):
    {
      "merges": [ {"type": "issue|intervention", "from": [cluster_ids...], "to_name": "New Canonical Name"}, ...],
      "renames": [ {"type": "issue|intervention", "id": cluster_id, "to_name": "Better Name"}, ...],
      "moves": [ {"type": "issue|intervention", "concept": "text", "from": cluster_id, "to": cluster_id}, ...]
    }
    Return None if themes appear MECE.
    """
    print("---CRITIQUING GENERATED THEMES---")
    print(f"Debug - Starting critique with state keys: {list(state.keys())}")
    print(f"Debug - Issue clusters: {state.get('issue_clusters', {})}")
    print(f"Debug - Intervention clusters: {state.get('intervention_clusters', {})}")

    issues = {
        str(cid): {
            "name": state.get("issue_theme_names", {}).get(cid, ""),
            "concepts": state.get("issue_clusters", {}).get(cid, []),
        }
        for cid in (state.get("issue_clusters", {}) or {}).keys()
    }
    intrs = {
        str(cid): {
            "name": state.get("intervention_theme_names", {}).get(cid, ""),
            "concepts": state.get("intervention_clusters", {}).get(cid, []),
        }
        for cid in (state.get("intervention_clusters", {}) or {}).keys()
    }

    payload = {"issues": issues, "interventions": intrs}
    system = "You critique thematic clusters for MECE quality. Respond with STRICT JSON only."
    user = (
        "Review the clusters. Identify overlaps, poor names, miscategorized concepts.\n"
        'If acceptable MECE, respond with: {{"merges":[],"renames":[],"moves":[]}}\n\n'
        f"Clusters: {_escape_braces(json.dumps(payload)[:15000])}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.0)

    print("Debug - About to call LLM with prompt")
    try:
        resp = llm.invoke(prompt.format())
        print(f"Debug - LLM call successful, response type: {type(resp)}")
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        print(f"LLM critique raw response: {text}")  # Debug logging
    except Exception as e:
        print(f"Debug - LLM call failed: {e}")
        raise

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json\n"):
            text = text[len("json\n") :]

    print(f"LLM critique cleaned text: {text}")  # Debug logging

    try:
        parsed = json.loads(text)
    except Exception as e:
        print(f"JSON parse error: {e}, text was: {text}")  # Debug logging
        parsed = {"merges": [], "renames": [], "moves": []}

    # Empty suggestions means MECE accepted
    if not any(parsed.get(k) for k in ("merges", "renames", "moves")):
        return {**state, "theme_critique": None}

    return {**state, "theme_critique": json.dumps(parsed)}


async def apply_critique_suggestions(state: SynthesisState) -> SynthesisState:
    """Apply critique suggestions and increment iteration counter."""
    print("---APPLYING CRITIQUE SUGGESTIONS---")
    critique_content = state.get("theme_critique")

    if critique_content:
        try:
            suggestions = json.loads(critique_content or "{}")
        except Exception as e:
            print(f"Debug - JSON parse error: {e}")
            suggestions = {"merges": [], "renames": [], "moves": []}

        _apply_theme_suggestions(state, suggestions)
        current_iter = int(state.get("theme_iteration") or 0)
        next_iter = current_iter + 1
        state["theme_iteration"] = next_iter
        print(f"Applied suggestions. Next iteration: {next_iter}")

    return state


def check_critique(state: SynthesisState) -> str:
    """Conditional router: loop if critique exists, else proceed to next."""
    print("---CHECKING CRITIQUE---")
    critique_content = state.get("theme_critique")
    current_iter = int(state.get("theme_iteration") or 0)

    if critique_content and current_iter < 3:
        print("Critique found. Will apply suggestions and loop back.")
        return "apply_critique_suggestions"
    elif current_iter >= 3:
        print("Critique iterations maxed (3). Proceeding.")
        return "build_aggregated_tables"
    else:
        print("No critique. Proceeding.")
        return "build_aggregated_tables"


class SynthesisAgent:
    """Facade for running the synthesis workflow for a given project."""

    def __init__(self) -> None:
        self.workflow = create_synthesis_workflow()

    async def run(self, project_id: str) -> SynthesisState:
        """Run the synthesis agent and return the final state."""
        initial_state: SynthesisState = {"project_id": project_id}
        final_state: SynthesisState = await self.workflow.ainvoke(initial_state)
        return final_state
