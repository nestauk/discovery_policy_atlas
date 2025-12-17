"""
Synthesis agent for policy atlas.

Uses LangGraph to orchestrate theme discovery, RAG retrieval, and briefing generation.
This module defines the workflow graph and the SynthesisAgent facade.

Briefing generation uses the agentic approach with:
- gpt-5.2 orchestrator for tool selection
- gpt-5-mini for section generation and verification
- Mandatory verification for all claims
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import StateGraph, END

from app.services.vectorization import vectorization_service
from app.utils.llm.llm_utils import get_langfuse_handler, resolve_langfuse_session_id
from app.services.synthesis.state import SynthesisState
from app.services.synthesis.nodes import (
    load_raw_extractions,
    create_canonical_concepts,
    process_issue_themes,
    process_intervention_themes,
    process_outcome_themes,
    compute_evidence_coverage,
    build_aggregated_tables,
    retrieve_evidence_for_themes,
    retrieve_evidence_for_issues,
    apply_rcs_to_theme_evidence,
    apply_rcs_to_issue_evidence,
    generate_briefing,
)
from app.services.synthesis.schemas import RCSConfig


def create_synthesis_workflow():
    """Create the synthesis workflow graph.

    The workflow consists of 6 phases:
    1. Load: Fetch extractions and document metadata
    2. Theme Discovery: Discover, critique, and map themes for issues/interventions/outcomes
    3. Aggregation: Compute evidence coverage and build aggregated tables
    4. RAG Retrieval: Retrieve evidence chunks for grounded citations
    5. Contextual Summarisation (RCS): Score and summarise evidence per theme
    6. Briefing: Tool-augmented generation with mandatory verification

    Returns:
        Compiled LangGraph workflow.
    """
    workflow = StateGraph(SynthesisState)

    # Phase 1: Load

    # Phase 1: Load
    workflow.add_node("load_raw_extractions", load_raw_extractions)
    workflow.add_node("create_canonical_concepts", create_canonical_concepts)

    # Phase 2: Theme discovery (parallel processing)
    workflow.add_node("process_issue_themes", process_issue_themes)
    workflow.add_node("process_intervention_themes", process_intervention_themes)
    workflow.add_node("process_outcome_themes", process_outcome_themes)

    # Phase 3: Aggregation
    workflow.add_node("compute_evidence_coverage", compute_evidence_coverage)
    workflow.add_node("build_aggregated_tables", build_aggregated_tables)

    # Phase 4: RAG Retrieval
    workflow.add_node("retrieve_evidence_for_themes", retrieve_evidence_for_themes)
    workflow.add_node("retrieve_evidence_for_issues", retrieve_evidence_for_issues)

    # Phase 5: Contextual Summarisation (RCS)
    workflow.add_node("apply_rcs_to_theme_evidence", apply_rcs_to_theme_evidence)
    workflow.add_node("apply_rcs_to_issue_evidence", apply_rcs_to_issue_evidence)

    # Phase 6: Briefing (tool-augmented with mandatory verification)
    workflow.add_node("generate_briefing", generate_briefing)

    # Define edges
    workflow.set_entry_point("load_raw_extractions")
    workflow.add_edge("load_raw_extractions", "create_canonical_concepts")

    # Parallel theme processing (fan-out)
    workflow.add_edge("create_canonical_concepts", "process_issue_themes")
    workflow.add_edge("create_canonical_concepts", "process_intervention_themes")
    workflow.add_edge("create_canonical_concepts", "process_outcome_themes")

    # Converge to aggregation (fan-in)
    workflow.add_edge("process_issue_themes", "compute_evidence_coverage")
    workflow.add_edge("process_intervention_themes", "compute_evidence_coverage")
    workflow.add_edge("process_outcome_themes", "compute_evidence_coverage")

    # Sequential processing: Aggregation -> RAG -> RCS -> Briefing
    workflow.add_edge("compute_evidence_coverage", "build_aggregated_tables")
    workflow.add_edge("build_aggregated_tables", "retrieve_evidence_for_themes")
    workflow.add_edge("retrieve_evidence_for_themes", "retrieve_evidence_for_issues")

    # RCS processing after RAG retrieval
    workflow.add_edge("retrieve_evidence_for_issues", "apply_rcs_to_theme_evidence")
    workflow.add_edge("apply_rcs_to_theme_evidence", "apply_rcs_to_issue_evidence")

    # Briefing generation
    workflow.add_edge("apply_rcs_to_issue_evidence", "generate_briefing")
    workflow.add_edge("generate_briefing", END)

    return workflow.compile()


class SynthesisAgent:
    """Facade for running the synthesis workflow.

    Uses tool-augmented briefing with:
    - gpt-5.2 orchestrator for intelligent tool selection
    - gpt-5-mini for section generation and verification
    - Mandatory verification for all claims

    Example:
        agent = SynthesisAgent()
        final_state = await agent.run(project_id="...")
        briefing = final_state.get("structured_briefing")
        briefing_stats = final_state.get("briefing_results")
    """

    def __init__(self) -> None:
        """Initialise the synthesis agent with compiled workflow."""
        self.workflow = create_synthesis_workflow()

    async def run(
        self, project_id: str, user_id: Optional[str] = None
    ) -> SynthesisState:
        """Run the synthesis workflow for a project.

        Args:
            project_id: Analysis project UUID.
            user_id: Optional user ID for tracing.

        Returns:
            Final workflow state with structured_briefing and briefing_results.
        """
        session_id = resolve_langfuse_session_id(project_id)
        handler = get_langfuse_handler(session_id=session_id)
        resolved_user = user_id or self._resolve_project_user(project_id)

        initial_state: SynthesisState = {

        initial_state: SynthesisState = {
            "project_id": project_id,
            "langfuse_handler": handler,
            "langfuse_session_id": session_id,
            "policy_user_id": resolved_user,
            "rcs_config": RCSConfig(),
        }
        return await self.workflow.ainvoke(initial_state)
        return await self.workflow.ainvoke(initial_state)

    @staticmethod
    def _resolve_project_user(project_id: str) -> Optional[str]:
        """Resolve the user ID from the project record.

        Args:
            project_id: Analysis project UUID.

        Returns:
            User ID or None.
        """
        try:
            result = (
                vectorization_service.supabase.table("analysis_projects")
                .select("created_by_user_id")
                .eq("id", project_id)
                .execute()
            )
            return result.data[0].get("created_by_user_id") if result.data else None
            return result.data[0].get("created_by_user_id") if result.data else None
        except Exception:
            return None


async def run_synthesis(
    project_id: str, user_id: Optional[str] = None
) -> SynthesisState:
    """Run the synthesis workflow for a project.

    Convenience function that creates an agent and runs the workflow.

    Args:
        project_id: Analysis project UUID.
        user_id: Optional user ID for tracing.

    Returns:
        Final workflow state with structured_briefing and briefing_results.
    """
    agent = SynthesisAgent()
    return await agent.run(project_id=project_id, user_id=user_id)
