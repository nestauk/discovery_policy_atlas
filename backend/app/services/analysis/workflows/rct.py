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

    def _get_workflow_type(self) -> str:
        return "rct"

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
            chain = ISSUES_PROMPT | self.llm | self.json_parser
            tags = [
                "component:extraction",
                "component:extraction.issues",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await chain.ainvoke(
                {"full_text": state["full_text"]},
                config={
                    "callbacks": self._get_callbacks(),
                    "tags": tags,
                    "metadata": self._build_metadata(
                        tags, extra={"paper_id": state["paper_id"]}
                    ),
                    "run_name": "rct.extraction.issues",
                },
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
            chain = INTERVENTIONS_PROMPT | self.llm | self.json_parser
            tags = [
                "component:extraction",
                "component:extraction.interventions",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await chain.ainvoke(
                {"full_text": state["full_text"]},
                config={
                    "callbacks": self._get_callbacks(),
                    "tags": tags,
                    "metadata": self._build_metadata(
                        tags, extra={"paper_id": state["paper_id"]}
                    ),
                    "run_name": "rct.extraction.interventions",
                },
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

            chain = MAPPING_PROMPT | self.llm | self.json_parser
            tags = [
                "component:extraction",
                "component:extraction.mappings",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await chain.ainvoke(
                {
                    "full_text": state["full_text"],
                    "issues_json": issues_json,
                    "interventions_json": interventions_json,
                },
                config={
                    "callbacks": self._get_callbacks(),
                    "tags": tags,
                    "metadata": self._build_metadata(
                        tags, extra={"paper_id": state["paper_id"]}
                    ),
                    "run_name": "rct.extraction.mappings",
                },
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
            chain = RESULTS_PROMPT | self.llm | self.json_parser

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

                    result = await chain.ainvoke(
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": one_intervention_json,
                        },
                        config={
                            "callbacks": self._get_callbacks(),
                            "tags": tags,
                            "metadata": self._build_metadata(
                                tags,
                                extra={
                                    "paper_id": state["paper_id"],
                                    "intervention_idx": intervention.idx,
                                },
                            ),
                            "run_name": "rct.extraction.results",
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

            chain = CONCLUSIONS_PROMPT | self.llm | self.json_parser
            tags = [
                "component:extraction",
                "component:extraction.conclusions",
                "workflow:rct",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]

            result = await chain.ainvoke(
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                },
                config={
                    "callbacks": self._get_callbacks(),
                    "tags": tags,
                    "metadata": self._build_metadata(
                        tags, extra={"paper_id": state["paper_id"]}
                    ),
                    "run_name": "rct.extraction.conclusions",
                },
            )

            extraction = ConclusionsExtraction(**result)
            logger.info("[RCT] Extracted study conclusion with evidence assessment")

            return {"conclusion": extraction.conclusion}

        except Exception as e:
            logger.error(f"[RCT] Conclusions extraction failed: {e}")
            return {"conclusion": None, "error": f"Conclusions extraction failed: {e}"}

    async def _validate_and_filter(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage F: Post-hoc validation - filter items without valid quotes."""
        try:
            full_text = state["full_text"]

            # Filter issues
            valid_issues = []
            for issue in state["issues"]:
                if issue.supporting_quote and self._fuzzy_quote_match(
                    issue.supporting_quote, full_text
                ):
                    valid_issues.append(issue)
                else:
                    logger.warning(
                        f"[RCT] Filtered out issue {issue.idx}: quote not grounded"
                    )

            # Filter interventions
            valid_interventions = []
            for intervention in state["interventions"]:
                if intervention.supporting_quote and self._fuzzy_quote_match(
                    intervention.supporting_quote, full_text
                ):
                    valid_interventions.append(intervention)
                else:
                    logger.warning(
                        f"[RCT] Filtered out intervention {intervention.idx}: quote not grounded"
                    )

            # Filter mappings
            valid_issue_indices = {issue.idx for issue in valid_issues}
            valid_intervention_indices = {i.idx for i in valid_interventions}
            valid_mappings = []

            for mapping in state["mappings"]:
                if (
                    mapping.issue_idx in valid_issue_indices
                    and mapping.intervention_idx in valid_intervention_indices
                    and mapping.supporting_quote
                    and self._fuzzy_quote_match(mapping.supporting_quote, full_text)
                ):
                    valid_mappings.append(mapping)
                else:
                    logger.warning(
                        f"[RCT] Filtered out mapping {mapping.issue_idx}->{mapping.intervention_idx}"
                    )

            # Filter results
            valid_results = []
            for result in state["results"]:
                if (
                    result.intervention_idx in valid_intervention_indices
                    and result.supporting_quote
                    and self._fuzzy_quote_match(result.supporting_quote, full_text)
                ):
                    valid_results.append(result)
                else:
                    logger.warning(
                        f"[RCT] Filtered out result for intervention {result.intervention_idx}"
                    )

            # Validate conclusion
            valid_conclusion = None
            if state.get("conclusion"):
                conclusion = state["conclusion"]
                if conclusion.supporting_quote and self._fuzzy_quote_match(
                    conclusion.supporting_quote, full_text
                ):
                    valid_conclusion = conclusion
                else:
                    logger.warning("[RCT] Filtered out conclusion: quote not grounded")

            logger.info(
                f"[RCT] Validation complete. Kept: {len(valid_issues)} issues, "
                f"{len(valid_interventions)} interventions, {len(valid_mappings)} mappings, "
                f"{len(valid_results)} results, {'1' if valid_conclusion else '0'} conclusion"
            )

            return {
                "issues": valid_issues,
                "interventions": valid_interventions,
                "mappings": valid_mappings,
                "results": valid_results,
                "conclusion": valid_conclusion,
            }

        except Exception as e:
            logger.error(f"[RCT] Validation failed: {e}")
            return {"error": f"Validation failed: {e}"}
