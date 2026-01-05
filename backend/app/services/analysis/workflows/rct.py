"""
RCT Extraction Workflow.

Optimized for extracting data from individual RCTs and quasi-experimental studies.
Extracts: Issues → Interventions → Mappings → Results (per intervention) → Conclusions → Validation
"""

import json
import logging
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from .base import BaseExtractionWorkflow, WorkflowState
from ..prompts import (
    ISSUES_PROMPT,
    INTERVENTIONS_PROMPT,
    MAPPING_PROMPT,
    RESULTS_PROMPT,
    CONCLUSIONS_PROMPT,
)
from ..schemas_langchain import (
    IssuesExtraction,
    InterventionsExtraction,
    MappingsExtraction,
    ResultsExtraction,
    ConclusionsExtraction,
)

logger = logging.getLogger(__name__)


class RCTExtractionWorkflow(BaseExtractionWorkflow):
    """Extraction workflow optimized for RCTs and quasi-experimental studies.

    Implements a 4-stage extraction pipeline:
    A. Issues: Extract 1-3 problem statements that motivated the research
    B. Interventions: Extract 2-6 active interventions being evaluated
    C. Mappings: Link issues to interventions with rationale
    D. Results: Extract 1-5 results per intervention (looped)
    E. Conclusions: Extract study conclusions with evidence strength assessment
    F. Validation: Filter items without valid quotes
    """

    workflow_type = "rct"

    def _build_workflow(self) -> StateGraph:
        """Build the RCT extraction workflow graph."""
        workflow = StateGraph(WorkflowState)

        # Add nodes
        workflow.add_node("extract_issues", self._extract_issues)
        workflow.add_node("extract_interventions", self._extract_interventions)
        workflow.add_node("extract_mappings", self._extract_mappings)
        workflow.add_node("extract_results", self._extract_results)
        workflow.add_node("extract_conclusions", self._extract_conclusions)
        workflow.add_node("validate_and_filter", self._validate_and_filter)

        # Define the flow
        workflow.set_entry_point("extract_issues")
        workflow.add_edge("extract_issues", "extract_interventions")
        workflow.add_edge("extract_interventions", "extract_mappings")
        workflow.add_edge("extract_mappings", "extract_results")
        workflow.add_edge("extract_results", "extract_conclusions")
        workflow.add_edge("extract_conclusions", "validate_and_filter")
        workflow.add_edge("validate_and_filter", END)

        return workflow.compile()

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage A: Extract issues."""
        try:
            tags = [
                "component:extraction",
                "component:extraction.issues",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await self._run_prompt_stage(
                ISSUES_PROMPT,
                {"full_text": state["full_text"]},
                tags,
                "rct.extraction.issues",
                extra={"paper_id": state["paper_id"]},
            )

            extraction = IssuesExtraction(**result)
            logger.info(f"[RCT] Extracted {len(extraction.issues)} issues")

            return {"issues": extraction.issues}

        except Exception as e:
            logger.error(f"[RCT] Issues extraction failed: {e}")
            return {"issues": [], "error": f"Issues extraction failed: {e}"}

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage B: Extract interventions."""
        try:
            tags = [
                "component:extraction",
                "component:extraction.interventions",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await self._run_prompt_stage(
                INTERVENTIONS_PROMPT,
                {"full_text": state["full_text"]},
                tags,
                "rct.extraction.interventions",
                extra={"paper_id": state["paper_id"]},
            )

            extraction = InterventionsExtraction(**result)

            # Set intervention_semantic_type for RCT workflow
            for intervention in extraction.interventions:
                intervention.intervention_semantic_type = "trial_intervention"

            logger.info(
                f"[RCT] Extracted {len(extraction.interventions)} interventions"
            )

            return {"interventions": extraction.interventions}

        except Exception as e:
            logger.error(f"[RCT] Interventions extraction failed: {e}")
            return {
                "interventions": [],
                "error": f"Interventions extraction failed: {e}",
            }

    async def _extract_mappings(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage C: Extract mappings between issues and interventions."""
        try:
            if not state["issues"] or not state["interventions"]:
                return {"mappings": []}

            issues_json = self._serialize_for_prompt(state["issues"], "issues")
            interventions_json = self._serialize_for_prompt(
                state["interventions"], "interventions"
            )

            tags = [
                "component:extraction",
                "component:extraction.mappings",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await self._run_prompt_stage(
                MAPPING_PROMPT,
                {
                    "full_text": state["full_text"],
                    "issues_json": issues_json,
                    "interventions_json": interventions_json,
                },
                tags,
                "rct.extraction.mappings",
                extra={"paper_id": state["paper_id"]},
            )

            extraction = MappingsExtraction(**result)
            logger.info(f"[RCT] Extracted {len(extraction.mappings)} mappings")

            return {"mappings": extraction.mappings}

        except Exception as e:
            logger.error(f"[RCT] Mappings extraction failed: {e}")
            return {"mappings": [], "error": f"Mappings extraction failed: {e}"}

    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage D: Extract results per intervention."""
        try:
            if not state["interventions"]:
                return {"results": []}

            all_results = []

            # Process each intervention
            for intervention in state["interventions"]:
                try:
                    one_intervention_json = json.dumps(intervention.model_dump())
                    tags = [
                        "component:extraction",
                        "component:extraction.results",
                        "workflow:rct",
                        f"paper:{state['paper_id']}",
                        f"model:{self.model_name}",
                    ]

                    result = await self._run_prompt_stage(
                        RESULTS_PROMPT,
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": one_intervention_json,
                        },
                        tags,
                        "rct.extraction.results",
                        extra={
                            "paper_id": state["paper_id"],
                            "intervention_idx": intervention.idx,
                        },
                    )

                    extraction = ResultsExtraction(**result)

                    # Set fields for RCT workflow
                    for res in extraction.results:
                        res.intervention_idx = intervention.idx
                        res.estimate_level = "study"

                    all_results.extend(extraction.results)

                except Exception as e:
                    logger.warning(
                        f"[RCT] Results extraction failed for intervention {intervention.idx}: {e}"
                    )
                    continue

            logger.info(
                f"[RCT] Extracted {len(all_results)} results across "
                f"{len(state['interventions'])} interventions"
            )
            return {"results": all_results}

        except Exception as e:
            logger.error(f"[RCT] Results extraction failed: {e}")
            return {"results": [], "error": f"Results extraction failed: {e}"}

    async def _extract_conclusions(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage E: Extract study conclusions with evidence strength assessment."""
        try:
            interventions_json = (
                json.dumps(
                    [
                        intervention.model_dump()
                        for intervention in state["interventions"]
                    ],
                    indent=2,
                )
                if state["interventions"]
                else "No interventions extracted"
            )

            tags = [
                "component:extraction",
                "component:extraction.conclusions",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await self._run_prompt_stage(
                CONCLUSIONS_PROMPT,
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                },
                tags,
                "rct.extraction.conclusions",
                extra={"paper_id": state["paper_id"]},
            )

            extraction = ConclusionsExtraction(**result)
            logger.info("[RCT] Extracted study conclusion with evidence assessment")

            return {"conclusion": extraction.conclusion}

        except Exception as e:
            logger.error(f"[RCT] Conclusions extraction failed: {e}")
            return {"conclusion": None, "error": f"Conclusions extraction failed: {e}"}

    # Uses base class _validate_and_filter - no RCT-specific validation needed
