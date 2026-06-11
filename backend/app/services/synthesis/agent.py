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

import logging
import time
from typing import Optional

from langgraph.graph import StateGraph, END

from app.services.vectorization import vectorization_service
from app.utils.llm.llm_utils import (
    get_langfuse_handler,
    langfuse_span,
    resolve_langfuse_session_id,
)
from app.services.synthesis.state import SynthesisState
from app.services.synthesis.nodes import (
    load_raw_extractions,
    create_canonical_concepts,
    process_issue_themes,
    process_intervention_themes,
    process_outcome_themes,
    process_risk_themes,
    compute_evidence_coverage,
    build_aggregated_tables,
    compute_impact_syntheses,
    retrieve_evidence_for_themes,
    retrieve_evidence_for_issues,
    retrieve_evidence_for_outcomes,
    apply_rcs_to_theme_evidence,
    apply_rcs_to_issue_evidence,
    apply_rcs_to_outcome_evidence,
    generate_briefing,
)
from app.services.synthesis.schemas import RCSConfig

logger = logging.getLogger(__name__)


def _timed_node(node_fn, node_name: str):
    """Wrap a LangGraph node function so it persists its wall-clock duration
    and creates a Langfuse span whose name matches the timing stage_name.

    Timing is written directly to the ``pipeline_timings`` table (not via
    state) so that parallel nodes don't clobber each other.

    The Langfuse span uses ``start_as_current_span`` so that any LLM calls
    made inside the node are automatically nested as children.
    """

    async def wrapper(state):
        start = time.time()

        with langfuse_span(
            node_name,
            metadata={"project_id": state.get("project_id")},
        ):
            result = await node_fn(state)

        duration = time.time() - start

        project_id = state.get("project_id")
        if project_id:
            try:
                from app.services.timing import persist_timing

                persist_timing(project_id, "synthesis", node_name, duration)
            except Exception as e:
                logger.warning(
                    "Failed to persist synthesis timing for %s: %s", node_name, e
                )

        return result

    # Preserve the original function name for LangGraph introspection
    wrapper.__name__ = node_fn.__name__
    wrapper.__qualname__ = node_fn.__qualname__
    return wrapper


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
    workflow.add_node(
        "load_raw_extractions",
        _timed_node(load_raw_extractions, "load_raw_extractions"),
    )
    workflow.add_node(
        "create_canonical_concepts",
        _timed_node(create_canonical_concepts, "create_canonical_concepts"),
    )

    # Phase 2: Theme discovery (parallel processing)
    workflow.add_node(
        "process_issue_themes",
        _timed_node(process_issue_themes, "process_issue_themes"),
    )
    workflow.add_node(
        "process_intervention_themes",
        _timed_node(process_intervention_themes, "process_intervention_themes"),
    )
    workflow.add_node(
        "process_outcome_themes",
        _timed_node(process_outcome_themes, "process_outcome_themes"),
    )
    workflow.add_node(
        "process_risk_themes", _timed_node(process_risk_themes, "process_risk_themes")
    )

    # Phase 3: Aggregation
    workflow.add_node(
        "compute_evidence_coverage",
        _timed_node(compute_evidence_coverage, "compute_evidence_coverage"),
    )
    workflow.add_node(
        "build_aggregated_tables",
        _timed_node(build_aggregated_tables, "build_aggregated_tables"),
    )
    workflow.add_node(
        "compute_impact_syntheses",
        _timed_node(compute_impact_syntheses, "compute_impact_syntheses"),
    )

    # Phase 4: RAG Retrieval
    workflow.add_node(
        "retrieve_evidence_for_themes",
        _timed_node(retrieve_evidence_for_themes, "retrieve_evidence_for_themes"),
    )
    workflow.add_node(
        "retrieve_evidence_for_issues",
        _timed_node(retrieve_evidence_for_issues, "retrieve_evidence_for_issues"),
    )
    workflow.add_node(
        "retrieve_evidence_for_outcomes",
        _timed_node(retrieve_evidence_for_outcomes, "retrieve_evidence_for_outcomes"),
    )

    # Phase 5: Contextual Summarisation (RCS)
    workflow.add_node(
        "apply_rcs_to_theme_evidence",
        _timed_node(apply_rcs_to_theme_evidence, "apply_rcs_to_theme_evidence"),
    )
    workflow.add_node(
        "apply_rcs_to_issue_evidence",
        _timed_node(apply_rcs_to_issue_evidence, "apply_rcs_to_issue_evidence"),
    )
    workflow.add_node(
        "apply_rcs_to_outcome_evidence",
        _timed_node(apply_rcs_to_outcome_evidence, "apply_rcs_to_outcome_evidence"),
    )

    # Phase 6: Briefing (tool-augmented with mandatory verification)
    workflow.add_node(
        "generate_briefing", _timed_node(generate_briefing, "generate_briefing")
    )

    # Define edges
    workflow.set_entry_point("load_raw_extractions")
    workflow.add_edge("load_raw_extractions", "create_canonical_concepts")

    # Parallel theme processing (fan-out)
    workflow.add_edge("create_canonical_concepts", "process_issue_themes")
    workflow.add_edge("create_canonical_concepts", "process_intervention_themes")
    workflow.add_edge("create_canonical_concepts", "process_outcome_themes")
    workflow.add_edge("create_canonical_concepts", "process_risk_themes")

    # Converge to aggregation (fan-in)
    workflow.add_edge("process_issue_themes", "compute_evidence_coverage")
    workflow.add_edge("process_intervention_themes", "compute_evidence_coverage")
    workflow.add_edge("process_outcome_themes", "compute_evidence_coverage")
    workflow.add_edge("process_risk_themes", "compute_evidence_coverage")

    # Sequential processing: Aggregation -> RAG -> RCS -> Briefing
    workflow.add_edge("compute_evidence_coverage", "build_aggregated_tables")
    workflow.add_edge("build_aggregated_tables", "compute_impact_syntheses")
    workflow.add_edge("compute_impact_syntheses", "retrieve_evidence_for_themes")
    workflow.add_edge("retrieve_evidence_for_themes", "retrieve_evidence_for_issues")

    # RCS processing after RAG retrieval
    workflow.add_edge("retrieve_evidence_for_issues", "retrieve_evidence_for_outcomes")
    workflow.add_edge("retrieve_evidence_for_outcomes", "apply_rcs_to_theme_evidence")
    workflow.add_edge("apply_rcs_to_theme_evidence", "apply_rcs_to_issue_evidence")
    workflow.add_edge("apply_rcs_to_issue_evidence", "apply_rcs_to_outcome_evidence")

    # Briefing generation
    workflow.add_edge("apply_rcs_to_outcome_evidence", "generate_briefing")
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
            "project_id": project_id,
            "langfuse_handler": handler,
            "langfuse_session_id": session_id,
            "policy_user_id": resolved_user,
            "rcs_config": RCSConfig(),
        }
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
